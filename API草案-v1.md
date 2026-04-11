# API 草案（v1）

## 1. 文档目标

- 定义重构项目 P0 阶段的后端接口契约草案
- 约束前后端联调与任务执行的输入输出结构
- 为后续 OpenAPI 实现提供实现基线

## 2. 范围说明（P0）

- 任务提交：`GPC`、`NMR`
- 任务中心：任务状态查询、任务结果查询
- 文件管理：文件上传
- 健康检查：服务可用性检查

不在 v1 范围：

- IR/Raman（延后到 P1）
- NMR 两段式交互任务（已明确不采用）

## 3. 通用约定

## 3.1 URL 前缀

- `/api/v1`

## 3.2 认证方式（预留）

- P0 可先不启用登录
- 预留 Header：`Authorization: Bearer <token>`

## 3.3 通用响应结构

成功响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

失败响应：

```json
{
  "code": 40001,
  "message": "invalid parameter",
  "data": null,
  "request_id": "d1f8c6..."
}
```

## 3.4 任务状态枚举

- `PENDING`
- `QUEUED`
- `RUNNING`
- `SUCCESS`
- `FAILED`
- `CANCELED`（预留）

## 3.5 错误码建议（首版）

- `40001` 参数错误
- `40002` 文件类型不支持
- `40003` 文件不存在
- `40401` 任务不存在
- `50001` 内部执行错误
- `50002` 下游服务异常

## 4. 文件上传接口

## 4.1 上传文件

- `POST /api/v1/files/upload`
- `Content-Type: multipart/form-data`

请求参数：

- `file`：二进制文件（必填）
- `biz_type`：业务类型（可选，`gpc`/`nmr`）

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "file_id": "f_20260410_0001",
    "file_name": "sample.arw",
    "file_size": 24576,
    "file_ext": ".arw",
    "storage_path": "uploads/2026/04/10/f_20260410_0001_sample.arw",
    "sha256": "4b7d..."
  }
}
```

校验规则：

- 空文件拒绝
- 扩展名白名单校验（按 `biz_type` 区分）
- 单文件大小上限可配置（默认 100MB）

## 5. 任务接口：GPC

## 5.1 提交 GPC 任务

- `POST /api/v1/tasks/gpc`
- `Content-Type: application/json`

请求体：

```json
{
  "input": {
    "input_type": "file_path",
    "input_path": "E:/spectrum_files/gpc/spectrum/a.arw",
    "file_id": null
  },
  "params": {
    "detect_mode": "auto",
    "manual_interval": null,
    "three_color_arw_paths": null,
    "calibration_file_path": null,
    "comparison_report_pdf_path": null
  },
  "options": {
    "priority": 5,
    "callback_url": null
  }
}
```

字段说明：

- `input.input_type`：`file_path` 或 `file_id`
- `input.input_path`：当 `input_type=file_path` 必填
- `input.file_id`：当 `input_type=file_id` 必填
- `params.detect_mode`：`auto` 或 `manual`
- `params.manual_interval`：`[start, end]`，`manual` 模式必填

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "t_gpc_20260410_0001",
    "task_type": "gpc_analysis",
    "status": "PENDING"
  }
}
```

## 6. 任务接口：NMR

## 6.1 提交 NMR 任务（单阶段）

- `POST /api/v1/tasks/nmr`
- `Content-Type: application/json`

请求体：

```json
{
  "input": {
    "input_type": "folder_path",
    "input_path": "E:/spectrum_files/nmr/2026-03-11/sample01",
    "file_id": null
  },
  "params": {
    "nucleus": "1H",
    "threshold": 0.01,
    "min_distance": 0.3,
    "min_prominence": 0.01,
    "width_multiplier": 1.0,
    "baseline_degree": 3,
    "smooth_window": 5,
    "detection_range_mode": "full",
    "detection_range_min": null,
    "detection_range_max": null,
    "ppm_offset": 0.0,
    "integration_method": "voigt",
    "internal_standard_policy": "auto",
    "internal_standard_prefer": ["solvent", "tms"]
  },
  "options": {
    "priority": 5,
    "callback_url": null
  }
}
```

关键约束：

- NMR 不采用两段式任务
- 首次调用必须给出完整解析参数
- `internal_standard_policy=auto` 时，系统按 `internal_standard_prefer` 自动确定内标峰
- 推荐策略：先匹配溶剂峰，失败再匹配 TMS 峰

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "t_nmr_20260410_0001",
    "task_type": "nmr_analysis",
    "status": "PENDING"
  }
}
```

## 7. 任务中心接口

## 7.1 查询任务状态

- `GET /api/v1/tasks/{task_id}`

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "t_nmr_20260410_0001",
    "task_type": "nmr_analysis",
    "status": "RUNNING",
    "progress": 45,
    "message": "peak detection finished",
    "created_at": "2026-04-10T15:10:00+08:00",
    "updated_at": "2026-04-10T15:12:30+08:00"
  }
}
```

## 7.2 查询任务结果

- `GET /api/v1/tasks/{task_id}/result`

成功结果示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "t_gpc_20260410_0001",
    "status": "SUCCESS",
    "result": {
      "structured_data": {},
      "text_report": "# GPC 分析报告...",
      "metadata": {
        "spectrum_type": "gpc"
      }
    }
  }
}
```

失败结果示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "t_gpc_20260410_0002",
    "status": "FAILED",
    "error": {
      "error_code": "50001",
      "error_message": "file format invalid",
      "error_detail": "only .arw is supported"
    }
  }
}
```

## 8. 健康检查接口

## 8.1 服务健康检查

- `GET /api/v1/health`

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "api": "up",
    "mongodb": "up",
    "rabbitmq": "up",
    "worker": "up",
    "time": "2026-04-10T15:20:00+08:00"
  }
}
```

## 9. MongoDB 建议集合结构（草案）

## 9.1 `tasks`

```json
{
  "task_id": "t_nmr_20260410_0001",
  "task_type": "nmr_analysis",
  "status": "RUNNING",
  "input": {},
  "params": {},
  "progress": 45,
  "message": "peak detection finished",
  "result_ref": "r_20260410_0001",
  "error": null,
  "created_at": "2026-04-10T15:10:00+08:00",
  "updated_at": "2026-04-10T15:12:30+08:00"
}
```

## 9.2 `analysis_results`

```json
{
  "result_id": "r_20260410_0001",
  "task_id": "t_nmr_20260410_0001",
  "task_type": "nmr_analysis",
  "structured_data": {},
  "text_report": "# NMR 分析报告...",
  "artifacts": [
    {
      "type": "image",
      "path": "outputs/tasks/t_nmr_20260410_0001/plot1.png"
    }
  ],
  "created_at": "2026-04-10T15:15:00+08:00"
}
```

## 9.3 `files`

```json
{
  "file_id": "f_20260410_0001",
  "file_name": "sample.arw",
  "storage_path": "uploads/2026/04/10/f_20260410_0001_sample.arw",
  "file_ext": ".arw",
  "file_size": 24576,
  "sha256": "4b7d...",
  "created_at": "2026-04-10T15:00:00+08:00"
}
```

## 10. 待确认项

1. `input_type` 是否统一只保留 `file_id`（避免直接传本地绝对路径）
2. `progress` 是否按 0~100 整数统一
3. NMR 自动内标峰策略的最终判定阈值（溶剂峰/TMS 匹配容差）
4. 是否在 P0 即加入 `DELETE /api/v1/tasks/{task_id}`（取消任务）

## 11. 版本记录

- v0.1（2026-04-10）：P0 接口草案首版（GPC/NMR/任务中心/文件上传/健康检查）
