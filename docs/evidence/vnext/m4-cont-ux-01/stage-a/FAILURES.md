# 阶段 A 失败历史（只追加本轮，不改旧记录）

- `red-01`：11 failed；真实复现新 Follow-up 被 Task 8/6 拒绝、caller limit 绕过、Run/Task 并发超额、辅助计数缺失和不准确的耗尽原因。Schema 新字段尚未实现的负例另列，不冒充业务动态复现。
- `red-02`：5 failed / 2 passed / 11 deselected。两种初始 Run OS 恢复通过；两种只读 Follow-up 恢复分别消费 5、6 MODEL，超过新合同 4；混合辅助分类/Chat/Compression 的两连接竞争实际累计 9。四次接口旅程的两个变体在独立准备处使用了错误字段 `receiver_version`（真实列是 `version`），属于测试准备错误，不算有效业务 RED。修正测试准备，不更改用户目标、判据或正式源码，另存下一轮日志。

付费 Provider：0。所有运行使用确定性模型/本地 HTTP/MCP；原始日志与对应 COMMAND.json 的退出码为准。

- `red-03`：修正字段后的两个完整接口旅程均为有效 RED。最后一轮真实取得同 Event 当前 PROCESSED，但旧 Task MODEL=8 已满，未能正常生成该轮模型答案，结果为事实降级 PARTIAL。两种合法工具次序都失败；不以非空 PARTIAL 计完整成功。
- `green-01`：18 failed，初始化器仍将 >16 视为不支持，而迁移已写入 17，导致二次初始化被拒。这是本轮实现遗漏，不是测试准备或旧产品问题；同步支持版本为 17 后新鲜复跑，原日志不改。
- `green-02`：12 passed / 6 deselected；计数、两级并发、辅助混合竞争与非空 Run 限制交付通过，OS/旅程留给下一次完整运行。
- `green-03`：21 passed / 1 failed。两条四请求真实 HTTP/MCP 确定性旅程、四种 OS 恢复均通过。补充 HTTP 响应丢失测试错误要求现有消息 API 返回 `replayed` 字段；该 API 的合同是返回相同持久 Message/Run/Command ID，未承诺该字段。改为对照响应丢失后实际提交的 Command 结果与重放 ID，不改产品接口或 Gold。

- `green-04`：3 passed / 20 deselected，响应丢失重放、正式纠错与迁移定向通过。
- `regression-01`：142 passed / 6 failed。三个原回归把新建 Task 当作历史 8/6 场景；另外三个相关迁移断言仍期待 Schema 16。本轮显式提供 test-only legacy fixture，并将真实 Schema 迁移断言同步为 17；原安全/业务断言未放宽，旧 Gold、废弃 Intent RED 不改。`green-05` 对 25 个新增用例及这 6 个失败用例复跑，31 passed。
- `full-unfiltered-01`：399 passed / 1 failed。唯一失败是原 `test_m4_autonomy_c1_red.py` 使用废弃 `READONLY_FOLLOWUP` 分类 Intent，而当前合法契约是 `FOLLOW_UP + readonly_action=INVESTIGATE`。原断言、旧 RED 和本次失败日志均保留；没有在生产分类器加入旧 Intent 兼容分支。
- `full-active-01`：399 passed / 1 deselected，仅排除上项历史契约 RED。其结果只证明当时的测试断言，不自动证明每句用户答复都正确。
- `fixture-version-red-01`：最终逐句阅读实际持久答复发现，四轮旅程的 Chat 模型替身硬写了 `receiver-ack-contract-v2@2.0.0`，实际输入来源和上一轮引用为 `2.1.0`。增加精确版本断言后两种合法工具次序均失败（2 failed / 23 deselected）。这是测试替身内容缺陷与此前断言不足，不是生产 Context 来源丢失，也不是 Provider 真实误答。保留此前全部轨迹，不能将先前两条旅程计算为答复质量完整成功。替身改为从实际出站 `CURRENT_APPLICABLE` Knowledge 引用读取版本，正式源码保持不变；用新运行证据重新计算旅程结果。
- `fixture-version-green-01`：2 passed / 23 deselected。两个完整旅程的代词解释均准确引用实际出站当前协议版本；此前错误轨迹不改。
- `full-active-02`：最终测试目标 `fcfb8f99e8b9209d61a737ab1e7b4af696f58595`，399 passed / 1 deselected，exit 0；25 项阶段 A 新测试全部通过。唯一排除仍是已保留的废弃分类契约 RED。所有业务源码仍为 `27a96c1e7ffbb4e836cec15421d24b731dff13b0` 的相同内容，未为答复替身问题扩大生产修复范围。
- 证据打包首次执行因早期四次 COMMAND 没有 `head_at_start` 字段而停止（`KeyError`）。原运行日志/元数据不修改；汇总改为明确 `null / NOT_CAPTURED_IN_EARLY_RUN_METADATA_DO_NOT_BACKFILL`，不事后猜填旧 HEAD。最终全量的 HEAD/工作树 hash 已在调用前真实采集。该失败属于证据打包兼容问题，不是业务或测试运行失败。
- 暂存检查发现未过滤全量 JUnit 的历史失败栈含原始缩进空白。保留 XML 原字节，不清洗失败栈；与原始 `.log` 同样将本任务 `runs/*.xml` 标为 `-text -whitespace`，源码和文档仍执行正常 diff 检查。此处是证据工件空白检查问题，没有修改测试结果或隐藏业务失败。
