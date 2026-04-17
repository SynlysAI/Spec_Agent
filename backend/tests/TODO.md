# backend/tests TODO

## 本轮接口稳定性优化待补测试

- [ ] `main.py` 异常映射测试：覆盖 `400/404/422/502/504/500` 的 `status + code + message + request_id`
- [ ] `nmr_server_service.py` 测试：覆盖上游超时、连接失败、非 JSON、`code != 0`、协议字段缺失
- [ ] `nmr_server.py` 端点测试：验证 `NmrServerBusinessError` / `NmrServerProtocolError` 映射到 502，`Timeout` 映射到 504
- [ ] 前端 API 错误分类测试（后续在 frontend 测试框架接入后补）：`timeout/network/http/api_business/canceled`
- [ ] 任务详情页稳定性测试（后续在 frontend 测试框架接入后补）：分阶段拉取、轮询退避、卸载取消请求、局部失败降级

## 备注

- 当前仓库尚未接入统一前端测试框架（例如 Vitest），前端相关用例先记录为待办。
## 已补充的首轮自动化测试建议

- 增加 `task_executors` 注册表单测，覆盖任务类型到执行器映射。
- 增加 `TaskService._validate_input_source` 单测，覆盖 `file_id/file_path/folder_path`。
- 增加 `TaskRepository/ResultRepository/FileRepository` 的 mock 单测，验证字段读写口径。
- 增加配置单测，确认默认运行目录落在 `.runtime/`，默认外部依赖为本地安全值。
