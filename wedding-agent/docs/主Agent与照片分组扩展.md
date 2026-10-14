# 主 Agent 与照片分组扩展

本轮实现保持旧客户端兼容，同时支持男女照片分组任务。

## 创建任务

`POST /api/tasks` 可以继续传原来的 `photo_file_ids`，也可以传：

```json
{
  "groom_photo_file_ids": ["f_groom_1"],
  "bride_photo_file_ids": ["f_bride_1", "f_bride_2"],
  "description": "想要韩式影棚风",
  "consent": {
    "authorization_scope": "generation_only",
    "retention_days": 7,
    "allow_training": false,
    "watermark": true,
    "delete_original": true,
    "confirmed": true
  }
}
```

新郎和新娘都必须各有 1～10 张照片。任务工单会把两组地址分别写入
`groom_photo_urls` 和 `bride_photo_urls`，并把合并后的地址保留在旧字段
`photo_urls`，这样生图、质检模块不需要立刻改接口。

`consent` 在接口里是可选的：前端已经让用户确认过授权，可以随建单传入；没传或未确认时，
由小囍在第一轮用 `q_consent` 询问（见《主Agent与妆造师修改清单》3.1），确认前不会调用视觉模型。
授权记录位于工单顶层，不会拼进生图提示词。

照片不合格时小囍返回补传题（`type: "upload"`），用户补传后框架在回答里附上 `urls`，
由小囍更新 `groom_photo_urls`、`bride_photo_urls`、`photo_urls`；框架检查每组 1～10 张、
`photo_urls` 等于新郎照片加新娘照片。

## 职责边界

以《主Agent与妆造师修改清单》第 1 节为准：小囍问"是什么"，专家问"选哪个"。

- 小囍负责照片、授权、身高、物料、请柬信息；不问风格、妆容、发型、服装、配饰、背景、场景、灯光、姿势，需求单也不再填这些字段。
- 妆造师负责风格和一套妆造（新娘和新郎一起，资产库种类 `look_set`），最多两轮，结果写入 `look`。
- 摄影师负责互动、姿势、构图、场景、季节和灯光。

## 生图阶段

1. 完成三位 Agent 的需求确认后，生图 Agent 进入 `stage=sample`，只生成 1 张样片并暂停在 `preview_ready`。
2. 用户确认样片时，接口返回 `running`，流程切换到 `stage=set`，生成 9 张婚礼照套图，再次暂停在 `preview_ready`。
3. 用户确认套图后才进入支付和交付；`deliverables.photos` 返回 9 张高清图，`deliverables.photo` 保留主视觉兼容旧客户端。
4. 用户重做时沿用当前阶段的数量：样片重做 1 张，套图重做 9 张；摄影师继续负责场景、季节和灯光问题。
