"""Grade the grader: a human labels a sample of judged cases; we report judge-vs-human agreement and Cohen's kappa."""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path


def export_labels(run: Path, n: int = 30, seed: int = 3) -> str:
    cases = {c["id"]: c for c in json.loads((run / "evalset.json").read_text(encoding="utf-8"))}
    final = json.loads((run / "scorecards.json").read_text(encoding="utf-8"))[-1]["results"]
    sample = random.Random(seed).sample(final, min(n, len(final)))
    p = run / "human_labels.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "question", "expected", "answer", "judge_passed", "human_passed (y/n)"])
        for r in sample:
            c = cases[r["case_id"]]
            exp = "MUST REFUSE" if c["should_refuse"] else (c.get("expected_tool") or " | ".join(c["key_facts"]))
            w.writerow([r["case_id"], c["question"], exp, r["answer"], "y" if r["passed"] else "n", ""])
    return f"Wrote {p}. Fill the last column with y/n, then run: python -m forgeai agreement {run}"


def agreement(run: Path) -> dict:
    rows = [r for r in csv.DictReader(open(run / "human_labels.csv", encoding="utf-8"))
            if r["human_passed (y/n)"].strip().lower() in ("y", "n")]
    if not rows:
        return {"error": "no labelled rows yet"}
    j = [r["judge_passed"] == "y" for r in rows]
    h = [r["human_passed (y/n)"].strip().lower() == "y" for r in rows]
    n = len(rows)
    po = sum(a == b for a, b in zip(j, h)) / n
    pj, ph = sum(j) / n, sum(h) / n
    pe = pj * ph + (1 - pj) * (1 - ph)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    out = {"labelled": n, "agreement": round(po, 3), "cohens_kappa": round(kappa, 3),
           "judge_too_lenient": sum(a and not b for a, b in zip(j, h)),
           "judge_too_strict": sum(b and not a for a, b in zip(j, h))}
    (run / "judge_agreement.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
