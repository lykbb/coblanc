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

未传入已确认的 `consent` 时，小囍会先询问授权范围，确认前不会调用视觉模型。
默认建议是不用于训练、预览带水印、保留 7 天、交付后删除原图。授权记录位于工单顶层，
不会拼进生图提示词。

## 职责边界

- 小囍负责照片分组数量、授权、风格和物料。
- 妆造师负责妆容、发型、婚纱、西装和配饰；分组照片任务会追加发型与配饰追问，最终细节写入 `look.text`。
- 摄影师负责互动、姿势、构图、场景、季节和灯光，避免妆造师重复追问。

## 生图阶段

1. 完成三位 Agent 的需求确认后，生图 Agent 进入 `stage=sample`，只生成 1 张样片并暂停在 `preview_ready`。
2. 用户确认样片时，接口返回 `running`，流程切换到 `stage=set`，生成 9 张婚礼照套图，再次暂停在 `preview_ready`。
3. 用户确认套图后才进入支付和交付；`deliverables.photos` 返回 9 张高清图，`deliverables.photo` 保留主视觉兼容旧客户端。
4. 用户重做时沿用当前阶段的数量：样片重做 1 张，套图重做 9 张；摄影师继续负责场景、季节和灯光问题。
