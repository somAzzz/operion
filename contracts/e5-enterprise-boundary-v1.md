# E5 企业边界合同 v1

状态：技术控制已实现；企业试运行尚未签署。只有 `operion-evaluate-e5` 对真实环境证据返回 `passed` 后，才能把 E5 标记为完成。

## 身份与授权

- 企业模式只接受 OIDC 非对称签名 Bearer token；固定允许 issuer、audience 和算法，并要求 `exp`、`iat`、`sub` 及可撤销的 `sid`/`jti`。
- JWT 只证明登录，不授予 Operion 权限。tenant、单一 Company、canonical customer scope 和角色每次请求都从服务端 identity policy 解析。
- identity policy 修改后按文件版本即时重载；禁用用户、撤销 session 或提高 `valid_after` 会阻断旧 token。
- 角色仅有 `agent_read`、`followup_proposer`、`action_reader`、`action_approver` 和 `action_operator`。未知角色拒绝加载。
- 会话 owner key 包含 tenant 与稳定 user ID；跨用户/租户历史、取消和动作查询均拒绝。

## 浏览器与服务边界

可信 ingress 完成登录，将 access token 放在 `x-forwarded-access-token` 或配置的 HttpOnly cookie 中。Next.js 只在服务端读取并转发；不得创建 `NEXT_PUBLIC_*` token。企业部署必须让 Next.js 只能经 ingress 到达，否则客户端可伪造转发头。

Agent 和 Action API 都独立验证 token。Agent 按身份动态构造 customer scope 和工具集。Action API 的批准仍要求服务端 CSRF secret；通用提案和通用修订不能绕过 E4 的服务端事实解析。

## 写入发布锁

企业默认 `OPERION_WRITES_ENABLED=0`：Action API 拒绝批准，Agent 不启用跟进提案，Worker 拒绝启动。开放 E4 唯一写路径必须同时设置：

- `OPERION_WRITES_ENABLED=1`；
- 非空 `OPERION_RELEASE_ID`；
- O01–O08 与 E4 回归通过；
- 当前业务时段、值班、备份和回退已确认。

新工具和新动作类型仍默认拒绝。

## 审计、保留与监控

- Agent 访问事件追加保存并由 SQLite trigger 禁止修改/删除。
- 原始 conversation 和 tool-call 内容默认最多保留 24 小时，由 `operion-session-purge` 清空内容但保留运行元数据和访问事件。
- Action 事件仍使用逐 action 哈希链；`/api/operations` 仅 `action_operator` 可读取状态计数、最老 UNKNOWN、过期租约、暂停状态和 Worker 心跳。
- Worker 心跳包含状态、当前 action 和 release ID。UNKNOWN 超过 5 分钟、Worker 停滞、过期租约、审计异常、备份超 RPO 或磁盘不足必须由外部监控实际投递给主/备值班人。

## 完成判定

代码测试或本地故障注入不能替代企业运行证据。E5 完成必须提交严格 schema 的证据文件，证明真实身份/撤销、密钥轮换、网络隔离、告警接收、加密异机备份恢复、RPO/RTO、五并发容量、发布回退、数据删除和至少 10 个业务日的非零合法流量，并取得业务、运维、治理三方签署。
