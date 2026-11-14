"""Render Context Block/token evidence from the captured fixture traces."""

import json
from pathlib import Path
import tiktoken


ROOT = Path(__file__).parent
RESULTS = json.loads((ROOT / "RESULTS.json").read_text(encoding="utf-8"))
CASES = json.loads((ROOT / "BENCHMARK_CASES.json").read_text(encoding="utf-8"))
CASE_BY_ID = {item["case_id"]: item for item in CASES["cases"]}
ROWS = {item["case_id"]: item for item in RESULTS["cases"]}


def md(value):
    if value is None:
        return "未观测"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def sequence_list(values):
    if not values:
        return "—"
    if len(values) > 20:
        return f"{values[0]}…{values[-1]}（{len(values)} 条）"
    return ", ".join(str(value) for value in values)


lines = [
    "# Context Breakdown：Token、来源与实际输入",
    "",
    "**范围：** 固定 Base `d8e30bcb82557e370f8fec664803a952b8d06e14`；隔离 Domain/Checkpoint；确定性 Fixture Model。Token 均为 `tiktoken:cl100k_base:0.14.0` 应用估算，不是 Provider 计费量。",
    "",
    "## 计数口径",
    "",
    "- `B` 是配置输入预算；`R` 是助手路径对工具 Schema、系统提示、WORK_CONTEXT 和 1,024 Token 工具结果预留的合计；`E=max(0,B-R)` 是压缩选择预算。`RESULTS.json` 中 C06 在首批材料报错前没有返回预算 Manifest，因此实际 `B/E/R` 留空，配置上限仍记录为 12,000。",
    "- `F` 是 Domain Chat 在优先级分配前的完整候选估算。最终模型请求的 `prompt_estimated_tokens`、Schema 估算和 8 Token 序列化/消息开销组成 `estimated_after`。这两个估算口径不同，不把 `estimated_after-F` 当成压缩净节省。",
    "- Manifest 的 `TRUSTED_CONTROL` 数值与最终请求的完整 `prompt_estimated_tokens` 相同；它是实际模型消息集合的聚合估算。`HISTORICAL_SUMMARY` 是该聚合中的子项，不能再相加。`CURRENT_TASK_STATE`、`CURRENT_FACTS`、`RECENT_INTERACTION` 等是来源分类/分配记录；消息内容已由聚合 prompt 计数，逐类估算为 0 不代表那些最近消息没有发送。",
    "- `excluded_blocks` 记录整块排除；`excluded_sources` 记录块内按 Token 预算排除的来源消息。`RECENT_WINDOW` 在生成候选前裁去较旧消息，因而未必产生逐源 `excluded_sources` 记录。",
    "",
    "## 每例预算与模型输入",
    "",
    "| Case | Strategy | W | B | R | E | F | Trigger | Prompt + schema + overhead = after | Summary calls | Raw/selected history Token |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]

for case_id, row in ROWS.items():
    trace_path = ROOT / "case_traces" / f"{case_id}.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    answer_calls = [
        call for call in trace.get("model_calls", [])
        if "context-compression:" not in str(call.get("logical_key", ""))
    ]
    wire = answer_calls[-1].get("request", {}) if answer_calls else {}
    budget = wire.get("context_budget", {})
    prompt = budget.get("prompt_estimated_tokens")
    schema = budget.get("tool_schema_estimated_tokens")
    overhead = (
        row["estimated_after"] - prompt - schema
        if row.get("estimated_after") is not None and prompt is not None and schema is not None
        else None
    )
    after = row.get("estimated_after")
    equation = (
        f"{prompt} + {schema} + {overhead} = {after}"
        if overhead is not None else "未发送"
    )
    strategy = CASE_BY_ID.get(case_id, {}).get("strategy", "—")
    if strategy == "—":
        measured = (trace.get("instrumentation", {}).get("prep_calls") or [{}])[0]
        strategy = measured.get("context_budget", {}).get("strategy", strategy)
    if budget.get("strategy") not in (None, "FAIL_CLOSED_NO_HISTORY_COMPRESSION"):
        strategy = budget["strategy"]
    raw = row.get("raw_history_estimate")
    selected = row.get("selected_raw_history_estimate")
    lines.append(
        f"| {case_id} | {strategy} | {md(row.get('window'))} | {md(row.get('input_budget'))} "
        f"| {md(row.get('reserved'))} | {md(row.get('effective_input_budget_after_reserve'))} "
        f"| {md(row.get('estimated_before'))} | {md(row.get('trigger'))} | {equation} "
        f"| {row.get('compression_calls', 0)} | {md(raw)} / {md(selected)} |"
    )

