# auth_request 子请求（app/login.py /internal/gate/<名>）：204 放行 / 401 去登录页 / 403 拒绝。
# team：只看来源 IP 白名单（图墙、后台登录页）；admin：IP 白名单 + 后台登录会话。
# X-Original-URI/Host：后端据此记页面访问（同人同站 30 分钟一次）和被拒的访问（写审计）。
location = /_gate_team {
  internal;
  proxy_pass http://127.0.0.1:8000/internal/gate/team;
  proxy_pass_request_body off;
  proxy_set_header Content-Length "";
  proxy_set_header X-Original-IP $remote_addr;
  proxy_set_header X-Original-URI $request_uri;
  proxy_set_header X-Original-Host $host;
}
location = /_gate_admin {
  internal;
  proxy_pass http://127.0.0.1:8000/internal/gate/admin;
  proxy_pass_request_body off;
  proxy_set_header Content-Length "";
  proxy_set_header X-Original-IP $remote_addr;
  proxy_set_header X-Original-URI $request_uri;
  proxy_set_header X-Original-Host $host;
}
