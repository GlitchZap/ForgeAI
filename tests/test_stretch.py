"""Stretch goals: prompt tournament, budget early-stop, human baseline compare, regression mode."""
import json

from forgeai.compare import compare_baseline, regress
from forgeai.pipeline import Factory

from conftest import ROOT, FakeLLM

HR = ROOT / "demos" / "hr_policy"
BRIEF = (HR / "brief.md").read_text(encoding="utf-8")


def _run(tmp_path, **kw):
    out = tmp_path / "run"
    meta = Factory(FakeLLM(), out, **kw).run(BRIEF, HR / "docs", "hr")
    return out, meta


def test_prompt_tournament_picks_on_dev_only(tmp_path):
    out, _ = _run(tmp_path, candidates=3, max_iters=0)
    t = json.loads((out / "tournament.json").read_text())
    assert len(t) == 3 and all("dev_pass_rate" in x for x in t)
    assert "Prompt tournament" in (out / "report.md").read_text()


def test_budget_early_stop(tmp_path):
    _, meta = _run(tmp_path, candidates=1, budget_tokens=10**9, budget_seconds=0.001)
    assert "budget" in meta["stop_reason"]


def test_compare_and_regress(tmp_path):
    out, _ = _run(tmp_path, candidates=1, max_iters=1)
    cmp = compare_baseline(out, HR / "human_baseline.json", FakeLLM())
    assert set(cmp) == {"factory", "human", "factory_wins", "human_wins"}
    assert (out / "baseline_comparison.md").exists()
    summary = regress(out, HR / "docs_v2", FakeLLM(), tmp_path / "reg")
    assert sum(summary.values()) == len(json.loads((out / "evalset.json").read_text()))
    assert (tmp_path / "reg" / "regression.md").exists()
