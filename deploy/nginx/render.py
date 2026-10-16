"""渲染 nginx 配置：python3 render.py BASE http|https 输出目录

BASE：现在 43.142.59.166.nip.io（通配 DNS 指向服务器），以后换真实域名。三个站点：
  前台      默认站点（http 时用裸 IP 访问；https 时 https://BASE）
  图墙      gallery.BASE
  后台管理  abordadmin.BASE
https 需要先用 certbot 给这三个名字申请一张证书（--cert-name BASE），见 deploy.sh --nginx --https。
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent


def render(base: str, mode: str) -> dict[str, str]:
    https = mode == "https"
    ssl = (f"ssl_certificate /etc/letsencrypt/live/{base}/fullchain.pem;\n  "
           f"ssl_certificate_key /etc/letsencrypt/live/{base}/privkey.pem;\n  ssl_protocols TLSv1.2 TLSv1.3;") if https else ""
    values = {
        "__SCHEME__": "https" if https else "http",
        "__LISTEN_DEFAULT__": "listen 443 ssl default_server;\n  http2 on;" if https else "listen 80 default_server;",
        "__LISTEN__": "listen 443 ssl;\n  http2 on;" if https else "listen 80;",
        "__SSL__": ssl,
        "__HSTS__": 'add_header Strict-Transport-Security "max-age=31536000" always;' if https else "",
        "__HTTPS_REDIRECT__": ("server {\n  listen 80 default_server;\n  server_name _;\n  server_tokens off;\n"
                               "  location ^~ /.well-known/acme-challenge/ { root /var/www/certbot; }\n"
                               "  location / { return 301 https://$host$request_uri; }\n}\n") if https else "",
    }
    out = {}
    for src, dest in (("wedding.conf.template", "wedding"), ("wedding-gallery.conf.template", "wedding-gallery"),
                      ("wedding-admin.conf.template", "wedding-admin"), ("portal-common.inc.template", "wedding-portal.conf")):
        text = (HERE / src).read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace(key, value)
        out[dest] = text.replace("__BASE__", base)
        assert "__" not in out[dest].replace("__init__", ""), f"{dest} 有未替换的占位符"
    out["wedding-allow-ips.conf"] = (HERE / "allow-ips.conf").read_text(encoding="utf-8")
    return out


if __name__ == "__main__":
    base, mode, folder = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in render(base, mode).items():
        (folder / name).write_text(text, encoding="utf-8")
