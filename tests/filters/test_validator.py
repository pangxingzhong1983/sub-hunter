import base64

from filters import validator


def test_clash_yaml_valid():
    yaml = """
proxies:
  - name: node1
    type: vmess
  - name: node2
    type: trojan
"""
    assert validator.looks_like_clash_yaml(yaml)


def test_clash_yaml_invalid_no_proxies():
    yaml = """
proxy-groups:
  - name: "auto"
    type: select
"""
    assert not validator.looks_like_clash_yaml(yaml)


def test_clash_yaml_invalid_proxies_missing_fields():
    yaml = """
proxies:
  - name: node1
  - name: node2
"""
    assert not validator.looks_like_clash_yaml(yaml)


def test_clash_yaml_valid_with_add_field():
    yaml = """
proxies:
  - name: node1
    server: 1.2.3.4
    port: 443
    type: vmess
  - name: node2
    server: example.com
    port: 8080
    type: trojan
"""
    assert validator.looks_like_clash_yaml(yaml)


def test_v2_text_valid():
    body = (
        "\n".join(["vmess://example1", "trojan://example2", "ss://example3"]) + "\n" * 5
    )
    assert validator.looks_like_v2_text(body)


def test_v2_text_short_invalid():
    body = "vmess://x"
    assert not validator.looks_like_v2_text(body)


def test_b64_subscription_valid():
    inner = "\n".join(["vmess://aaa", "vless://bbb"]) + "\n"
    enc = base64.b64encode(inner.encode()).decode()
    assert validator.looks_like_b64_subscription(enc)


def test_html_page_rejected():
    body = "<html><body>Login required</body></html>"
    assert not validator.looks_like_v2_text(body)
    assert not validator.is_valid_subscription("https://example.com/sub", body)


def test_error_page_rejected():
    body = "404 Not Found"
    assert not validator.is_valid_subscription("https://example.com/sub", body)


def test_vmess_b64_parse_valid():
    inner = json_payload = (
        '{"v": "2", "ps": "node1", "add": "1.2.3.4", "port": "443", "id": "11111111-1111-1111-1111-111111111111", "net": "tcp" }'
    )
    enc = base64.b64encode(json_payload.encode()).decode()
    seg = f"vmess://{enc}"
    assert validator._is_valid_vmess_link_segment(seg)


def test_vmess_b64_parse_invalid():
    seg = "vmess://not_base64_or_json"
    assert not validator._is_valid_vmess_link_segment(seg)
