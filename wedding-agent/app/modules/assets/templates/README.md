# 模板（资产库维护）

- `styles/`：风格示例图，文件名 `<风格编号>.jpg`，和妆造师 `prompts/<风格编号>.md` 一一对应，用在追问选项的图片上。
- `poses/`：姿势骨架图，摄影师用 `get_template("poses/<姿势编号>.png")` 取地址。姿势编号按身高差分 3 档：`close_*`（5cm 以内）、`medium_*`（5–15cm）、`large_*`（15cm 以上），例如 `medium_a`。
- `layouts/`：物料版式，文件名用物料名：`invitation.png`（请柬 4:5）、`welcome_poster.png`（迎宾海报 2:3）、`led_screen.png`（婚礼大屏 16:9）、`moments.png`（朋友圈图 1:1）。
