"""S3 user delivery from revalidated sources; no Gate, authorization or tool routing."""
from __future__ import annotations

import json
import re


def parse_response(text):
    raw = str(text or "").strip()
    blocks=re.findall(r"```(?:json)?\s*\n(.*?)```",raw,flags=re.DOTALL|re.IGNORECASE)
    if len(blocks)>1:
        return None
    payload=blocks[0].strip() if blocks else raw
    try:
        value = json.loads(payload)
        if isinstance(value, dict) and value.get("action") in {"answer", "clarify"} and isinstance(value.get("answer"), str) and value["answer"].strip():
            return {**value, "answer": value["answer"].strip(), "result_state": "PARTIAL" if value["action"] == "clarify" else value.get("result_state", "PARTIAL")}
    except (ValueError, TypeError):
        pass
    first, sep, rest = raw.partition("\n")
    match = re.fullmatch(r"RESULT:\s*(ANSWERED|PARTIAL)", first, re.IGNORECASE)
    if match and sep and rest.strip():
        return {"action": "answer", "result_state": match[1].upper(), "answer": rest.strip(), "legacy_format": True}
    if raw.startswith("CLARIFY:") and raw[8:].strip():
        return {"action": "clarify", "result_state": "PARTIAL", "answer": raw[8:].strip()}
    return None


def event_frame(evidence, inputs, proposed_target=None):
    history = [item["facts"] for item in evidence if item["fact_type"] == "s3_transport_history"]
    records = [row for facts in history for row in facts.get("attempts", [])]
    receivers = [item["facts"] for item in evidence if item["fact_type"] == "s3_receiver"]
    deliveries = [item["facts"] for item in evidence if item["fact_type"] == "s3_delivery"]
    events = {str(row["event_id"]) for row in records + receivers + deliveries if row.get("event_id")}
    latest_input = str(inputs[-1].get("body", "")) if inputs else ""
    explicit = [event for event in events if event in latest_input]
    filtered = {facts["requested_event_id"] for facts in history if facts.get("requested_event_id")}
    target = explicit[0] if len(explicit) == 1 else next(iter(filtered)) if len(filtered) == 1 else proposed_target if proposed_target in events else next(iter(events)) if len(events) == 1 else None
    receiver = next((row for row in reversed(receivers) if row.get("event_id") == target), None)
    return {"target_event_id": target, "processing_status": receiver["status"] if receiver else "UNKNOWN",
            "records": records, "receivers": receivers, "events": sorted(events)}


def supported_response(response, evidence, inputs):
    if response is None or response.get("result_state") not in {"ANSWERED", "PARTIAL"}:
        return False
    frame = event_frame(evidence, inputs, response.get("target_event_id"))
    target = response.get("target_event_id")
    if target is not None and target != frame["target_event_id"]:
        return False
    claim = response.get("processing_claim")
    if claim is not None:
        return claim == "NOT_APPLICABLE" or (claim in {"UNKNOWN", "QUEUED", "PROCESSED", "NOT_RECEIVED"} and claim == frame["processing_status"])
    # Legacy protocol answers remain supported; ambiguous cross-Event status prose
    # cannot establish a current processing conclusion without a typed claim.
    return not frame["target_event_id"] or not frame["receivers"] or any(
        row.get("event_id") == frame["target_event_id"] for row in frame["receivers"]
    )


def factual_partial(evidence, knowledge, inputs, reason):
    """A useful sourced fallback, explicitly distinct from normal model delivery."""
    frame = event_frame(evidence, inputs)
    lines = ["当前可核查的事实与未知事项：" if reason == "RULE_BASELINE" else "本次调查只能交付以下已核实事实与缺口："]
    target = frame["target_event_id"]
    if target:
        lines.append(f"关注的事件是 {target}。")
    elif len(frame["events"]) > 1:
        lines.append("发现多个事件（" + "、".join(frame["events"]) + "）；尚未确定您所指的那次，请补充事件或请求标识。")
    rows = [row for row in frame["records"] if not target or row["event_id"] == target]
    for row in rows[-4:]:
        result = f"HTTP {row['http_status']}" if row["result_kind"] == "HTTP_RESPONSE" else "发送结果未知，未取得确定响应"
        lines.append(f"{row['event_id']} 第 {row['attempt_no']} 次，请求 {row['transport_request_id']}，{row['observed_at']}：{result}。")
    if not rows:
        lines.append("本轮没有目标事件可用的历史发送记录；不能用最新快照或 attempt_count 还原旧请求。")
    if target and frame["processing_status"] != "UNKNOWN":
        lines.append(f"同一事件当前接收处理状态为 {frame['processing_status']}；HTTP 接受与处理完成是不同事实。")
    elif frame["receivers"]:
        visible = "; ".join(f"{row['event_id']}={row['status']}" for row in frame["receivers"])
        lines.append(f"当前接收观察为 {visible}；它不能证明其他目标事件恢复，目标当前处理状态仍未知。")
    else:
        lines.append("缺少目标事件本轮有效的接收处理观察，当前是否完成仍未知。")
    if rows:
        lines.append("这些仅为已记录观察；未记录和发送后未落库窗口不构成完整审计。")
    if knowledge:
        lines.append("适用协议来源：" + ", ".join(f"{item['document_id']}@{item['version']}" for item in knowledge) + "。")
    refs = [item["evidence_id"] for item in evidence]
    if refs:
        lines.append("事实来源：" + ", ".join(refs) + "。")
    lines.append("这些只读结论不代表已重发、恢复或交接。" if reason == "RULE_BASELINE" else "调查额度或模型可用性限制了进一步解释；需继续核实上述缺口，不能据此声称已重发、恢复或交接。")
    return "\n".join(lines), {"delivery_mode": "RULE" if reason == "RULE_BASELINE" else "DETERMINISTIC_FALLBACK", "reason": reason, "event_frame": {k: v for k, v in frame.items() if k in {"target_event_id", "processing_status"}}}
