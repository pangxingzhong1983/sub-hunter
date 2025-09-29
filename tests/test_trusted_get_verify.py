# 尝试直接导入 main_extract_fast；若失败则按文件路径动态加载，确保在各种 pytest/PYTHONPATH 环境下都能运行
try:
    import main_extract_fast as mef
except ModuleNotFoundError:
    import importlib.util
    import pathlib

    p = pathlib.Path(__file__).resolve().parents[1] / "main_extract_fast.py"
    spec = importlib.util.spec_from_file_location("main_extract_fast", str(p))
    mef = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mef)


def test_trusted_get_verify_accepts_subscription(monkeypatch):
    url = "https://raw.githubusercontent.com/example/repo/master/sub.txt"

    # 确保配置启用且包含该 host
    monkeypatch.setattr(mef, "TRUSTED_GET_VERIFY", True)
    monkeypatch.setattr(mef, "TRUSTED_GET_HOSTS", {"raw.githubusercontent.com"})

    # mock fetch_text 返回一个明显的订阅文本（包含 vmess 行）
    def fake_fetch(u, timeout=10):
        assert u == url
        return "vmess://examplebase64==\nvmess://another=="

    monkeypatch.setattr(mef, "fetch_text", fake_fetch)

    ok, reason = mef.trusted_verify_single(url, timeout=2)
    assert ok is True
    assert reason.startswith("validated")


def test_trusted_get_verify_rejects_rules(monkeypatch):
    url = "https://raw.githubusercontent.com/example/repo/master/config.yaml"

    monkeypatch.setattr(mef, "TRUSTED_GET_VERIFY", True)
    monkeypatch.setattr(mef, "TRUSTED_GET_HOSTS", {"raw.githubusercontent.com"})

    # mock fetch_text 返回一个规则文件样例（domain-suffix 等）
    def fake_fetch(u, timeout=10):
        return "domain-suffix,google.com\ndomain,ads.example\nrule-set: something"

    monkeypatch.setattr(mef, "fetch_text", fake_fetch)

    ok, reason = mef.trusted_verify_single(url, timeout=2)
    assert ok is False
    assert reason in ("not_subscription", "empty") or reason.startswith(
        "validator_error"
    )