lines += [
    "",
    "`Raw history Token` 是测试结束时保存的消息快照估算，包含模型回答；`selected history Token` 只计入本次最终模型调用选中的原始消息。序号以 `RESULTS.json` 为准。",
    "",
    "## Context Manifest 分块明细",
    "",
]

for case_id, row in ROWS.items():
    trace_path = ROOT / "case_traces" / f"{case_id}.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    answer_calls = [
        call for call in trace.get("model_calls", [])
        if "context-compression:" not in str(call.get("logical_key", ""))
    ]
    lines += [f"### {case_id}", "", f"证据：[`case_traces/{case_id}.json`](case_traces/{case_id}.json)。"]
    if not answer_calls:
        detail = row.get("error_detail") or {}
        lines += [
            "",
            f"最终模型调用未发生。内部异常 `{detail.get('type')}: {detail.get('message')}`；触发为 `{md(row.get('trigger'))}`，判定记录 `{row.get('trigger_evaluation')}`。本例没有可用的最终 Context Manifest。",
            "",
        ]
        continue
    request = answer_calls[-1].get("request", {})
    context_budget = request.get("context_budget", {})
    lines += [
        "",
        "| Context Block | Token | 状态 | 来源/解释 |",
        "|---|---:|---|---|",
    ]
    for block in request.get("context_blocks", []):
        category = block.get("category", "unknown")
        refs = block.get("source_refs") or []
        if category == "TRUSTED_CONTROL":
            source = "最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。"
        elif category == "HISTORICAL_SUMMARY":
            source = ", ".join(refs) if refs else "无当前摘要"
        elif category == "RECENT_INTERACTION":
            source = (
                f"原始消息序号 {sequence_list(row.get('retained_messages', {}).get('sequences', []))}；"
                "消息 Token 已计入聚合 prompt，本分类的独立估算为 0。"
            )
        elif category == "TOOL_SCHEMA":
            wire_json = json.loads(answer_calls[-1]["request_json"])
            tool_names = [
                item.get("function", {}).get("name", "unknown")
                for item in wire_json.get("tools", [])
            ]
            source = f"当前 Canonical tools/list Schema ({len(tool_names)} tools: {', '.join(tool_names)})。"
            if row.get("schema_change"):
                source += (
                    f"另加未调用合成 Schema `{row['schema_change']['schema_name']}`；"
                    f"描述增加 {row['schema_change']['added_description_tokens']} Token。"
                )
        elif refs:
            source = ", ".join(refs)
        else:
            source = "无当前 Task/MCP/Memory 来源；详见该块状态。"
        lines.append(
            f"| `{category}` | {block.get('estimated_tokens', 0)} | {block.get('status')} | {source} |"
        )
    lines += [
        "",
        f"预算：`B={context_budget.get('input_budget_tokens')}`，`R={row.get('reserved')}`，"
        f"`E={row.get('effective_input_budget_after_reserve')}`；最终输入估算："
        f"`prompt={context_budget.get('prompt_estimated_tokens')} + schema="
        f"{context_budget.get('tool_schema_estimated_tokens')} + 8 = {row.get('estimated_after')}`。",
    ]
    selected = row.get("retained_messages", {}).get("sequences", [])
    lines.append(f"本次选中的原始消息序号：`{sequence_list(selected)}`。")
    sources = row.get("excluded_sources", [])
    if sources:
        details = "; ".join(
            f"seq {item.get('sequence')} ({item.get('role')}, {item.get('category')}, {item.get('reason')})"
            for item in sources
        )
        lines.append(f"逐源排除：{details}。原始消息仍在 Domain 快照中。")
    elif row.get("excluded_blocks"):
        lines.append(f"整块排除：`{json.dumps(row['excluded_blocks'], ensure_ascii=False)}`。")
    else:
        lines.append("最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。")
    batches = row.get("summarized_seq_range", [])
    if batches:
        lines += ["", "压缩批次："]
        for batch in batches:
            lines.append(
                f"- 覆盖 `{batch.get('covered_seq_range')}`；输入估算 {batch.get('estimated_compression_input_tokens')} Token；"
                f"来源序号 `{sequence_list(batch.get('source_sequences', []))}`；"
                f"父摘要 `{batch.get('parent_summary_id') or '无'}`；结果 `{batch.get('status')}`。"
            )
    lines += [""]

