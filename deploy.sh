#!/bin/zsh
# 一键重新部署到 43.142.59.166（不传 .env；要更新 .env 用：./deploy.sh --env）
# 三个站点：前台（裸 IP / 以后主域名）；图墙、后台管理按 SITE_MODE 部署：
#   path（默认）：http://IP/gallery/、http://IP/abordadmin/（不需要域名、不开新端口）
#   subdomain：gallery.$BASE、abordadmin.$BASE（需要已备案域名）
# 更新 nginx：./deploy.sh --nginx；有域名和证书后：SITE_MODE=subdomain BASE=域名 ./deploy.sh --nginx --https
set -e
export PATH=/opt/homebrew/bin:$PATH
cd "$(dirname "$0")"
KEY=~/.ssh/wedding_server.pem; H=ubuntu@43.142.59.166
SSH=(ssh -i $KEY -o IdentitiesOnly=yes)
SITE_MODE=${SITE_MODE:-path}; export SITE_MODE  # 前端构建（vite base）和 nginx 渲染都用它
BASE=${BASE:-43.142.59.166.nip.io}  # subdomain 模式的根域名；以后换真实域名

if [[ "$1" == "--nginx" ]]; then
  # 渲染 deploy/nginx 模板 → 上传 → 整体备份 /etc/nginx → 安装 → nginx -t 通过才 reload，失败整体还原
  SCHEME=http; [[ "$2" == "--https" ]] && SCHEME=https
  OUT=$(mktemp -d); python3 deploy/nginx/render.py $SITE_MODE $SCHEME "$BASE" "$OUT"
  cp deploy/fail2ban/* "$OUT/"
  rsync -a --delete -e "${SSH[*]}" "$OUT/" ${H}:/tmp/wedding-nginx/ && rm -rf "$OUT"
  $SSH $H 'set -e; cd /tmp/wedding-nginx; BK=/etc/nginx/backup-$(date +%Y%m%d%H%M%S).tgz
    sudo tar czf $BK -C /etc nginx/sites-available nginx/sites-enabled nginx/snippets $(cd /etc && ls nginx/wedding-allow-ips.conf 2>/dev/null)
    sudo mkdir -p /etc/nginx/snippets /var/www/certbot
    # 先清掉本项目的旧配置（换部署方式时不留残余），再装这次渲染的
    sudo rm -f /etc/nginx/sites-enabled/wedding-gallery /etc/nginx/sites-enabled/wedding-admin /etc/nginx/sites-available/wedding-gallery /etc/nginx/sites-available/wedding-admin /etc/nginx/snippets/wedding-portal*.conf /etc/nginx/wedding-allow-ips.conf
    for f in sites/*; do n=$(basename $f); sudo install -m 644 $f /etc/nginx/sites-available/$n; sudo ln -sf /etc/nginx/sites-available/$n /etc/nginx/sites-enabled/$n; done
    for f in snippets/*; do sudo install -m 644 $f /etc/nginx/snippets/$(basename $f); done
    for f in .htpasswd .htpasswd-admin; do [ -f /etc/nginx/$f ] || echo "提醒：还没有 /etc/nginx/$f（登录页账号密码，sudo htpasswd -c /etc/nginx/$f 用户名）"; done
    if sudo nginx -t; then sudo systemctl reload nginx && echo "nginx 已更新（备份 $BK）"; else
      echo "nginx -t 失败，整体还原"; sudo rm -rf /etc/nginx/sites-available /etc/nginx/sites-enabled /etc/nginx/snippets; sudo tar xzf $BK -C /etc; sudo nginx -t; exit 1; fi
    # fail2ban（deploy/fail2ban）：登录输错密码、扫描敏感路径、频繁 429；团队白名单 IP 不封（见 wedding.jail）
    if command -v fail2ban-client >/dev/null; then
      FB=/etc/fail2ban/backup-$(date +%Y%m%d%H%M%S).tgz; sudo tar czf $FB -C /etc fail2ban/jail.d fail2ban/filter.d
      for f in *.filter; do sudo install -m 644 $f /etc/fail2ban/filter.d/${f%.filter}.conf; done
      sudo rm -f /etc/fail2ban/jail.d/nginx-http-auth.local /etc/fail2ban/jail.d/wedding-login.local
      sudo install -m 644 wedding.jail /etc/fail2ban/jail.d/wedding.local
      if sudo fail2ban-client -t >/dev/null 2>&1; then sudo fail2ban-client reload && echo "fail2ban 已更新（备份 $FB）"; else
        echo "fail2ban 配置检查失败，还原"; sudo rm -f /etc/fail2ban/jail.d/wedding.local; sudo tar xzf $FB -C /etc; fi; fi
    rm -rf /tmp/wedding-nginx'
  exit 0
fi

(cd wedding-agent/web && npm run build)
# 内部站点：图墙 gallery、后台 admin（vite base 随 SITE_MODE），nginx 见 deploy/nginx/
for APP in admin gallery; do (cd wedding-agent/$APP && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build); done
# 后端代码指纹：只有它变了（或 --env / --restart）才重启后端，避免无谓重启打断正在跑的任务
SUM='cd ~/ai-wedding 2>/dev/null && find wedding-agent/app wedding-agent/pyproject.toml wedding-agent/uv.lock pi-wedding -path pi-wedding/node_modules -prune -o -type f ! -name "*.pyc" -print0 2>/dev/null | sort -z | xargs -0 md5sum | md5sum'
BEFORE=$($SSH $H "$SUM" || true)
# 代码：--delete 让服务器不留本地已删的旧文件；数据、密钥、依赖、服务器独有文件和 .git 按 deploy/rsync.rules 不传不删
rsync -az --delete --filter='merge deploy/rsync.rules' -e "${SSH[*]}" ./ ${H}:ai-wedding/
rsync -az --delete -e "${SSH[*]}" wedding-agent/web/dist/ ${H}:ai-wedding/wedding-agent/web/dist/
for APP in admin gallery; do rsync -az --delete -e "${SSH[*]}" wedding-agent/$APP/dist/ ${H}:ai-wedding/wedding-agent/$APP/dist/; done
[[ "$1" == "--env" ]] && scp -q -i $KEY -o IdentitiesOnly=yes wedding-agent/.env ${H}:ai-wedding/wedding-agent/.env
# 摄影师/生图的 Pi 运行时直接跑 TypeScript，需要 Node ≥ 23.6；服务器自带 Node 22 不行，缺了就装 Node 24 到 ~/.local/node24
$SSH $H 'V=v24.16.0; N=~/.local/node24/bin/node; if ! [ -x $N ] || [ "$($N -p "process.versions.node.split(\".\")[0]")" -lt 24 ]; then echo "安装 Node $V 到 ~/.local/node24"; cd /tmp && curl -sfLO https://registry.npmmirror.com/-/binary/node/$V/node-$V-linux-x64.tar.xz && mkdir -p ~/.local/node24 && tar -xJf node-$V-linux-x64.tar.xz -C ~/.local/node24 --strip-components=1 && rm -f node-$V-linux-x64.tar.xz; fi; $N -v'
$SSH $H 'export PATH=$HOME/.local/node24/bin:$PATH; chmod 600 ~/ai-wedding/wedding-agent/.env; cd ~/ai-wedding/wedding-agent && UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple ~/.local/bin/uv sync -q --frozen --python 3.11 && cd ../pi-wedding && npm ci --registry=https://registry.npmmirror.com --no-audit --no-fund -s'
# 登录页校验用的 htpasswd 是 root:www-data 640：给后端服务加 www-data 组（重启后生效）
$SSH $H 'D=/etc/systemd/system/wedding-backend.service.d; [ -f $D/htpasswd.conf ] || { sudo mkdir -p $D && printf "[Service]\nSupplementaryGroups=www-data\n" | sudo tee $D/htpasswd.conf >/dev/null && sudo systemctl daemon-reload; }'
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
