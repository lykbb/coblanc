#!/bin/zsh
# 一键重新部署到 43.142.59.166（不传 .env；要更新 .env 用：./deploy.sh --env）
# 三个站点：前台（裸 IP / 以后主域名）、图墙 gallery.$BASE、后台管理 abordadmin.$BASE。
# 更新 nginx：./deploy.sh --nginx（http）；有真实域名和证书后：BASE=域名 ./deploy.sh --nginx --https
set -e
export PATH=/opt/homebrew/bin:$PATH
cd "$(dirname "$0")"
KEY=~/.ssh/wedding_server.pem; H=ubuntu@43.142.59.166
SSH=(ssh -i $KEY -o IdentitiesOnly=yes)
BASE=${BASE:-43.142.59.166.nip.io}  # 内部站点的根域名（nip.io 通配解析到服务器 IP），以后换真实域名

if [[ "$1" == "--nginx" ]]; then
  # 渲染 deploy/nginx/*.template → 上传 → 备份旧配置 → 安装 → nginx -t 通过才 reload，失败自动还原
  MODE=http; [[ "$2" == "--https" ]] && MODE=https
  OUT=$(mktemp -d); python3 deploy/nginx/render.py "$BASE" $MODE "$OUT"
  rsync -a -e "${SSH[*]}" "$OUT/" ${H}:/tmp/wedding-nginx/ && rm -rf "$OUT"
  $SSH $H 'set -e; cd /tmp/wedding-nginx; TS=$(date +%Y%m%d%H%M%S); sudo mkdir -p /etc/nginx/snippets /var/www/certbot /etc/nginx/backup-$TS
    for f in wedding wedding-gallery wedding-admin; do [ -f /etc/nginx/sites-available/$f ] && sudo cp /etc/nginx/sites-available/$f /etc/nginx/backup-$TS/; sudo install -m 644 $f /etc/nginx/sites-available/$f; sudo ln -sf /etc/nginx/sites-available/$f /etc/nginx/sites-enabled/$f; done
    [ -f /etc/nginx/snippets/wedding-portal.conf ] && sudo cp /etc/nginx/snippets/wedding-portal.conf /etc/nginx/backup-$TS/
    sudo install -m 644 wedding-portal.conf /etc/nginx/snippets/wedding-portal.conf
    for f in admin gallery; do [ -f /etc/nginx/.htpasswd-$f ] || echo "提醒：还没有 /etc/nginx/.htpasswd-$f（sudo htpasswd -c /etc/nginx/.htpasswd-$f 用户名）"; done
    if sudo nginx -t; then sudo systemctl reload nginx && echo "nginx 已更新（备份在 /etc/nginx/backup-$TS）"; else
      echo "nginx -t 失败，还原旧配置"; for f in wedding wedding-gallery wedding-admin; do if [ -f /etc/nginx/backup-$TS/$f ]; then sudo cp /etc/nginx/backup-$TS/$f /etc/nginx/sites-available/$f; else sudo rm -f /etc/nginx/sites-enabled/$f /etc/nginx/sites-available/$f; fi; done
      [ -f /etc/nginx/backup-$TS/wedding-portal.conf ] && sudo cp /etc/nginx/backup-$TS/wedding-portal.conf /etc/nginx/snippets/; sudo nginx -t; exit 1; fi
    rm -rf /tmp/wedding-nginx'
  exit 0
fi

(cd wedding-agent/web && npm run build)
# 内部站点：图墙 gallery、后台 admin，按子域名各自独立 nginx server，见 deploy/nginx/
for APP in admin gallery; do (cd wedding-agent/$APP && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build); done
# 后端代码指纹：只有它变了（或 --env / --restart）才重启后端，避免无谓重启打断正在跑的任务
SUM='cd ~/ai-wedding 2>/dev/null && find wedding-agent/app wedding-agent/pyproject.toml wedding-agent/uv.lock pi-wedding -path pi-wedding/node_modules -prune -o -type f ! -name "*.pyc" -print0 2>/dev/null | sort -z | xargs -0 md5sum | md5sum'
BEFORE=$($SSH $H "$SUM" || true)
rsync -az -e "${SSH[*]}" --exclude node_modules --exclude .venv --exclude runs/ --exclude 'wedding-agent/state/' --exclude 'wedding-agent/reference_library/' \
  --exclude 'wedding-agent/storage/*/*' --exclude .DS_Store --exclude __pycache__ --exclude .env --exclude "ubuntu@*" ./ ${H}:ai-wedding/
rsync -az --delete -e "${SSH[*]}" wedding-agent/web/dist/ ${H}:ai-wedding/wedding-agent/web/dist/
for APP in admin gallery; do rsync -az --delete -e "${SSH[*]}" wedding-agent/$APP/dist/ ${H}:ai-wedding/wedding-agent/$APP/dist/; done
[[ "$1" == "--env" ]] && scp -q -i $KEY -o IdentitiesOnly=yes wedding-agent/.env ${H}:ai-wedding/wedding-agent/.env
# 摄影师/生图的 Pi 运行时直接跑 TypeScript，需要 Node ≥ 23.6；服务器自带 Node 22 不行，缺了就装 Node 24 到 ~/.local/node24
$SSH $H 'V=v24.16.0; N=~/.local/node24/bin/node; if ! [ -x $N ] || [ "$($N -p "process.versions.node.split(\".\")[0]")" -lt 24 ]; then echo "安装 Node $V 到 ~/.local/node24"; cd /tmp && curl -sfLO https://registry.npmmirror.com/-/binary/node/$V/node-$V-linux-x64.tar.xz && mkdir -p ~/.local/node24 && tar -xJf node-$V-linux-x64.tar.xz -C ~/.local/node24 --strip-components=1 && rm -f node-$V-linux-x64.tar.xz; fi; $N -v'
$SSH $H 'export PATH=$HOME/.local/node24/bin:$PATH; chmod 600 ~/ai-wedding/wedding-agent/.env; cd ~/ai-wedding/wedding-agent && UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple ~/.local/bin/uv sync -q --frozen --python 3.11 && cd ../pi-wedding && npm ci --registry=https://registry.npmmirror.com --no-audit --no-fund -s'
AFTER=$($SSH $H "$SUM")
BUSY=$($SSH $H 'cd ~/ai-wedding/wedding-agent && grep -lE "\"status\": *\"(running|delivering)\"" state/tasks/*.json 2>/dev/null | wc -l')
if [[ ( "$BEFORE" != "$AFTER" || "$1" == "--env" || "$1" == "--restart" ) && "$BUSY" -gt 0 && "$2" != "--force" && "$1" != "--force" ]]; then
  echo "有 $BUSY 个任务正在生成，暂不重启（代码已同步，稍后再跑 ./deploy.sh --restart；确需立即重启加 --force）"
elif [[ "$BEFORE" != "$AFTER" || "$1" == "--env" || "$1" == "--restart" || "$1" == "--force" ]]; then
  echo "后端有改动，重启 wedding-backend"
  $SSH $H 'sudo systemctl restart wedding-backend && sleep 3 && systemctl is-active wedding-backend'
else
  echo "后端没改动，不重启（只更新了前端）"
fi
