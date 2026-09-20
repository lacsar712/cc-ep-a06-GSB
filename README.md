# 科学实验溯源工作台（Experiment Provenance Workbench）

CQRS + Event Sourcing 全栈示例：命令追加 `event_store`，查询走投影表；Vue 前端查看 Run、事件时间线与血缘。

## How to Run

```bash
cd projects/03-experiment-provenance
docker compose up --build
```

> 镜像默认走 `docker.m.daocloud.io`（便于国内拉取）；前端 npm 使用 `npmmirror`。若你可直连 Docker Hub，可将 Dockerfile / compose 中的镜像前缀改回官方名。

首次启动会：

1. 拉起 PostgreSQL
2. 启动 FastAPI 后端并建表
3. `seed` 写入 2 条已完成 Run + 1 条进行中 Run
4. 构建并启动前端（nginx）

停止：

```bash
docker compose down
```

本地后端测试（可选，需 Python 3.11+）：

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

## Services / 端口

| 服务 | 地址 |
|------|------|
| Frontend | http://localhost:3173 |
| Backend API | http://localhost:8173 |
| PostgreSQL | localhost:54373 |

容器内：

- `db`：Postgres `provenance/provenance`，库名 `provenance`
- `backend`：Uvicorn `:8000`
- `seed`：一次性灌数后退出
- `frontend`：nginx `:80`，`/api` 反代到 backend

## 账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| researcher | lab123456 | 可发命令（Start/Metric/Artifact/Complete/Abort） |
| auditor | audit123456 | 只读事件与投影 |

## Verification

1. 打开 http://localhost:3173 ，使用 `researcher` / `lab123456` 登录
2. 在 Run 列表看到 seed 数据（含进行中与已完成）
3. 点击「新建 Run」，填写 project/name、dataset sha、code commit，启动
4. 在详情页记录指标、挂载产物，再 Complete（或 Abort）
5. 打开「事件时间线」确认 version 递增的原始事件
6. 打开「血缘」确认 code_commit、dataset 指纹、artifacts、metrics
7. 健康检查：`GET http://localhost:8173/api/health`
8. 用 `auditor` 登录：可看列表/事件/血缘，命令按钮不可用

终态或 `expected_version` 不匹配时，API 返回 **409**。

## 架构要点

- **命令**：`StartRun` / `RecordMetric` / `AttachArtifact` / `CompleteRun` / `AbortRun` / `AddTags` / `RemoveTags`
- **事件**：`RunStarted` / `MetricRecorded` / `ArtifactAttached` / `RunCompleted` / `RunAborted` / `RunTagsAdded` / `RunTagsRemoved`
- **event_store**：`(aggregate_id, version)` 唯一；冲突 → 409
- **run_projections**：查询侧投影（状态、指标、产物、`tags_json` 标签等）

### 标签（Tags）

- 落库方式：**走命令写入事件，可回看**。研究员在列表「🏷 标签」面板或 Run 详情页打/删标签，后端追加 `RunTagsAdded` / `RunTagsRemoved` 事件到 `event_store`（带 version、操作人），并投影到 `run_projections.tags_json`；事件时间线可回看每一次标签变更。
- 一条 Run 可保存多个标签；标签在 Run 任意状态（含已完成）均可修改，仍受 `expected_version` 乐观锁保护。
- 列表每行显示已有标签，点击标签或在标签面板/筛选框中按标签过滤；过滤走**服务端**：`GET /api/runs?tag=<label>`，Postgres 下为 JSONB 包含查询 `tags_json @> '["label"]'`。`GET /api/tags` 返回全量标签及计数供面板入口使用。
- 权限：研究员（researcher）可写；审计员（auditor）只能查看，写/删标签返回 403。
