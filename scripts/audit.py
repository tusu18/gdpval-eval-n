"""Small, inspectable preparation checks. Not a semantic contamination certificate."""
import math
import re
import unicodedata


def normalized(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def fivegrams(text):
    words = normalized(text).split()
    return {tuple(words[i:i+5]) for i in range(max(0, len(words)-4))}


def overlap(train, evaluation):
    findings = []
    for a in train:
        for b in evaluation:
            reasons = []
            for field in ("source_id", "seed_family_id", "template_id"):
                if a.get(field) and a.get(field) == b.get(field):
                    reasons.append(field + "_shared")
            if normalized(a["prompt"]) == normalized(b["prompt"]):
                reasons.append("exact_normalized_prompt")
            ag, bg = fivegrams(a["prompt"]), fivegrams(b["prompt"])
            containment = len(ag & bg) / len(bg) if bg else None
            if containment and containment >= .2:
                reasons.append("lexical_review_candidate")
            if reasons:
                findings.append({"train_id": a["task_id"], "eval_id": b["task_id"], "reasons": reasons, "eval_5gram_containment": containment})
    return findings


def summarize(records):
    if not records:
        raise ValueError("No scheduled tasks")
    if len({r["task_id"] for r in records}) != len(records):
        raise ValueError("Duplicate task IDs; repeated attempts require a separate run ID")
    for r in records:
        if not isinstance(r["usable"], bool) or not isinstance(r["critical_error"], bool):
            raise ValueError("Explicit boolean judgments required; unresolved rows cannot silently disappear")
        if r["usable"] and r["critical_error"]:
            raise ValueError("Critical-error output cannot be usable")
        if not math.isfinite(r["cost_usd"]) or r["cost_usd"] < 0:
            raise ValueError("Finite nonnegative cost required")
    n = len(records)
    success = sum(r["usable"] for r in records)
    total_cost = sum(r["cost_usd"] for r in records)
    return {"scheduled": n, "usable": success, "usable_rate": success / n, "critical_error_rate": sum(r["critical_error"] for r in records) / n, "total_cost_usd": total_cost, "cost_per_usable_usd": total_cost / success if success else None}
