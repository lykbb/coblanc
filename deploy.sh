#!/bin/zsh
# 一键重新部署到 43.142.59.166（不传 .env；要更新 .env 用：./deploy.sh --env）
set -e
export PATH=/opt/homebrew/bin:$PATH
cd "$(dirname "$0")"
KEY=~/.ssh/wedding_server.pem; H=ubuntu@43.142.59.166
SSH=(ssh -i $KEY -o IdentitiesOnly=yes)
(cd wedding-agent/web && npm run build)
rsync -az -e "${SSH[*]}" --exclude node_modules --exclude .venv --exclude runs/ \
  --exclude 'wedding-agent/storage/*/*' --exclude .DS_Store --exclude __pycache__ --exclude .env ./ $H:ai-wedding/
rsync -az --delete -e "${SSH[*]}" wedding-agent/web/dist/ $H:ai-wedding/wedding-agent/web/dist/
[[ "$1" == "--env" ]] && scp -q -i $KEY -o IdentitiesOnly=yes wedding-agent/.env $H:ai-wedding/wedding-agent/.env
$SSH $H 'chmod 600 ~/ai-wedding/wedding-agent/.env; cd ~/ai-wedding/wedding-agent && UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple ~/.local/bin/uv sync -q --python 3.11 && cd ../pi-wedding && npm ci --registry=https://registry.npmmirror.com --no-audit --no-fund -s && sudo systemctl restart wedding-backend && sleep 3 && systemctl is-active wedding-backend'
