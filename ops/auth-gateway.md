# 本地认证网关运行手册

日期：2026-09-29。范围：I07 本地 Keycloak、公开 WWI 快照、只读 Agent。此部署供开发和协议验收使用，不开放真实写入，不替代 E5 实际用户观察。

## 1. 结构与信任边界

```text
浏览器 → HTTPS Nginx :8443 → OAuth2 Proxy → Next.js → Agent API
              ↓                 ↓                        ↓
          Keycloak          Redis 会话             OIDC + 服务端 policy
                                                        ↓
                                              scoped tools / WWI snapshot
```

- 登录采用 OIDC Authorization Code + PKCE S256、state 和 nonce。Keycloak 26.7.4、OAuth2 Proxy 7.15.4 的镜像标签固定在 Compose 中。
- 浏览器只持有 `__Host-operion_session` 票据，Secure、HttpOnly、SameSite=Lax、Path=/，不保存 OAuth access/refresh token。会话内容保存在私有 Redis。
- Nginx 清除外部认证/转发头，OAuth2 Proxy 根据已验证会话注入 `x-forwarded-access-token`。Next.js 不接受浏览器 token cookie 或企业模式静态服务 token。
- Next.js 通过 Agent 的 `/api/identity` 在每次请求重新检查签名、用户是否有效和当前服务端角色；页面、API 和静态资源均位于登录边界后。Agent API 和 Action API 继续独立验签及检查操作权限。
- `/api/identity` 只返回当前用户、租户、公司和角色，不返回 token 或 session ID；身份查询不会赋予 `agent_read`。对话需要 `agent_read`，动作页需要 action 类角色，具体批准仍由 Action API 控制。
- 非只读浏览器请求必须带精确匹配的 Origin。`/oauth2/sign_out` 仅允许同源 POST，不能由 GET 或外部站点触发；它删除 Redis 会话并对 Keycloak 执行后台注销，之后跳到固定 `/signed-out`。
- 只有 Nginx 发布到 `127.0.0.1:8443`；Web、Agent、Keycloak、Redis 没有主机端口。Keycloak 管理路径不公开。Agent 通过固定 model relay 使用已有本地 SGLang，无业务写凭据及 Worker。
- 网关不修复实时业务关联。I01 的订单归属授权问题仍需独立解决；本栈固定使用公开快照。

配置与源码：[Compose](../deploy/gateway/compose.yaml)、[OAuth2 Proxy](../deploy/gateway/oauth2-proxy.cfg)、[Nginx](../deploy/gateway/nginx.conf)、[Web 入口校验](../apps/web/proxy.ts)、[后端身份校验](../src/operion_etl/enterprise_auth.py)。

## 2. 初始化与启动

前置条件：Docker Compose、项目 Python 环境和空闲的 8443 端口。真实 Agent 查询还需要现有 SGLang 在宿主机 30000 端口提供 `qwen3.8-27b`；登录和身份 API 本身不需要模型。

在仓库根目录执行：

```bash
.venv/bin/python scripts/gateway.py init
.venv/bin/python scripts/gateway.py up
.venv/bin/python scripts/gateway.py status
```

`init` 生成独立本地 CA/站点证书、随机密码、OIDC client secret、cookie secret、Keycloak realm 和 scope policy，保存到忽略目录 `var/gateway/`。该目录权限为 0700，凭据文件为 0600；仅 Keycloak 的导入文件和公开证书需要在容器挂载中可读。已有目录会拒绝覆盖，不能把重新初始化当作无损密码轮换。

入口：`https://operion.localhost:8443`。

本地证书由生成的 CA 签名，有效期 30 天；不会自动修改操作系统或浏览器信任库。浏览器使用前由操作者把 `var/gateway/tls/ca.crt` 作为专用开发 CA 加入对应测试浏览器的信任配置。不要关闭 TLS 校验或把浏览器警告绕过算作验收。证书到期需受控更新证书及信任，当前脚本不自动轮换。

若本机不能解析 `.localhost`，在本地测试环境为 `operion.localhost` 配置 `127.0.0.1`。协议验证脚本只对自己的进程覆盖该域名解析，并始终验证证书和主机名；无需修改系统 DNS。

生成的演示账号：

| 用户 | 允许范围 | 用途 |
|---|---|---|
| alice | 客户 65、供应商 7；`agent_read` | 正常只读路径 |
| bob | 客户 60，无供应商；`agent_read` | 跨用户与范围隔离 |
| unassigned | 无 Operion policy | 有效 IdP 登录不能自动获得业务访问 |

密码在 `var/gateway/credentials.json`，不写入终端日志、文档或报告。这些都是合成测试账号，不计为 E5 的实际试运行用户。Keycloak 不开放自助注册、密码授权或服务账号授权。

启动完成后可进行健康检查：

```bash
curl --noproxy '*' --resolve operion.localhost:8443:127.0.0.1 \
  --cacert var/gateway/tls/ca.crt -o /dev/null -s -w '%{http_code}\n' \
  https://operion.localhost:8443/api/conversations
# 未登录预期 401；网页 / 预期 302 到登录入口。
```

