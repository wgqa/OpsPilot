"""Offline, pre-frozen lexical-v1 vs BM25-lite-v1 Knowledge retrieval comparison."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from opspilot.config import ROOT
from opspilot.domain.s3_assets import search_knowledge
from opspilot.smokes.m4_02 import write_json

BASE = ROOT / "docs/evidence/vnext/m4-03"


def _dcg(relevances: list[int]) -> float:
    return sum((2 ** value - 1) / math.log2(index + 2) for index, value in enumerate(relevances))


def main() -> int:
    query_set = json.loads((BASE / "RETRIEVAL_QUERIES.json").read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("retrieval-%Y%m%dT%H%M%SZ")
    root = BASE / "runs" / stamp
    root.mkdir(parents=True, exist_ok=False)
    results = []
    summary = {}
    for version in (1, 2):
        for query in query_set["queries"]:
            labels = {str(key): int(value) for key, value in query["relevant_documents"].items()}
            for method in ("lexical-v1", "bm25-lite-v1"):
                started = time.perf_counter()
                ranked = search_knowledge(query["query"], limit=8, contract_version=version, method=method)
                elapsed_ms = round((time.perf_counter() - started) * 1000, 4)
                relevance = [labels.get(str(item["document_id"]), 0) for item in ranked]
                first_relevant_rank = next((index + 1 for index, value in enumerate(relevance) if value > 0), None)
                ideal = sorted((value for value in labels.values() if value > 0), reverse=True)
                top_relevance = relevance[0] if relevance else 0
                top_one = [top_relevance]
                idcg = _dcg(ideal[:1])
                result = {
                    "query_id": query["query_id"], "contract_version": version, "method": method,
                    "query": query["query"], "ranked_document_ids": [item["document_id"] for item in ranked],
                    "relevance_by_rank": relevance, "judged_relevant_documents": labels,
                    "recall_at_1": int(bool(ranked and str(ranked[0]["document_id"]) in labels)),
                    "mrr": round(1 / first_relevant_rank, 6) if first_relevant_rank else 0,
                    "ndcg_at_1": round(_dcg(top_one) / idcg, 6) if idcg else 0,
                    "mean_top_relevance": round(top_relevance, 4),
                    "candidate_count": len(ranked), "elapsed_ms": elapsed_ms,
                    "embedding_calls": 0, "provider_tokens": 0,
                }
                results.append(result)
                group = summary.setdefault(f"v{version}:{method}", {"rows": 0, "recall_at_1": 0, "mrr": 0.0, "ndcg_at_1": 0.0, "mean_top_relevance": 0.0, "mean_elapsed_ms": 0.0, "empty_queries": 0})
                group["rows"] += 1
                for metric in ("recall_at_1", "mrr", "ndcg_at_1", "mean_top_relevance", "elapsed_ms"):
                    key = "mean_elapsed_ms" if metric == "elapsed_ms" else metric
                    group[key] += float(result[metric])
                group["empty_queries"] += int(not ranked)
    for group in summary.values():
        for metric in ("recall_at_1", "mrr", "ndcg_at_1", "mean_top_relevance", "mean_elapsed_ms"):
            group[metric] = round(group[metric] / max(group["rows"], 1), 6)
    write_json(root / "RESULTS.json", {"release": stamp, "query_release": query_set["release"], "summary": summary, "results": results})
    print(json.dumps({"evidence_dir": str(root.relative_to(ROOT)), "summary": summary}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
