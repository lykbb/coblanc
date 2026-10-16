# auth_request 子请求：问后端来源 IP 是否在内部站点白名单（204 放行 / 403 拒绝）
location = /_portal_ip_check {
  internal;
  proxy_pass http://127.0.0.1:8000/internal/portal-ip-check;
  proxy_pass_request_body off;
  proxy_set_header Content-Length "";
  proxy_set_header X-Original-IP $remote_addr;
}
