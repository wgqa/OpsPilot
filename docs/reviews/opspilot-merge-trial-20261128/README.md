# OpsPilot 分支试合记录

状态为 ACCEPTANCE_CANDIDATE。验证范围为隔离试合与离线定向回归，发布仍待独立验收。

## 基线与范围

- GitHub 上核实 140 条分支及其提交。31 条其他分支的提交已经是 main 祖先。按祖先关系去重后有 11 个互不包含的分支顶端。
- 远端 main 为 60eee87bfe3cca522011316cb4cd2c0064ad291b。本地旧 main 落后 232 个提交，试合从远端提交出发。
- P0 单独试合为 c2afb195e54be7640844056df580730fff4131c8，树与 P0-02-Bridge dbe1e0d29892c479af82ce3385c2ed9c209ca969 完全一致。
- 组合试合的父提交为 P0-02-Bridge dbe1e0d29892c479af82ce3385c2ed9c209ca969 和 AR-05 release-regression-boundary 91c6564129dfa2f3cf568b34ef9844a9c5c31bcb。后者包含当前 D3 复核与恢复测试，AR-05 早期预检分支属于其祖先。
- 总纲 e36f2f75509738551ac6d4a2de5b4f9cf44a7991、AGENTS f174a6ab7f23f9e6d8b3ef98d455b99a75193143、评审 Skill d405c8d413d633824b279202cc1503dab4cf0b03 在两个父提交的 Blob 一致。
- AR-04A/B Gold 为 6c8ba3867e2dad983abe6f1b85bd559fc28e36ac / f5056cbb3344208e2e34671ea08a50963d3aea3d。适用既有 v1.0 D3/D4、M2-01/02 遗留门禁及 AR-05 冻结旅程。已有 Gold、RED、Trace 和失败记录保留。

## 合并冲突与验证

- frontend/src/App.vue 同时保留 AR-05 同会话专业助手路由与 P0 条件审核。条件卡和正式更正使用只能定位当前 S3 的 assistantTaskId。S1 普通对话仍留在原 Session。
- opspilot/assistant.py 同时保留 P0 条件预算与限制提示、AR-05 实验 Memory 开关和来源当前性投影。预算使用与出站序列化一致的来源投影。
- P0 单独试合 pytest **99/99**，Vue typecheck/build 通过。
- 组合试合 P0、F01、撤权与压缩取消 **19/19**。24 轮离线旅程的后续 SDK 输入保留四条确认要求，同时覆盖跨任务排除、替换、撤回和公共背景。
- 组合试合 S1/S2、D3/D4、事件与纠错回归 **66/66**。覆盖同会话进入调查、真实本地只读 MCP 与 HTTP、有效复核下的恢复、旧授权失效和幂等重放。
- 组合试合 Vue typecheck/build 通过。用此次离线运行记录再次执行前端投影测试 **5/5**。其中 S1 投影的后端夹具单独复跑 **1/1**，与 66 项有重叠。
- 精确 main 代码创建 v18 临时数据库。组合试合代码连续初始化两次，原数据保留，v19 同时具备条件审核字段和 D3 复核回执表。
- 使用仓库现有锁定环境，Python lock Blob de16e1113ac250511cee8d7b6a079b88b1ca4f99，前端 lock Blob 88431e5822d130e873b478da59b062eb155bfebd。后端使用隔离临时路径、禁用追踪并清空外部提供商凭据。

## 复现入口

~~~text
python -m pytest -q tests/test_p0_02_bridge.py tests/test_p0_02_task_conditions.py tests/test_p0_01_task_context.py tests/test_ar04c_f01_context_currentness.py tests/test_ar04a_compression_cancel_hf_01.py::test_cancelled_compression_is_not_resent_on_recovery tests/test_m4_03_hf_02.py::test_revoked_scope_blocks_s3_chat_context_chunks_and_redacts_bound_answer
python -m pytest -q tests/test_ar05_s1_session_bridge_01.py tests/test_ar05_s2_assistant_handoff_01.py tests/test_d3_actions.py tests/test_d4_recovery.py tests/test_m1_event_process_recovery.py tests/test_m4_01_dialogue_update_safety.py
npm --prefix frontend run build
node --experimental-transform-types --test frontend/test/ar05-s1-bridge.test.ts
~~~

前端第五项需要 AR05_TRACE_PATH 指向新生成的离线 S1 夹具。设置该变量为隔离的绝对路径后，运行 tests/test_ar05_s1_session_bridge_01.py::test_formal_worker_investigates_same_session_through_real_mcp_and_http 生成夹具。

## 停止线

- 试合以保留连续调查、可信审批和恢复行为为目标。模型仍可在原预算、权限和工具范围内判断下一步。本次没有新增 Workflow Gate，模型判断质量未复评。
- R2 b7c444586c0ee782109e3d5931034abb27a3d597 含 AR-05 较早预检祖先，与 P0 直接试算有 14 个冲突文件。P0 的 migration 19 对应条件审核，R2 的 migration 19 对应 Runtime Grant，R2 已到 v24。待验证合并迁移和摘要回退，R2 未进入候选。
- AR-04B 独立保留 HOLD / UNVERIFIED。组合全仓 pytest、实际浏览器和真实 Provider 为 NOT_RUN。付费请求和外部业务写入为 0。main 保持基线。
