"""渲染 nginx 配置：python3 render.py SITE_MODE SCHEME BASE 输出目录

SITE_MODE：path（默认）——图墙 /gallery/、后台 /abordadmin/ 挂在前台 server（裸 IP / 主域名）下；
           subdomain ——图墙 gallery.BASE、后台 abordadmin.BASE 各自一个 server（需要已备案域名）。
SCHEME：http 或 https（https 需先用 certbot 申请证书，--cert-name BASE）。
输出：sites/ 下是 sites-available 文件，snippets/ 下是 /etc/nginx/snippets 文件。
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
SITES = {  # 站点：(path 前缀, 前端目录, 名称, 谁能用, 上传上限)
    "gallery": ("/gallery/", "gallery", "图墙", "只认团队 IP 白名单，无登录。", "12m"),
    "admin": ("/abordadmin/", "admin", "后台管理", "团队 IP 白名单 + 账号密码登录页。", "6m"),
}
ADMIN_LOGIN = ("  error_page 401 = @admin_login;\n"
               "  location = /abordadmin/login { auth_request /_gate_team; limit_req zone=admin_login burst=6 nodelay; proxy_pass http://127.0.0.1:8000/auth/admin/login; }\n"
               "  location = /abordadmin/logout { auth_request /_gate_team; proxy_pass http://127.0.0.1:8000/auth/admin/logout; }\n")
ADMIN_NAMED = "location @admin_login { return 302 /abordadmin/login?next=$uri; }\n"
GATES = {"gallery": "team", "admin": "admin"}
LOGIN_PROXY = ("proxy_set_header Host $http_host;\nproxy_set_header X-Real-IP $remote_addr;\n"
               "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\nproxy_set_header X-Forwarded-Proto $scheme;\n"
               'add_header X-Frame-Options "DENY" always;\nadd_header X-Robots-Tag "noindex, nofollow" always;\n')
ADMIN_FILES = "  location ^~ /abordadmin/files/ { limit_req zone=admin_api burst=60 nodelay; proxy_pass http://127.0.0.1:8000/files/; }  # 任务图片\n"


def fill(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace(key, value)
    assert "__" not in text.replace("__init__", ""), "有未替换的占位符"
    return text


def render(mode: str, scheme: str, base: str) -> dict[str, str]:
    https = scheme == "https"
    common = {
        "__SCHEME__": scheme,
        "__LISTEN_DEFAULT__": "listen 443 ssl default_server;\n  http2 on;" if https else "listen 80 default_server;",
        "__LISTEN__": "listen 443 ssl;\n  http2 on;" if https else "listen 80;",
        "__SSL__": (f"ssl_certificate /etc/letsencrypt/live/{base}/fullchain.pem;\n  "
                    f"ssl_certificate_key /etc/letsencrypt/live/{base}/privkey.pem;\n  ssl_protocols TLSv1.2 TLSv1.3;") if https else "",
        "__HSTS__": 'add_header Strict-Transport-Security "max-age=31536000" always;' if https else "",
        "__HTTPS_REDIRECT__": ("server {\n  listen 80 default_server;\n  server_name _;\n  server_tokens off;\n"
                               "  location ^~ /.well-known/acme-challenge/ { root /var/www/certbot; }\n"
                               "  location / { return 301 https://$host$request_uri; }\n}\n") if https else "",
        "__BASE__": base,
    }
    out = {"sites/wedding-zones": (HERE / "wedding-zones.template").read_text(encoding="utf-8"),
           "snippets/wedding-portal-ip-check.conf": (HERE / "portal-ip-check.inc").read_text(encoding="utf-8"),
           "snippets/wedding-login-proxy.conf": LOGIN_PROXY,
           "snippets/wedding-api-errors.conf": (HERE / "api-errors.inc").read_text(encoding="utf-8")}
    guard = (HERE / "portal-guard.inc.template").read_text(encoding="utf-8")
    portals = ""
    for site, (prefix, app, label, who, body) in SITES.items():
        out[f"snippets/wedding-portal-{site}.conf"] = fill(guard, {**common, "__PREFIX__": prefix if mode == "path" else "/", "__GATE__": GATES[site]})
        if mode == "path":
            portals += fill((HERE / "portal-path.inc.template").read_text(encoding="utf-8"), {
                "__LABEL__": label, "__WHO__": who, "__PATHNAME__": prefix.rstrip("/"), "__PREFIX__": prefix, "__SITE__": site,
                "__APP__": app, "__BODY__": body, "__FILES__": ADMIN_FILES if site == "admin" else "",
                "__LOGIN__": ADMIN_LOGIN if site == "admin" else "", "__NAMED__": ADMIN_NAMED if site == "admin" else ""})
        else:
            out[f"sites/wedding-{site}"] = fill((HERE / f"wedding-{site}.conf.template").read_text(encoding="utf-8"), common)
    if mode == "path":
        out["snippets/wedding-portals.conf"] = portals
    include = ("  include /etc/nginx/snippets/wedding-portal-ip-check.conf;\n  include /etc/nginx/snippets/wedding-portals.conf;\n"
               if mode == "path" else "")
    out["sites/wedding"] = fill((HERE / "wedding.conf.template").read_text(encoding="utf-8"), {**common, "__PORTALS__": include})
    return out


if __name__ == "__main__":
    mode, scheme, base, folder = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    assert mode in ("path", "subdomain") and scheme in ("http", "https")
    for name, text in render(mode, scheme, base).items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
