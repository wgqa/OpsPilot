# AR-04B-MEMORY-JOURNEY-01 — 失败与未完成项

## 有效 RED → GREEN

1. **模型输入漏装 Memory（业务 RED）**：runs/red-formal-wire.json 显示 Manifest 有已确认 Memory 引用，但 Fixture Model 实际消息没有指导块。实施后 runs/green-formal-wire-on-off.json 和 E1 Trace 中，ON 输入包含 ID/版本/Digest/内容，OFF 不含。证据来自正式 API/Worker + Fixture Model handler，不是 Provider HTTP。
2. **Manifest/Wire 仅靠 ID 和 Digest 不够（安全 RED）**：runs/red-wire-tamper-valid.log 显示，持久请求中的指导被篡改后旧校验仍成功。恢复完整指导块匹配和答案事务 currentness 校验后，runs/green-wire-tamper-valid.log 通过；runs/G3-tampered-guidance-rejected.json 为 FAILED，已提交答案为 0。

## 保留的失败与准备噪声

- runs/red-formal-wire.log、red-formal-wire-pytest.log、red-formal-wire-basetemp*.log、red-formal-wire-venv.log 保留早期启动失败和 RED 调试日志。最早尝试因项目导入路径或系统 Python 环境不匹配，无法导入 opspilot/langchain_core；它们不是业务 RED，不能计入有效通过。漏装证据独立保存在 red-formal-wire.json。
- runs/green-j6-same-task-followup.log 保留 J6 第一次测试失败：测试误以为 messages API 返回 source_message_id；Domain 关联实际在 chat_run_answers(run_id,message_id)。改为读取该持久关联后，runs/green-j6-same-task-followup-02.log 和最终套件通过。该次是测试断言/取证适配失败，不是产品缺陷。
- runs/green-wire-tamper-e6*.log 和其他 green-*.log 保留中间轮次；包含对 LangChain 序列化层级的早期测试假设，最终按实际 request_json 的 data.content 读取。
- AR-04A 回归 runs/regression-ar04a-context.log：7/8 通过，唯一失败为 test_ar04a_invalidated_summary_is_not_sent_to_the_model。断言搜索整个请求记录，发现摘要 ID 出现在 excluded_sources 用以说明排除原因；摘要状态 NOT_APPLICABLE、选入 Token 为 0、摘要内容未进入 messages。该失败仍保留，本轮没有修改范围外测试。由于日志是在候选上运行，没有证据断言它在原基线上也失败。
- 未执行全量 pytest。无真实 Provider 失败，因为 Provider HTTP=0。
- runs/pytest-tmp-* 是本任务生成的隔离 SQLite/Checkpoint 临时目录，不作为公开证据提交；原始日志和整理后的脱敏 Trace 已保存。

## 尚未验证

- 真实 DeepSeek 是否形成更好的工具选择或答案。
- Provider Usage、真实 Token/费用和 HTTP wire。
- 专门构造大 Memory 并逼近 12,000 Token 上限的 AR-04B 边界样本。
- 全量 pytest 与 AR-04A 唯一失败断言的定义调整。