wp3 = json.loads((ROOT / "case_traces" / "WP3_INFORMATION_RETENTION.json").read_text(encoding="utf-8"))
current_summaries = [summary for summary in wp3.get("summaries", []) if summary.get("state") == "CURRENT"]
assert len(current_summaries) == 1, f"expected one CURRENT WP3 summary, found {len(current_summaries)}"
wp3_summary = current_summaries[0]
wp3_summary_json = json.loads(wp3_summary["summary_json"])
wp3_sequence_by_message_id = {
    message["message_id"]: message["sequence"]
    for message in wp3.get("persisted_messages", [])
}
wp3_summary_source_ids = [
    source_id
    for value in wp3_summary_json.values()
    for item in ([value] if isinstance(value, dict) else value if isinstance(value, list) else [])
    if isinstance(item, dict)
    for source_id in item.get("source_message_ids", [])
]
assert all(source_id in wp3_sequence_by_message_id for source_id in wp3_summary_source_ids), (
    "CURRENT WP3 summary contains source IDs absent from the persisted message snapshot"
)
protocol_timeline = [
    item for item in wp3_summary_json.get("timeline", [])
    if "v1.2" in item.get("text", "") and "max_attempts" in item.get("text", "")
]
assert len(protocol_timeline) == 1, "CURRENT WP3 summary must have one protocol/attempts timeline item"
protocol_item = protocol_timeline[0]
protocol_text = protocol_item.get("text", "")
required_protocol_facts = ("v1.2", "v1.3", "max_attempts", "3", "5", "部署版本未知")
assert all(fact in protocol_text for fact in required_protocol_facts), (
    "CURRENT WP3 summary lost a version/attempts/deployed-version ground truth"
)
protocol_source_sequences = [
    wp3_sequence_by_message_id[source_id]
    for source_id in protocol_item.get("source_message_ids", [])
    if source_id in wp3_sequence_by_message_id
]
assert protocol_source_sequences == [11], (
    f"CURRENT WP3 protocol timeline should cite seq 11, got {protocol_source_sequences}"
)
wp3_call = [
    call for call in wp3.get("model_calls", [])
    if "context-compression:" not in str(call.get("logical_key", ""))
][-1]
wp3_wire = json.loads(wp3_call["request_json"])
wp3_messages = wp3_wire.get("messages", [])
lines += [
    "## WP3 最终 Fixture Model 输入内容核对",
    "",
    "以下内容由实际传给确定性 Fixture Model 的持久化 `request_json` 复核。Message Token 为内容 Token；整条 prompt 的估算另含角色和消息开销。该输入没有经过真实 Provider。",
    "",
    "| 最终输入部分 | 内容 Token | 来源/证据 |",
    "|---|---:|---|",
]
for index, message in enumerate(wp3_messages):
    data = message.get("data", message)
    kind = message.get("type", data.get("role", "unknown"))
    content = data.get("content", "")
    if isinstance(content, list):
        content = json.dumps(content, ensure_ascii=False)
    if index == 0:
        label = "系统控制提示"
        source = "固定应用系统/安全控制"
    elif kind == "system":
        label = "历史 Summary"
        source = "当前 Summary JSON；来源 ID 见 case trace"
    elif kind == "ai":
        label = "保留的长合成工具结果"
        source = "序号 28；完整合成结果中含 `Receiver=QUEUED`"
    elif index == len(wp3_messages) - 1:
        label = "当前用户消息"
        source = "包含未解决状态与最新 QUEUED 观察"
    else:
        label = "近期合成用户消息"
        source = "Domain 消息序号 19、21、23、25、27"
    lines.append(f"| {label} | {len(tiktoken.get_encoding('cl100k_base').encode(str(content)))} | {source} |")

