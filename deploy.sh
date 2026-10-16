#!/bin/zsh
# 一键重新部署到 43.142.59.166（不传 .env；要更新 .env 用：./deploy.sh --env）
set -e
export PATH=/opt/homebrew/bin:$PATH
cd "$(dirname "$0")"
KEY=~/.ssh/wedding_server.pem; H=ubuntu@43.142.59.166
SSH=(ssh -i $KEY -o IdentitiesOnly=yes)
(cd wedding-agent/web && npm run build)
rsync -az -e "${SSH[*]}" --exclude node_modules --exclude .venv --exclude runs/ \
  --exclude 'wedding-agent/storage/*/*' --exclude .DS_Store --exclude __pycache__ --exclude .env --exclude "ubuntu@*" ./ ${H}:ai-wedding/
rsync -az --delete -e "${SSH[*]}" wedding-agent/web/dist/ ${H}:ai-wedding/wedding-agent/web/dist/
[[ "$1" == "--env" ]] && scp -q -i $KEY -o IdentitiesOnly=yes wedding-agent/.env ${H}:ai-wedding/wedding-agent/.env
# 摄影师/生图的 Pi 运行时直接跑 TypeScript，需要 Node ≥ 23.6；服务器自带 Node 22 不行，缺了就装 Node 24 到 ~/.local/node24
$SSH $H 'V=v24.16.0; N=~/.local/node24/bin/node; if ! [ -x $N ] || [ "$($N -p "process.versions.node.split(\".\")[0]")" -lt 24 ]; then echo "安装 Node $V 到 ~/.local/node24"; cd /tmp && curl -sfLO https://registry.npmmirror.com/-/binary/node/$V/node-$V-linux-x64.tar.xz && mkdir -p ~/.local/node24 && tar -xJf node-$V-linux-x64.tar.xz -C ~/.local/node24 --strip-components=1 && rm -f node-$V-linux-x64.tar.xz; fi; $N -v'
$SSH $H 'export PATH=$HOME/.local/node24/bin:$PATH; chmod 600 ~/ai-wedding/wedding-agent/.env; cd ~/ai-wedding/wedding-agent && UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple ~/.local/bin/uv sync -q --frozen --python 3.11 && cd ../pi-wedding && npm ci --registry=https://registry.npmmirror.com --no-audit --no-fund -s && sudo systemctl restart wedding-backend && sleep 3 && systemctl is-active wedding-backend'
