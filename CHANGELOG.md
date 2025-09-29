# Changelog

## Unreleased (补充)

- 增强订阅内容校验（filters/validator.py）
  - 增加基于协议前缀计数的 v2 文本检测，过滤掉包含少量或无协议标识的无效页面
  - 改进 Clash YAML 校验：解析 YAML 并确保 `proxies` 或 `proxy-providers` 中至少包含一个代理
  - 改进 Base64 解码后检测：对解码后的内容进行 YAML 或 v2 文本的二次检测
  - 新增 HTML / 错误页面的启发式排除（检测 404、登录/验证码、403 等关键词）
  - 增加可通过环境变量配置的阈值：MIN_V2_LINKS、MIN_CLASH_PROXIES、MIN_BODY_LENGTH

- 新增 vmess 链接校验：能够解析 vmess:// 后的 base64 JSON 并验证必要字段（add, port, id/uuid），减少伪造或短无效 vmess 前缀造成的误判。
- 新增可选样本节点连通性检测（通过 env ENABLE_SAMPLE_NODE_CHECK 开启），可抽取订阅中的若干节点并尝试建立短 TCP 连接以确认订阅中是否包含活动节点（默认关闭）。
- 新增控制项：ENABLE_SAMPLE_NODE_CHECK、SAMPLE_NODE_CHECK_COUNT、SAMPLE_NODE_CHECK_TIMEOUT。

- 在主流程中加入基于 Content-Type 的快速过滤（main.py）：如果响应为 HTML 且未发现订阅特征，则直接忽略，减少误判。

- 新增单元测试（tests/filters/test_validator.py），覆盖常见的有效/无效订阅场景。


# 使用说明

可以通过环境变量调整校验的严格程度：

- MIN_V2_LINKS（默认 1）: v2 文本中最少应包含的协议前缀数量
- MIN_CLASH_PROXIES（默认 1）: Clash YAML 中 proxies 数量最小阈值
- MIN_BODY_LENGTH（默认 30）: 响应体最小字符长度，低于此值直接视为无效

例如：

export MIN_V2_LINKS=2

将要求文本订阅中至少包含两个协议链接才能被认定为有效。
