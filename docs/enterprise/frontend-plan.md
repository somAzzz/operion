# Operion 前端方案：assistant-ui + AG-UI

版本：v1.3；日期：2026-09-20；状态：E2–E4 前端闭环与 E5 企业令牌转发已实现；实际 IdP/ingress 待接入。

## 1. 技术决策与范围

Operion 正式前端采用 **assistant-ui + shadcn/ui**，从 assistant-ui 官方 `with-ag-ui` 模板起步，不 fork 完整聊天平台。前端通过 AG-UI 连接 FastAPI / Pydantic AI Agent，通过普通的经认证 REST API 读取和审批动作。两条通道可以出现在同一产品界面，但不得共享授权事实：

```text
Operion Web UI（assistant-ui + shadcn/ui）
        │
        ├─ AG-UI / SSE ──→ FastAPI / Pydantic AI Agent ──→ 只读工具、propose_*
        │                    对话、流式文本、工具结果展示
        │
        └─ REST ─────────→ Action Service / PostgreSQL ──→ 写 Worker
                             提案、修订、审批、状态、事件
```

首版只交付三个产品页面：

| 路由 | 目的 | 首版内容 |
|---|---|---|
| `/chat` | 客户概览与履约对话 | assistant-ui 线程、流式回答、来源、缺失项、业务结果卡片 |
| `/approvals` | 审查待办动作 | 待审批列表、可信预览、批准/拒绝、过期与冲突提示 |
| `/actions`、`/actions/:id` | 跟踪执行事实 | 状态、事件时间线、目标系统回读、人工处理提示 |

Pydantic AI `Agent.to_web()` 只用于开发期快速验证工具输出、流式和模型兼容性，不作为正式用户界面或授权边界。首版不同时引入 CopilotKit、Chainlit、Appsmith 或另一套聊天状态框架；出现明确且经验证的能力缺口后再单独评审。

## 2. 权威状态与信任边界

- 浏览器不直连 SGLang，不持有业务系统写凭据，也不能调用任意 HTTP、GraphQL、SQL 或 Shell。
- 身份、租户、经营主体和权限范围来自服务端已验证会话。浏览器传入的角色、`approved_by`、会话归属或权限声明一律不作为授权依据。
- AG-UI 输入中的消息、工具结果、状态和历史均视为客户端可控。服务端按会话标识加载或核对其持久化历史，不因客户端重放 tool call、批准文本或旧消息而获得权限。
- 前端工具只允许导航、复制、折叠和展示等无业务副作用操作。业务读取和 `propose_*` 在服务端执行；真实写入只由已批准动作的确定性 Worker 执行。
- assistant-ui/AG-UI 的 interrupt 或 resume 能力可以改善交互，但不能替代动作表、不可变修订和批准表。正式审批只提交 `action_id + revision + decision`，执行参数从服务端提案读取。
- Action Service 是 `PENDING_APPROVAL`、`APPROVED`、`EXECUTING`、`SUCCEEDED`、`CONFLICT`、`UNKNOWN/RECONCILING` 等状态的唯一权威。聊天文案和本地 UI 状态不能宣告动作成功。
- 正式运行默认不依赖第三方托管的对话存储。若以后启用 Assistant Cloud 或其他外部持久化/遥测，须先完成数据位置、访问、保留和删除评审。

Cookie 会话必须实施 CSRF 防护；跨标签页、刷新和重新登录后都重新从服务端读取动作状态。前端只能缓存可重新获取的展示数据，不缓存执行资格。

## 3. 前端组件与结果表达

基于 assistant-ui 的 Thread、Composer 和消息部件增加以下 Operion 业务组件：

| 组件 | 展示内容 | 禁止行为 |
|---|---|---|
| `CustomerOverviewCard` | 客户身份、来源系统、记录链接、时间和缺失项 | 根据同名自动合并客户 |
| `FulfillmentResultCard` | 规则版本、数量/单位、仓库、检查时间和信息不足原因 | 将规则检查表述为交付承诺 |
| `ActionProposalCard` | `action_id`、修订、目标、具体参数、副作用、有效期 | 在浏览器重建或修改待执行 payload |
| `ActionStatusCard` | 当前状态、尝试/回读摘要、目标链接和下一步 | 将超时或未知状态显示为失败/成功 |

`ActionProposalCard` 可以提供“前往审批”入口；批准/拒绝操作在 `/approvals` 的服务端预览上完成。移动端必须能够完整阅读动作目标、修订、截止时间和副作用，不能把关键内容隐藏在 hover 中。

默认不向普通用户展示模型 thinking。工具运行过程只显示经过脱敏的步骤和可理解状态；认证头、内部提示词、原始异常、敏感客户字段和执行凭据不得进入浏览器日志或错误界面。

## 4. 接口边界

### AG-UI 对话通道

