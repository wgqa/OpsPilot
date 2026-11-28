from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "docs/evidence/r2-ar04-live-semantic-pilot-01/RESULTS.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "PREVIOUS_SCORE_SUPPLEMENT.json"
PRELIMINARY_STATUS = "IMPLEMENTER_PRELIMINARY_REVIEW"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_supplement(source: dict) -> dict:
    rows = []
    for item in source.get("rows", []):
        review = item.get("manual_semantic_review")
        if not isinstance(review, dict) or review.get("status") != "REVIEWED_BY_MAIN_AGENT":
            continue
        response = item.get("response")
        rows.append({
            "question_id": item.get("question_id"),
            "group": item.get("group"),
            "status": item.get("status"),
            "response_sha256": _sha(response) if isinstance(response, str) else None,
            "deterministic_rule_score": item.get("deterministic_checks"),
            "manual_semantic_score": {
                "status": PRELIMINARY_STATUS,
                "category": review.get("category"),
                "rationale": review.get("rationale"),
                "reviewer_role": "implementer",
                "independent_main_agent_review": False,
                "evidence_level": "REAL_PROVIDER_RESPONSE_WITH_IMPLEMENTER_PRELIMINARY_REVIEW",
            },
        })
    return {
        "schema_version": 1,
        "task": "R2-AR04-LIVE-EVAL-SETUP-HF-01",
        "source_file": "../r2-ar04-live-semantic-pilot-01/RESULTS.json",
        "source_base_sha": source.get("base_sha"),
        "source_result_status": source.get("status"),
        "status": "IMPLEMENTER_PRELIMINARY_REVIEW",
        "deterministic_and_semantic_scores_separated": True,
        "independent_main_agent_review": "NOT_PERFORMED",
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write an implementer-only scoring erratum supplement.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    result = build_supplement(source)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"rows={len(result['rows'])} status={result['status']} output={args.output}")


if __name__ == "__main__":
    main()