lines += [
    "",
    "WP3 的 30 条测试结束 Domain 消息快照约 35,095 Token；最终调用选中的原始消息约 4,450 Token。另有 5 条 RECENT_INTERACTION 来源（序号 18、20、22、24、26）因 `INPUT_TOKEN_BUDGET` 未发给模型，原始结果仍在快照中。序号 14、16 的旧材料落入摘要来源；序号 28 的完整长结果仍作为最近消息发送。",
    "",
    "Fixture 的最后回答仅确认请求到达固定 Answer 分支。它不能证明模型从摘要记起早期 API 配置。自然语言语义忠实度、引用充分性和早期回忆仍为 `NEEDS_LIVE_SEMANTIC_EVAL`。",
    "",
    "## WP3 摘要 JSON 信息保持核对",
    "",
    "| Ground Truth | 当前 Summary JSON | 结构/来源判断 |",
    "|---|---|---|",
    "| 初始目标：只读核验回调处理，202 不等于完成 | 保留在 `initial_goal`，引用 seq 1 | 含义一致；Fixture 仅证结构字段和来源映射 |",
    "| 禁止改凭证/业务写入 | 保留在 `constraints`，引用 seq 5 | 含义一致 |",
    "| 初始 endpoint `/callback`、`max_attempts=3`、req-482、evt-731 | Summary 未保留 endpoint 和原始配置关联；`max_attempts=3` 在 seq 11 版本变更中保留，req-482 仅作为更正前错误值出现，evt-731 保留于更正 | 早期配置仅部分保留；摘要不能恢复未写入的 endpoint/原始关联 |",
    "| 正式更正 req-483；req-482 是录入错误；Event 仍 evt-731 | 保留在 `corrections`，引用 seq 7 | 内容和来源 ID 相符 |",
    "| 排除 timeout 假设 | 保留在 `rejected_hypotheses`，引用 seq 9 | 内容和来源 ID 相符 |",
    f"| 协议 v1.2→v1.3；attempts 3→5；部署版本未知 | CURRENT Summary `timeline` 原文：{protocol_text} | 已保留；来源 seq {sequence_list(protocol_source_sequences)}。生成器断言校验版本、attempts、未知部署状态及来源 |",
    "| Synthetic tool result：202 ACCEPTED，Receiver=QUEUED，不证明完成 | `timeline` 保留两条重复材料且在 `HTTP 202` 结束 | 丢失 ACCEPTED、Receiver 与非完成语义；不能把摘要当事实回执 |",
    "| Receiver completion unknown | `unresolved_items` 是空数组 | 未保留在 Summary；当前用户消息仍包含该未解决状态 |",
    "| 最新观察：Receiver=QUEUED，时间 2026-11-14T12:00Z | 不在 Summary；在最终用户消息 seq 29 | 本轮实际 prompt 可见，不能证明跨轮摘要保持 |",
    "",
    "Fixture JSON 中 `source_message_ids` 均可映射到同一 Domain 快照的源消息；这仅证明结构性来源存在，不证明自然语言陈述忠实。Summary 的 512 Token 上限、每条 120 字上限和每类最多 3 项均来自当前代码，以上截断/遗漏是该 Fixture 的实际输出，不是对真实模型质量的结论。",
    "",
    "## 来源失效与原始数据",
    "",
    "WP3 trace 导出了测试结束 Domain 中的原始消息 ID、序号、角色、文本和 digest；其中早期 endpoint、req-482、正式更正 req-483、v1.2→v1.3、原始 `Receiver=QUEUED` 长结果均可读取。测试 Domain 位于 `TemporaryDirectory`，trace 是离线审计快照。AR-04A 中 `test_ar04a_invalidated_summary_is_not_sent_to_the_model` 通过，证明失效 Summary 不进入最终 Fixture 输入；该断言属于 Fixture/Mock 回归，不是线上失效源验证。",
    "",
]

(ROOT / "CONTEXT_BREAKDOWN.md").write_text("\n".join(lines), encoding="utf-8")
print(ROOT / "CONTEXT_BREAKDOWN.md")
