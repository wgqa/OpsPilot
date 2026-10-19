# M3-01 源码入口图（基线 e46d99231f5ef259754228683a1504bf18cea79f）

| 现有入口 | 基线职责 | M3-01 允许的最小扩展 |
|---|---|---|
| opspilot/domain/episodic_memory.py::_source_for_task（约 97 行） | 仅校验 S1 committed REPAIR、200 VerificationReceipt、FrozenReport、Evidence | 加入按业务类型分支的 S2 DiagnosisReceipt/HandoffReceipt 真来源验证 |
| episodic_memory.py:create_memory_candidate/confirm_memory/revoke_memory/list_applicable_memories（约 244–399 行） | D5 单一 Candidate/Active/Revoked 生命周期；固定 401 内容 | 改为案例具体结构化内容和双业务来源；保持 D5 同一生命周期 |
| episodic_memory.py:insert_context_provenance_in_transaction（约 400–490 行） | 在 reserve_attempt 的 BEGIN IMMEDIATE 内校验资产与持久化 selected refs | 将 Memory digest/source refs 纳入校验和可读 Provenance |
| opspilot/domain/database.py:SCHEMA d5_memories（约 708–765 行） | user_version=8；S1 receipt 列 NOT NULL；events FK 指向该注册表 | ADR-001 决定的 v8→v9 无损改造 |
| database.py:initialize（约 860–975 行） | 版本迁移至 v8 | v9 可重入迁移，不碰真实运行库 |
| opspilot/investigator.py::_prompt_messages（约 516–670 行） | S1 可加载 D5；s2_mode 明确不加载 Memory；ContextMetadata 传 reserve | 在唯一 Prompt builder 中按可信问题类型加载 S1/S2 历史方法提示 |
| investigator.py 调用 loop（约 1135–1190 行） | prompt build 后 reserve_attempt，再 Provider I/O | Memory ON/OFF 仅测试级参数；在 reserve transaction 再校验当前 active/version/digest/source |
| opspilot/domain/d2.py:reserve_attempt（约 581–670 行） | 出站预算与 attempt/provenance 原子登记；重用 insert_context_provenance | 保持其为 Memory prompt admission 的可信线性化点 |
| opspilot/domain/chat.py:_current_memories/_message_source_valid/_prepare_context（约 275–545 行） | CHAT_READONLY 当前只查询 auth_401；历史 Answer 依赖 Memory ID/version/digest | 基于可信 S1/S2 状态选择类别；撤销/过期后排除 Memory 及其依赖回答，审计 UI 保留 |
| opspilot/web/app.py:create_app/current_user/write_user 与 Routes（约 120–665 行） | Session、CSRF/Origin、M1/M2 Routes；无 Memory API | 新增最少 Candidate/APPROVER 管理 API，复用身份和命令幂等 |
| frontend/src/App.vue（约 882 行） | 单一工作台及 Task Context/Inspector | 加最小案例来源/审核/撤销/Memory Provenance 面板，不建通用资产后台 |
| tests/test_d5_context.py（约 300 行） | D5 仅 S1；验证确认/撤销、范围、Provenance、Reserve 竞态 | 追加 S2、不同 Task、Web、恢复、历史依赖、迁移和反向用例 |

## 已知基线事实

- Domain schema user_version=8；d5_memories.source_report_ref/source_verification_id NOT NULL。
- D5 固定 MEMORY_SUMMARY 是通用 401 排查方法，不是从源 Task 抽取的案例独有内容。
- S2 DiagnosisReceipt 保存 tenant/task/run/request/decision、Policy 版本、Evidence IDs/digests、observed versions；S2 HandoffReceipt 与 QueueEntry 有独立不可变身份。
- investigator.py 在 s2_mode 下把 memories 设为空；chat.py 查询 auth_401。
- d5_context_provenance 已在真实 Provider attempt 预留事务内写入；chat_context_manifests 和 chat_message_sources 有历史回答来源追踪。
- M2-03 最终报告历史 pytest 为 186/186；需要 M3-01 新鲜全量复跑。

## 冻结时源码与依赖输入 SHA-256

这些摘要绑定本次冻结检查的实际输入；实现提交之后不回写基线值。

| 文件 | SHA-256 |
|---|---|
| opspilot/domain/episodic_memory.py | 7f23f6d3fec933d76fa4457663ef6c987179b758a90d8294b60576c1da42b147 |
| opspilot/domain/investigation_context.py | 1a83e5d5f8ce1e955385cbbf1529d40670f88477a330b0cee05c606151ea4c5d |
| opspilot/domain/chat.py | 0d9fbe40485980d3d9270a1660e9de9d8bd6f8fdc5735ea07290037655a6616c |
| opspilot/investigator.py | 770e99d8ebb0aad4e59af7fcd4769d285763cf14c8090e5ae330e5abd68ce759 |
| opspilot/domain/database.py | 5ce699c704b122e18a7c7f76aec5d46a06e1d0e90633f3d916eda46b171a09e7 |
| opspilot/domain/s2_diagnosis.py | 34613082d0fcb573b9e6216bc5b4c45e3bb8a8f29448bb62f5c09af94b6ebfe1 |
| opspilot/domain/s2_handoff.py | 2daaa59825c18244bef21be4f2180bd4ecf8ec9cc23815e11eccfd4ba8e2a4c8 |
| opspilot/web/app.py | 5ffc3053d6d25f9a8b027b905a2e1421e529db68f727ba112daf95acab380081 |
| frontend/src/App.vue | 0d27d45bc52410c08ed06a34f6c8310f141ee5ca486210272a7ffade20eccf5e |
| tests/test_d5_context.py | 23cc8f027149ec7ecb441900a68b4b66435bc7c9b10992879a6c0d7615621801 |
| requirements.lock.txt | 59658b2a1412f580237fd3a20d88163aea3579e89f6499a768796b6aaca67ae8 |
| pyproject.toml | 351fe34fb378dd4d104e0407a4ae97bc5cc7167c53fef5bd18bb1fa4e34d8e4d |
| frontend/package.json | 0235a3305d7ec143979e8bf1c941a0e68891604506e37216dd122f0b4c19ad44 |
| frontend/package-lock.json | b02c2d6a06ac1aefde5de4d14cd5fdd20f716304481645a7e7b7ff9a4233808a |

此图只冻结实施入口，不声称扩展已完成。基线工作树已有用户未提交文件，均不属于上述源码入口。
