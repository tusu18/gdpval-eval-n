"""Prepare a pinned, solver-safe GDPval slice. No model calls or file downloads."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
OCCUPATIONS = (
    "Project Management Specialists",
    "Buyers and Purchasing Agents",
    "Shipping, Receiving, and Inventory Clerks",
)
SOLVER_FIELDS = {"task_id", "occupation", "sector", "prompt", "reference_files", "reference_urls"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def solver_record(row, revision):
    paths = row["reference_files"]
    if any(not p.startswith("reference_files/") or ".." in Path(p).parts for p in paths):
        raise ValueError("Invalid reference file path")
    out = {k: row[k] for k in ("task_id", "occupation", "sector", "prompt")}
    out["reference_files"] = paths
    out["reference_urls"] = [f"https://huggingface.co/datasets/openai/gdpval/resolve/{revision}/{quote(p, safe='/')}" for p in paths]
    assert set(out) == SOLVER_FIELDS
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parquet", type=Path, required=True)
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--output", type=Path, default=ROOT / "data/gdpval")
    a = p.parse_args()
    import pyarrow.parquet as pq
    metadata = json.loads(a.metadata.read_text())
    revision = metadata["sha"]
    expected = json.loads((ROOT / "config/evaluation_protocol.json").read_text())["revision"]
    if revision != expected:
        raise ValueError("Dataset revision differs from proposed protocol")
    rows = pq.read_table(a.parquet).to_pylist()
    selected = sorted((r for r in rows if r["occupation"] in OCCUPATIONS), key=lambda r: (r["occupation"], r["task_id"]))
    if Counter(r["occupation"] for r in selected) != Counter({o: 5 for o in OCCUPATIONS}):
        raise ValueError("Expected five tasks in each selected occupation")
    if len({r["task_id"] for r in selected}) != 15:
        raise ValueError("Duplicate task IDs")
    for role in ("solver", "grader"):
        (a.output / role).mkdir(parents=True, exist_ok=True)
    solver = [solver_record(r, revision) for r in selected]
    grader = [{"task_id": r["task_id"], "rubric_json": r["rubric_json"], "rubric_pretty": r["rubric_pretty"], "gold_deliverable_files": r["deliverable_files"]} for r in selected]
    files = []
    for role, records in (("solver", solver), ("grader", grader)):
        file = a.output / role / "tasks.jsonl"
        file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
        files.append(file)
    csv_path = a.output / "task_selection.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["task_id", "occupation", "reference_count", "prompt_characters"])
        writer.writeheader()
        for r in selected:
            writer.writerow({"task_id": r["task_id"], "occupation": r["occupation"], "reference_count": len(r["reference_files"]), "prompt_characters": len(r["prompt"])})
    manifest = {
        "dataset": "openai/gdpval", "revision": revision, "parquet_sha256": digest(a.parquet),
        "source_rows": len(rows), "selected_rows": len(selected), "occupations": list(OCCUPATIONS),
        "selection_rule": "all five tasks per occupation; selected before model outcomes",
        "use": "public diagnostic evaluation; never synthetic training seed",
        "solver_field_allowlist": sorted(SOLVER_FIELDS),
        "task_ids": [r["task_id"] for r in selected],
        "file_hashes": {str(f.relative_to(a.output)): digest(f) for f in files + [csv_path]},
        "reference_file_count": sum(len(r["reference_files"]) for r in selected),
        "reference_files_downloaded": False,
        "isolation_status": "data separation only; execution sandbox not implemented",
        "model_runs": 0,
    }
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("revision", "selected_rows", "reference_file_count", "model_runs")}))


if __name__ == "__main__":
    main()