- 规划端点：`POST /api/agent`，由 FastAPI 的 Pydantic AI AG-UI 适配层返回事件流。
- 服务端在运行前解析真实用户、租户、会话和允许工具；不能照单采用请求体中的身份或完整历史。
- 必须验证流式文本、工具调用/结果、取消、超时、断线清理、上游错误和服务端限额。
- 刷新后的线程恢复以 Operion 服务端持久化消息为准。assistant-ui 的本地/客户端历史适配只负责呈现，不成为可信历史库。

### 动作 REST 通道

首版接口合同至少覆盖：

```text
GET  /api/actions?status=PENDING_APPROVAL
GET  /api/actions/{action_id}
POST /api/actions/{action_id}/decisions
GET  /api/actions/{action_id}/events
```

批准请求只携带服务端动作引用、修订和决定；拒绝原因可作为说明，但不能携带替换后的执行参数。重复点击和 HTTP 重试使用请求幂等键；旧修订、过期动作、跨用户/租户访问和伪造身份都必须由服务端拒绝。API 的最终 schema、错误合同和状态迁移以 E3 动作控制方案为准。

## 5. 分阶段实施

| 阶段 | 前端工作 | 放行结果 |
|---|---|---|
| E2 | 可选用 `to_web()` 做本地诊断；从官方 `with-ag-ui` 模板建立 Web 应用；接入服务端身份、AG-UI、可信会话历史和两类只读结果卡片 | `/chat` 能重复完成只读场景；刷新、取消和错误降级可验证 |
| E3 | 以测试桩/固定数据开发 `/approvals`、`/actions` 和动作 REST 客户端；覆盖过期、冲突、未知与人工处理状态 | 已通过 production build、REST 联调和服务端授权测试 |
| E4 | 接入 `ActionProposalCard`、真实提案和受控任务执行；复验批准内容、幂等和回读 | 已通过；用户可进入独立审批页并从成功动作打开 Twenty Task |
| E5 | 完成企业登录、会话撤销、CSRF、数据保留、可访问性、响应式布局、观测和发布锁定 | 服务端 OIDC/范围/撤销和令牌转发已实现；实际 IdP、ingress、告警和 10 日观察待真实环境验收 |

计划代码位置为独立 Web 应用（优先 `apps/web/`）；实际创建时记录选定框架和目录决策。使用官方脚手架后立即固定 JavaScript 包版本与 lockfile，并把 assistant-ui、AG-UI 客户端和 Pydantic AI 服务端作为一个兼容组合测试。脚手架命令只用于创建初始代码，不作为可重复生产部署方法。

审批页和动作页可以在 E3 使用测试桩先行，不必等待模型效果；正式动作接线仍受 E4 放行门槛限制。

## 6. 验收清单

### 对话与读取

- 流式回答、取消、超时和断线后资源释放正确，失败不会被展示为成功。
- 刷新或重新登录后，只恢复当前用户/租户有权看到的服务端会话；伪造会话 ID 和 tool-call 历史失败。
- 客户与履约卡片显示来源、业务时间/抓取时间、规则版本、缺失项及模拟标记。
- 上游不可用、同名客户和过期数据分别显示服务异常、需要澄清和信息不足。
- 键盘可完成发送、停止、打开详情和审批导航；状态不只依赖颜色表达。

### 审批与动作

- 刷新、关闭聊天或换设备不改变待审批动作，Action Service 仍可查询。
- 旧修订、过期批准、跨用户重放、客户端换参和缺少 CSRF 令牌均无写入。
- 重复点击批准或请求重试不会生成第二个执行资格或第二个业务副作用。
- `UNKNOWN/RECONCILING` 明确提示等待对账或人工处理，不提供“重新创建”捷径。
- UI 展示的目标、参数、副作用、修订和执行器实际使用内容可由摘要与审计证据对应。

这些 UI 用例不替代 E2 的 C/F/P/A 业务案例和 E3/E4 的 W01–W15 服务端安全测试；两类证据必须同时通过。

## 7. 非目标与变更规则

首版不建设通用 Agent 平台、多 Agent 编排器、可视化流程编辑器、插件市场或多渠道客服系统，也不把 assistant-ui 组件扩展为业务授权层。新页面、新前端业务工具、Assistant Cloud、第二套对话框架或让浏览器直连模型均属于架构变更，必须说明业务价值、数据边界和验收用例后再纳入计划。

## 8. 官方参考

- [assistant-ui AG-UI Quickstart](https://www.assistant-ui.com/docs/runtimes/ag-ui/quickstart)
- [assistant-ui AG-UI Overview](https://www.assistant-ui.com/docs/runtimes/ag-ui/overview)
- [assistant-ui AG-UI Runtime Options](https://www.assistant-ui.com/docs/runtimes/ag-ui/runtime-options)
- [Pydantic AI AG-UI integration](https://pydantic.dev/docs/ai/integrations/ui/ag-ui/)
- [Pydantic AI Web UI](https://pydantic.dev/docs/ai/guides/web/)
- [shadcn/ui documentation](https://ui.shadcn.com/docs)
