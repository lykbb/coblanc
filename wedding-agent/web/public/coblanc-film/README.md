# COBLANC 婚纱照交互原型

这是一个静态页面（HTML + CSS + JS）。工作台已经接入小囍后端的 6 个接口：分组上传照片、创建任务、轮询进度、回答问题、样片和套图审核（确认、只要这一张、重做）、模拟支付、交付下载。

## 运行

第一次安装依赖和配置 `.env`，见 [wedding-agent/README.md 的「运行」](../../../README.md#运行)。

终端 1，后端：

```bash
cd ai-wedding/wedding-agent
uv run uvicorn app.api:app --reload --port 8000
# 不花钱测试：REAL_MODULES=none uv run uvicorn app.api:app --reload --port 8000
```

终端 2，前端：

```bash
cd ai-wedding/wedding-agent/web
npm run dev
```

打开 http://localhost:5173/coblanc-film/ 。

## 说明

- 登录是演示：任意 11 位手机号，验证码固定 `123456`，没有登录后端。
- 支付是演示（`method: mock`），不会扣款。
- 页面通过同源 `/api` 访问接口，开发时由 Vite 代理到 `127.0.0.1:8000`，所以后端必须同时开着。
- 接口出错时，工作台顶部会显示红色提示（错误码和说明）。
- 如果页面一直转圈，或提示「连不上后端服务」，检查两个终端是否都还开着。
