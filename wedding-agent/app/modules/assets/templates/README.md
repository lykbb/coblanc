# 物料库（资产库维护）

妆造师和摄影师用 `search_assets(kind, tags)` 在这里找物料。每放进一个文件，就在 `catalog.json` 里登记一条：

```json
{"asset_id": "pose_medium_a", "kind": "pose", "name": "并肩牵手", "tags": ["medium", "standing"], "file": "poses/medium_a.png"}
```

- `asset_id`：`<种类>_<名字>`，英文小写加下划线，全库唯一。
- `kind`：`style` 风格示例、`outfit` 婚纱西装、`makeup` 妆容、`pose` 姿势骨架、`background` 背景、`layout` 物料版式。
- `tags`：用来检索的标签。风格类带风格编号（如 `korean_studio`）；姿势类带身高档 `close`（5cm 以内）、`medium`（5–15cm）、`large`（15cm 以上）。
- `file`：相对本文件夹的路径，按种类放子文件夹：`styles/`、`outfits/`、`makeups/`、`poses/`、`backgrounds/`、`layouts/`。

物料版式的文件名用物料名：`layouts/invitation.png`（请柬 4:5）、`layouts/welcome_poster.png`（迎宾海报 2:3）、`layouts/led_screen.png`（婚礼大屏 16:9）、`layouts/moments.png`（朋友圈图 1:1）。
