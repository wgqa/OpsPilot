# 失败、限制与未完成事项

## A1 — TestClient shutdown

- 目标用例：`tests/test_ar03_material_remainder_01.py::test_remainder_repeated_same_tool_can_cross_old_ten_mcp_limit_in_formal_worker`，单测通过，1/1，退出码 0，5.65 秒。
- 同一用例在本轮全量 pytest 顺序中也通过（约 28%）；全量进程随后继续执行至最后一个测试并正常退出，未复现 `TestClient.wait_shutdown` 停滞，也未触发 faulthandler。
- 历史 R1 证据把停滞定位到 TestClient 退出开始 ASGI lifespan shutdown 时，dispatch 已达业务终态但 Worker/MCP 清理尚未完全返回。当前测试在退出 TestClient 前等待 dispatch 完成与 Worker idle，避免测试自身提前关闭生命周期。
- 本轮没有改生产 Worker、MCP 或 lifespan。当前证据证明本轮目标路径能结束，不证明所有 Worker 取消、MCP 子进程和测试序列都不存在 shutdown 竞态；由于本轮没有再次停滞，没有可提供的新线程栈。

## A2 — AR-03 Runner Git 预检（RED → GREEN）

- RED：`logs/ar03-runner-preflight-red.txt`。pytest `--basetemp` 位于仓库外时，Runner 从临时 `ROOT` 调用 Git 得到 `GIT_PREFLIGHT_FAILED:rev-parse HEAD`，而预期是 `MATERIAL_LIVE_BRANCH_MISMATCH`。原夹具没有为 Runner root 建立 Git checkout，结果会受 pytest 临时目录是否位于父仓库内影响。
- 修复：仅改 `tests/test_ar03_material_live_exec_prep.py`，在 `tmp_path` 建立真实临时 Git repo，提交 fixture 文件并切到 `codex/unapproved-branch`；不再伪造 `_git` 返回值。
- GREEN：`logs/ar03-runner-preflight-green.txt`，外部 basetemp 下 1/1 通过。合法/非法分支检查仍调用真实 Git；生产 Runner 校验未放宽。相关 Runner Recovery 02 定向组 13/13 通过；本轮全量序列中的该目标也通过。

## 全量 pytest — 未通过，需主 Agent 裁决

单次受控全量运行于 2026-11-06 正常退出，741 项，**701 passed / 40 failed**，16 分 49 秒，退出码 1。原始输出见 `logs/full-pytest.txt`，命令与环境见 `RUN_METADATA.json`。没有进行第二次全量运行。

失败分组：

1. **AR-04C 实验授权/Claim：12 项。** 相关用例将付费实验 authorization 与固定 execution HEAD / claim 绑定；当前验收分支不是该已消费实验的授权 HEAD，故模型构造或 Claim 入口以 `AR04C_ONE_SHOT_AUTHORIZATION_INVALID` 拒绝。一个并发 Claim 测试两边都 LOST，同样未进入有效授权竞争。另两个回归断言共享父目录的 `.runtime/ar04c-real-journey-01/claim.json` 不存在，但运行时观察到该路径存在。测试本轮没有创建、读取内容、消费或修改该 Claim；它留在原处。实验身份、授权与运行时路径都不应为通过全量测试而放宽。
2. **D4 恢复：24 项。** `tests/test_d4_recovery.py::_ready()` 直接准备旧式 READY/Approval，未为当前 Run 建立本卡及 HF01 合同要求的有效 D3 revalidation receipt / trusted executor 上下文。动作入口在 `get_or_create_action_intent()` 或 Graph 的 revalidation 节点以 `REVALIDATION_REQUIRED` / 缺少可信 executor、Run、loopback API 拒绝。失败发生在拟测试的恢复/动作路径建立之前，因此不能据此断言旧 Intent、Crash replay 或已提交回执恢复本身正确或错误；这些场景在现行复核合同下仍未验证。
3. **M1/M4 的 3 项动作/进程用例。** 与 D4 一样，错误在当前 revalidation 前置条件处出现。它们需要按有效的 RevalidationReceipt 更新隔离夹具后重新验证；本轮不重写它们或改变生产门禁。
4. **历史 C1 RED：1 项。** `test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix` 仍要求废弃的 `READONLY_FOLLOWUP` Intent，返回 `INVALID_MODEL_CLASSIFICATION`。当前合同是 `FOLLOW_UP + readonly_action=INVESTIGATE`；对应当前正例 `test_follow_up_request_for_bound_protocol_is_routed_to_same_task_readonly_investigation`、`test_follow_up_investigation_uses_real_mcp_and_persists_a_readonly_result` 均通过。本轮没有恢复旧生产兼容分支，也没有改写旧 RED。

### 其他验证限制

- `npm ci --offline` 因本机缓存缺少 `yocto-queue@0.1.0` 失败；未联网安装。复用了原工作区内与锁文件版本一致的 Node 依赖临时 Junction，构建后已移除 Junction。
- 直接 `node --test` 在当前 Node 24 strip-only 模式下不支持 TypeScript parameter properties；使用 `node --experimental-transform-types --test test/*.test.ts` 后为 27 passed、1 skipped、0 failed。
- 前端 ESLint 有 2 个错误，均在未改动的 `frontend/e2e/m4-03-s3-journey.mjs`：第 1 行 `access` 未使用，第 56 行 `setTimeout` 未定义。Typecheck 与 production build 通过。

## 未运行 / 未授权

- Browser / Playwright / Computer Use：`NOT_RUN`，既有 STOP 未解除。
- 真实 Provider 请求：0。
- 生产或外部业务写入：0。
- main 合并：未执行。
