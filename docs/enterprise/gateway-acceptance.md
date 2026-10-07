# I07 本地认证网关验收摘要

日期：2026-09-29。状态：**LOCAL_PROTOCOL_PASSED / BROWSER_NOT_RUN**。用户选择使用本地 Keycloak；本次实施与验证限于独立 loopback 部署、合成身份和公开 WWI 快照。

## 交付

- Nginx 1.30.5 HTTPS 入口、Keycloak 26.7.4、OAuth2 Proxy 7.15.4、Redis 7.4.11 服务端会话及私有 Web/Agent 服务；只有 `127.0.0.1:8443` 发布。
- OIDC code flow、PKCE S256、state/nonce、Secure/HttpOnly/SameSite cookie、服务器 token 转发和后端独立验证。
- 每请求查询当前身份策略，按页面/API 功能检查角色；移除企业模式浏览器 token cookie fallback；身份查询不授予额外业务角色。
- 同源 mutation 校验、同源 POST 注销、Redis session 删除和 Keycloak 后台注销。
- 初始化/启停脚本、可重复的协议验收脚本、健康检查与启动依赖、拒绝页面退出入口、运行手册与回归测试。

使用方式见 [认证网关运行手册](../../ops/auth-gateway.md)。入口为 `https://operion.localhost:8443`，凭据在忽略目录 `var/gateway/credentials.json`，浏览器需正确配置专用开发 CA 信任。

## 验证结果

| 检查 | 本次结果 | 范围 |
|---|---|---|
| 真实 Keycloak / HTTPS 协议验收 | 38/38 PASS | `scripts/verify-gateway.py --model`，包括实际模型请求 |
| Python 全套回归 | 169 项：146 PASS，23 SKIPPED，0 FAIL | 未配置隔离测试数据库，数据库组明确跳过 |
| Web 构建 | PASS | Docker 内 `npm run build -- --webpack`，TypeScript 检查通过 |
| Python lint / diff 格式 | PASS | 变更 Python 文件通过 Ruff；`git diff --check` 通过 |
| 实际浏览器渲染和点击 | NOT RUN | Computer Use inventory 没有浏览器或应用；HTTP/SSE 不替代此项 |
| 实际用户 E5 观察 | NOT RUN | 合成测试账号不算实际用户；没有完成 10 个业务日观察 |

协议通过项包括：匿名页面重定向/API 401、伪造认证头和 token cookie 拒绝、Host 校验、管理入口不公开、运行时端口隔离、私有 Web/Agent 的直接伪造请求拒绝、PKCE/state/nonce、callback 重放拒绝、安全 cookie、无 token 渲染、正常页面/API、跨域与缺失 Origin 拒绝、有效 IdP 用户无业务 policy 拒绝、禁用与恢复、错误功能角色、旧登录撤销、真实 Agent SSE、跨用户历史隔离、注销后的 cookie 重放拒绝及 IdP 会话终止。

本次同时修复了重启期间“网关已能登录、后端尚未就绪”的启动顺序问题，新增健康依赖后重新通过。早期失败记录保留，未以删除失败记录获得最终通过。最终报告使用更新后的 Nginx/Redis 固定版本和最终 Web/Agent 构建。

本地详细证据（不提交 Git，仓库以此脱敏摘要共享结论）：

```text
reports/enterprise/improvements/gateway/
  acceptance-final.json           最终 38 例逐项结果与时间
  manifest.json                   代码基线、变更文件哈希、镜像 ID、环境摘要
  initial.json                    早期重启干扰下的失败运行
  acceptance.json                 后端未就绪时的失败运行
  acceptance-after-readiness.json 健康依赖修复后的运行
```

没有记录或公开密码、OAuth code、token 或 session cookie。协议脚本对测试 policy 的临时修改在 finally 中恢复。没有启动 Action Worker，没有向 Twenty/ERPNext 写入业务对象；新增数据仅限该栈自己的身份库、会话历史和本地证据。

## 尚未放行的范围

- 浏览器点击与开发 CA 配置仍需实际验证；目前只证明协议和服务链路。
- I01 实时订单归属问题、I02 最终答案评分、I03 履约模式边界未在本次修复。网关不能替代业务对象授权。
- 当前单机 Keycloak 使用开发模式/H2，Redis 会话不持久化。实际部署需独立身份配置、数据库与备份、密钥/证书轮换、监控及故障演练。
- 本栈只证明新服务的网络边界，不代表宿主机既有模型、业务系统及数据库的网络隔离已经通过。
- 注销/撤销阻断后续请求；进行中的请求仍受原有超时控制，不能宣称立即撤回。仅 IdP 撤销也不能替代 Operion 服务端撤销策略。
- 本次不把 I07 标为全范围 PASSED，不放行 E5/M3、真实写入或私有业务数据。
