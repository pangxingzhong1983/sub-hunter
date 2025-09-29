# sub-hunter

## 使用说明

项目提供订阅抓取与过滤逻辑，主要过滤器位于 `filters/validator.py`。为了更好地剔除无效订阅，项目新增了若干环境变量用于调优：

- `MIN_V2_LINKS`（默认 1）: 文本订阅中最少应包含的协议前缀数量
- `MIN_CLASH_PROXIES`（默认 1）: Clash YAML 中 proxies 数量最小阈值
- `MIN_BODY_LENGTH`（默认 30）: 响应体最小字符长度
- `ENABLE_SAMPLE_NODE_CHECK`（默认 0）: 是否开启样本节点连通性检测（0/1）
- `SAMPLE_NODE_CHECK_COUNT`（默认 1）: 抽取并检测的样本节点数
- `SAMPLE_NODE_CHECK_TIMEOUT`（默认 2）: 节点连通性检测超时时间（秒）

示例：在运行前通过环境变量启用样本检测并设置阈值：

```bash
export ENABLE_SAMPLE_NODE_CHECK=1
export SAMPLE_NODE_CHECK_COUNT=2
export MIN_V2_LINKS=2
python main.py
```

测试

- 已添加单元测试：执行 `python -m pytest tests/filters/test_validator.py`。
- 项目包含 GitHub Actions CI，用于在 PR/Push 时自动运行测试（见 `.github/workflows/ci.yml`）。
