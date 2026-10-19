# 接口（/api/、<站点前缀>api/）被 auth_request 拦下时返回 JSON，不跳登录页：前端（web/src/http.js）收到 401 统一刷新页面，
# 页面请求再由 nginx 转到登录页；403 = 来源 IP 不在团队白名单。错误码见 wedding-agent/docs/小囍接口约定.md。
location @api_401 { default_type application/json; add_header Cache-Control "no-store" always; return 401 '{"error":{"code":"LOGIN_REQUIRED","message":"请先登录"}}'; }
location @api_403 { default_type application/json; add_header Cache-Control "no-store" always; return 403 '{"error":{"code":"IP_NOT_ALLOWED","message":"这个网络不在团队白名单里"}}'; }
