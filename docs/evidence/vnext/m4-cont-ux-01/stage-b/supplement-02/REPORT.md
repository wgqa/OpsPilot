# Stage B Supplement 02 — 同 Task 读响应乱序收口

**状态：** `ACCEPTANCE_CANDIDATE`（仅本定向补差；Stage B 整体仍待允许环境中的真实浏览器验收）

## 用户可见变化

Scope 撤销后，稍晚到达的旧 Inspector 或消息读取结果不能再把受限答复、来源、Receipt 或 Evidence 放回工作台。重新取得授权后，新发起的 Inspector/消息读取仍可正常展示；其它 Task 的消息不受该 Task 的失权标记影响。

## 核验基线

- Repo：`wgqa/OpsPilot`
- `origin/main` 与本轮基线：`4c891cbd5e28c8b43391ac99ca886f8c8af2ef44`
- 冻结标准提交：`7862c086ab92ff972d647c93af34c82a7ef8dbb2`
- 实现提交：`cb32e2ee995674de7f1784e784972bfe4e63c671`
- 总纲 Blob：`1f737712c7a36ceb34433ac09c3fbba3c3305542`
- AGENTS Blob：`32c45506cceeaa8c76a5c56bf8360ff476b58856`
- Skill Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`
- Stage B Gold Blob：`1290ef276690f00b6e9683f0251302f376a70098`（未修改）
- Diff 范围：`frontend/src/App.vue`、`frontend/src/conversation.ts`、`frontend/test/conversation.test.ts`，及本目录证据；不含业务 Domain、Gate、权限、预算或旧 Gold。

本轮实际重读了总纲 §0/§2/§3/§4/§6/§8、AGENTS、项目 Skill A/C、Stage B 冻结计划、SUP-01 冻结计划与报告，以及 M2-01/M2-02 的延期门禁。仓库中延期门禁实际位于 `docs/evidence/vnext/m2-01/DEFERRED_GATES.md` 与 `docs/evidence/vnext/m2-02/DEFERRED_GATES.md`；不存在 `docs/baseline/DEFERRED_GATES.md`。

## 缺陷与修复

原逻辑只比较当前 Task ID。对于同 Task 的请求 A、B，Scope 撤销后 B 可先返回并清理缓存；A 迟到时仍满足 Task ID 相同，因此其旧授权响应可覆盖 B。消息读取没有任何请求序号校验，也可能在清理之后覆盖 `messages`。

在 `conversation.ts` 增加局部 `S3ReadResponseFence`：Inspector 按 Task 递增代次；当前失权响应会使该 Task 的旧代次失效，并同步使在途 Session 消息读取失效；当前有效授权响应清除该 Task 的失权标记，同时淘汰较早的消息读取。Session 消息自身按 Session 全局代次接纳，并过滤失权期间与该 Task 关联的助手消息。`App.vue` 只在代次仍最新时接纳数据；授权判断仍由现有 Inspector/API/Domain 提供。没有新增 Domain Gate、权限服务、数据表或业务状态。

定向 RED 使用受控 Promise 按“旧授权 A 发出 → 新请求 B 表示失权并清理 → A 最后返回”的顺序执行，证明原有同 Task 检查会恢复旧 Inspector 内容；另一 RED 证明清理前发出的 Session 消息可在清理后恢复受限助手正文。两项均在补丁前失败，见 `runs/red-race-02/node-test.log`。测试也逐项包含受限答案、来源、Receipt、Evidence ID，覆盖撤权过滤保留用户锚点及其他 Task 消息，并验证重新授权后新读取可通过。

## 测试证据

最终新鲜运行：

- `node --experimental-strip-types --test test/conversation.test.ts`（工作目录 `frontend/`）：11 passed，0 failed。
- `npm run typecheck`：exit 0。
- `npm run build`：exit 0。
- `npx eslint src/App.vue src/conversation.ts test/conversation.test.ts`：exit 0。
- `git diff --cached --check`：实现提交前通过；最终证据提交前会再次核对。

命令原始输出、退出码与 Node/npm 版本保存在 `runs/green-race-04/`。RED、测试准备问题、两个中间测试/ lint 失败和修正记录保存在 `FAILURES.md` 及对应 `runs/`，没有覆盖旧 Stage B 证据。

本轮不改后端，未重跑此前 SUP-01 的 402 项通过结果。此前全量长路径运行的 20 项 Windows checkpoint 路径错误、短路径 402 项通过、旧 C1 废弃 Intent RED 的记录仍原样位于 Supplement 01；本轮均未复写或重新解释。真实浏览器/DOM/SSE、Computer Use 和 Provider 均为 `NOT_RUN`，不以纯前端单测替代浏览器验收。

## Skill 收尾核验（实施方，不代替主 Agent 裁决）

1. **用户变化：** 修复失权后的旧异步读响应回填风险，没有增加新的用户业务能力。
2. **Agent 决策：** 无 Agent 自主决策变化；受信程序仍决定是否允许读取。
3. **观察驱动：** 同 Task 的旧授权响应与新失权响应得到不同接纳结果；重新授权后的新响应仍可接纳。
4. **新增约束：** 仅拒绝已过时代次或失权期间的读取；正向测试保留同 Task 合法读取、重授权和其它 Task 消息。
5. **简化结果：** 复用现有 App 缓存清理和 Domain 当前权限语义，只加 UI 读取代次；没有改变 Gate 或历史消息生命周期。
6. **证据与停止线：** 两个有效 RED、11/11 定向 GREEN、类型检查/构建/Lint 通过；浏览器和 Provider 未运行。停止于本补差并交主 Agent 独立核验。

**实施方状态：** `ACCEPTANCE_CANDIDATE`。不签署 Stage B PASS；不启动 J1–J4、M5 或相邻业务切片。
