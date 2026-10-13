# 小囍 · AI 婚纱照

上传一张合照，生成婚纱照和婚礼物料（请柬、迎宾海报、婚礼大屏、朋友圈图）。

- 模块分工和开发规范：`docs/小囍模块接入规范.md`
- 前后端接口：`docs/小囍接口约定.md`
- 给 AI 编程助手看的规则：`AGENTS.md`

## 第一次运行

需要 [uv](https://docs.astral.sh/uv/) 和 Node.js 20 以上。

```bash
cp .env.example .env
uv sync
```

```bash
cd web && npm install
```

## 启动

后端（默认 fake 模式，不调用任何付费服务）：

```bash
uv run uvicorn app.api:app --reload --port 8000
```

接口说明页：http://127.0.0.1:8000/docs

前端（另开一个终端）：

```bash
cd web && npm run dev
```

打开 http://localhost:5173 。前端想脱离后端单独开发时，把 `web/.env` 里的 `VITE_USE_MOCK` 设成 `true`。

## 测试

```bash
uv run pytest
```

只跑某个模块：`uv run pytest app/modules/styling`

检查替换后的模块能不能直接接入：`uv run pytest tests/test_contracts.py`

## fake 模式和真实模式

- `.env` 里 `FAKE=1`：所有模块返回示例数据，整条流程不花钱就能跑通。
- 某个模块写好了真实实现，在 `REAL_MODULES` 里写上它的名字（例如 `REAL_MODULES=styling,generation`），其他模块继续用示例数据。
- `FAKE_FAIL_FIRST_CHECK=1`：第一次质检故意不合格，用来演示修图流程。

## 目录

```text
app/
  state.py        工单定义
  graph.py        LangGraph 流程
  runner.py       后台跑流程、暂停等用户、继续
  contracts.py    模块接口契约
  api.py          6 个接口
  common/         配置、大模型、错误、日志、进度
  modules/        intake 小囍 · styling 妆造师 · framing 摄影师
                  generation 生图 agent · review 评测修图师 · assets 资产库
web/              前端（Vue 3 + Vite + Vant）
tests/            示例工单、全流程测试、测试照片
docs/             模块规范和接口约定
```

现在每个模块只有 fake 实现，代码里的 `TODO(模块名)` 是各自要补的地方。