`up` 返回说明容器已创建，不代表 OIDC 已就绪；Keycloak 冷启动期间代理可能重启，验收脚本会等待入口就绪。停止仅影响本项目新建的 stack：

```bash
.venv/bin/python scripts/gateway.py stop
```

不会停止既有 Twenty、ERPNext、数据库或模型容器；`stop` 不删除身份数据库和会话历史。Redis 不持久化，会话存储容器重启后需重新登录。

## 3. 权限、撤销和退出

修改 `var/gateway/policy/identity-policy.json` 后无需重启服务；推荐在同一目录写临时文件再原子替换，保留 0600 权限。Compose 挂载整个 policy 目录，原子替换后的文件也能被服务读取。

- `active=false`：阻止该用户后续页面/API 请求。
- `valid_after`：阻止签发时间早于指定 Unix 时间的 token。
- `revoked_sessions`：按 token 的 `sid`/`jti` 阻断指定会话。
- `customer_ids`、`supplier_ids`、`roles`：业务权限来自服务器文件，不信任浏览器、模型或 JWT 自报的业务角色。

服务端 policy 在每次请求重新解析；已开始的请求不会因注销被自动撤回，长请求仍受现有运行超时限制。Keycloak access token 有效期为 5 分钟，代理每分钟尝试刷新会话；仅 IdP 端撤销不等于所有已签发 JWT 立即失效。需要立即阻断后续 Operion 请求时同时使用服务端撤销策略。

在网页右下角进入 **Session / sign out**，然后提交 Sign out。无业务权限的登录用户也可以从拒绝页面退出。复制注销前的 cookie 不能恢复被删除的 Redis 会话。浏览器自动填充密码或 IdP 重新登录不等于旧会话仍然有效。

## 4. 可复现验收

仅对本地合成账号执行；脚本会临时修改 Alice 的 policy、创建演示对话，并在 finally 中恢复原 policy。不要对实际使用中的 policy 并发运行；不要将此脚本直接指向真实身份环境。

```bash
.venv/bin/python scripts/verify-gateway.py --model \
  --output reports/enterprise/improvements/gateway/protocol.json

env -u OPERION_TEST_ACTION_DATABASE_URL \
  PYDANTIC_AI_NO_BANNER=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -q
```

不带 `--model` 时不调用模型，不测试跨用户 Agent 对话。脚本验证 TLS、真实登录、PKCE/state/nonce、匿名 API、伪造头/旧 token cookie、角色、撤销、CSRF、运行时端口发布、注销与 cookie 重放等；报告不保存密码、OAuth code、token 或 cookie。模型模式增加完整 SSE 调用和跨用户历史隔离，不能把它当作回答事实准确率评测。

网关日志只保存请求方法、路由类别、状态与耗时。Nginx 原始错误日志和 OAuth2 Proxy 原始诊断日志关闭，因为失败信息可能带 callback URL 或 token。排障首先查看容器状态、无敏感内容的网关状态码及 discovery 健康检查；不要在共享终端开启原始请求/认证日志。

实际浏览器点击仍应另验：信任正确 CA → 登录 → 正常对话 → 页面刷新 → 换账号 → 退出 → 后退/重放 → 无权限账号退出。没有可用浏览器时标记 NOT RUN，协议测试不能代替页面渲染和交互验收。

当前脱敏验收摘要见 [I07 本地网关结果](../docs/enterprise/gateway-acceptance.md)。

## 5. 迁移到实际身份环境

本地 `start-dev` / H2 Keycloak、生成账号、本地 CA、单实例 Redis 不作为生产配置。实际部署前：

1. 固定实际 HTTPS 域名、证书链和 IdP issuer；同步修改代理 redirect URL、Keycloak client、Nginx Host/Origin、Next.js public origin、Python issuer/audience/JWKS。不得保留宽泛 callback 通配符。
2. 使用实际用户 subject 和最小范围的 policy，安全注入/轮换 client 与 cookie secrets。切换主体与密钥后重验旧 token、旧 session 和权限撤销。
3. 使用适合实际环境的 IdP 数据库、备份、会话存储和故障策略；以 digest 固定发布镜像并记录代码/配置版本。
4. 在实际网络验证不能绕过入口；现有宿主机业务系统和模型的旧端口不由本栈自动整改，不能把本栈内部隔离外推为整台主机的 E5 隔离通过。
5. 重跑协议、浏览器和对应 O01/O02 检查，再按 E5 要求进入一名实际用户的只读观察。真实动作仍需独立审批与专项验收。

实现参考：[OAuth2 Proxy 配置](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/)、[服务端会话存储](https://oauth2-proxy.github.io/oauth2-proxy/configuration/session_storage/)、[Keycloak 容器](https://www.keycloak.org/server/containers)、[Keycloak 反向代理](https://www.keycloak.org/server/reverseproxy)。
