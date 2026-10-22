"""Score the diagnosis engine on labelled incidents, against a naive baseline."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .diagnose import LOG_RULES, Evidence, diagnose


def to_evidence(case: dict) -> Evidence:
    statuses = case.get("probe", [])
    probe = {"statuses": statuses, "p50_ms": case.get("p50")} if statuses else None
    metrics = {"memory": [{"max_pct_of_limit": case["memory_pct"]}] if "memory_pct" in case else [],
               "cpu": [{"max_pct_of_limit": case["cpu_pct"]}] if "cpu_pct" in case else []}
    return Evidence(app="case", platform=case.get("platform", ""), turned_on=case.get("turned_on", True),
                    log_lines=case.get("logs", []), events=case.get("events", []), probe=probe,
                    metrics=metrics)


def baseline(case: dict) -> str:
    """Naive approach: take the first log line that looks like an error and match the first rule."""
    for line in case.get("logs", []) + case.get("events", []):
        if re.search(r"error|fatal|exception|refused|killed|stopped", line, re.IGNORECASE):
            for rule in LOG_RULES:
                if re.search(rule.pattern, line, re.IGNORECASE):
                    return rule.id
            return "X-APP-ERROR"
    return "healthy"


def engine_top(case: dict) -> list[str]:
    result = diagnose(to_evidence(case))
    if result["summary"] == "healthy":
        return ["healthy"]
    return [c["id"] for c in result["causes"]] or ["unclear"]


def evaluate(path: Path) -> dict:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        good = {case["expect"], *case.get("accept", [])}
        top = engine_top(case)
        base = baseline(case)
        rows.append({"name": case["name"], "expect": case["expect"], "engine": top,
                     "engine_top1": top[0] == case["expect"], "engine_top3_ok": bool(good & set(top[:3])),
                     "baseline": base, "baseline_top1": base == case["expect"]})
    n = len(rows) or 1
    return {"set": Path(path).name, "cases": len(rows),
            "engine_top1": round(sum(r["engine_top1"] for r in rows) / n, 3),
            "engine_top3": round(sum(r["engine_top3_ok"] for r in rows) / n, 3),
            "baseline_top1": round(sum(r["baseline_top1"] for r in rows) / n, 3),
            "rows": rows}
