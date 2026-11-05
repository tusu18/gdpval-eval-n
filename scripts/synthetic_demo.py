"""Deterministic procurement-data prototype. Not benchmark evidence or human gold."""
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    "price_with_fixed_fee": {"demand": 200, "deadline": 30, "mandatory_certification": False},
    "capacity_and_deadline": {"demand": 500, "deadline": 14, "mandatory_certification": False},
    "certification_required": {"demand": 350, "deadline": 21, "mandatory_certification": True},
}


def solve(state):
    eligible = [s for s in state["suppliers"] if s["capacity"] >= state["demand"] and s["lead_days"] <= state["deadline"] and (not state["mandatory_certification"] or s["certified"])]
    costs = {s["supplier"]: state["demand"] * s["unit_price_cents"] + s["fixed_fee_cents"] for s in eligible}
    winner = min(costs, key=lambda name: (costs[name], name)) if costs else None
    return {"winner": winner, "eligible_costs_cents": costs, "total_cost_cents": costs.get(winner)}


def validate_answer(state, answer):
    # Independent implementation: exhaustive iteration, with the same documented contract.
    expected = {}
    for s in state["suppliers"]:
        if s["capacity"] < state["demand"]:
            continue
        if s["lead_days"] > state["deadline"]:
            continue
        if state["mandatory_certification"] and not s["certified"]:
            continue
        expected[s["supplier"]] = sum([s["unit_price_cents"] for _ in range(state["demand"])]) + s["fixed_fee_cents"]
    name = sorted(expected, key=lambda n: (expected[n], n))[0] if expected else None
    return answer == {"winner": name, "eligible_costs_cents": expected, "total_cost_cents": expected.get(name)}


def generate(family, seed):
    rng = random.Random(seed)
    state = dict(FAMILIES[family])
    state["suppliers"] = [{"supplier": f"Vendor-{j}", "unit_price_cents": rng.randint(90, 300), "fixed_fee_cents": rng.randint(0, 10000), "capacity": rng.choice([100, 400, 800]), "lead_days": rng.choice([7, 14, 28]), "certified": bool(rng.getrandbits(1))} for j in range(3)]
    answer = solve(state)
    raw = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return {
        "task_id": f"demo-{family}-{seed}", "split": "demonstration_only",
        "source_id": "original-procedural-procurement-spec-v1", "seed_family_id": family,
        "template_id": family, "rng_seed": seed, "generator_model": None,
        "generator_kind": "assistant-designed rules expanded by Python; no model API",
        "state_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "state": state,
        "prompt": "Select the eligible supplier with minimum total cost. Eligibility requires capacity at least demand, lead time at most deadline, and certification when mandatory. Total cost is demand times unit price plus fixed fee. All money is integer cents. Break ties by supplier name. If none is eligible, return null. Return winner, all eligible costs, and winner total.",
        "answer": answer, "verification": "independent recomputation; expert review not performed",
    }


def main():
    path = ROOT / "data/synthetic_demo"
    path.mkdir(parents=True, exist_ok=True)
    rows = [generate(family, seed) for family in FAMILIES for seed in range(100, 108)]
    assert all(validate_answer(r["state"], r["answer"]) for r in rows)
    (path / "examples.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    (path / "manifest.json").write_text(json.dumps({
        "status": "demonstration_only", "rows": len(rows), "independent_spec_families": len(FAMILIES),
        "generator_model": None, "api_calls": 0, "api_spend_usd": 0,
        "root_seed_source": "three original structured procurement specifications authored in this session",
        "random_seed_role": "reproducible numeric and constraint sampling; not a source of real-world coverage",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "data_sha256": hashlib.sha256((path / "examples.jsonl").read_bytes()).hexdigest(),
        "recomputed": len(rows), "expert_reviewed": 0, "model_evaluated": 0,
        "limitations": ["Same abstract workflow; no semantic independence claim", "No real-world realism validation", "No private holdout", "No GDPval prompts, gold outputs, or rubrics loaded by generator", "This orchestration session has viewed GDPval metadata and some prompt previews; generator isolation is not independent authoring"],
    }, indent=2) + "\n")
    print(f"Wrote {len(rows)} demonstration records from {len(FAMILIES)} specification families; no model calls.")


if __name__ == "__main__":
    main()
