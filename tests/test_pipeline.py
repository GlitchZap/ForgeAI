"""End-to-end factory run on the HR demo with FakeLLM: every stage runs and every artifact is written."""
import json

from forgeai.pipeline import Factory

from conftest import ROOT, FakeLLM

BRIEF = (ROOT / "demos" / "hr_policy" / "brief.md").read_text(encoding="utf-8")


def test_factory_end_to_end_writes_all_artifacts(tmp_path):
    out = tmp_path / "run"
    meta = Factory(FakeLLM(), out).run(BRIEF, ROOT / "demos" / "hr_policy" / "docs", "hr")
    for f in ["brief.md", "requirements.json", "requirements.md", "agent_v0.json", "agent.json", "tool_selection.json",
              "evalset.json", "evalgen_log.json", "scorecards.json", "iteration_log.json", "report.md", "run.json",
              "trace.jsonl", "events.jsonl"]:
        assert (out / f).exists(), f

    req = json.loads((out / "requirements.json").read_text())
    assert any(g["status"] == "unsupported" for g in req["groundability"])      # tax gap flagged
    assert all(qa["assumed"] for qa in req["clarifications"])                  # unattended -> assumptions labelled

    agent = json.loads((out / "agent.json").read_text())
    assert [t["name"] for t in agent["tools"]] == ["current_date"]             # no weather/csv on an HR agent

    cases = json.loads((out / "evalset.json").read_text())
    assert len(cases) >= 20
    kinds = {c["kind"] for c in cases}
    assert {"answerable", "multi_doc", "out_of_scope"} <= kinds
    assert {c["split"] for c in cases} == {"dev", "holdout"}
    assert not any("INVENTED FACT 999" in f for c in cases for f in c["key_facts"])  # unverifiable facts rejected
    gen_log = json.loads((out / "evalgen_log.json").read_text())
    assert gen_log == [] or all("rejected" in g or "skipped" in g or "error" in g for g in gen_log)

    scs = json.loads((out / "scorecards.json").read_text())
    assert 1 <= len(scs) <= 4
    assert meta["stop_reason"]
    report = (out / "report.md").read_text()
    assert "What still fails" in report and "How much to trust these numbers" in report
    assert "self-preference" not in report  # judge model differs from agent model in this run


def test_human_checkpoint_edits_are_used(tmp_path):
    def checkpoint(req):
        req.must_refuse.append("Questions about the office canteen")
        return req
    Factory(FakeLLM(), tmp_path / "r", max_iters=0).run(BRIEF, ROOT / "demos" / "hr_policy" / "docs", "hr", checkpoint=checkpoint)
    agent = json.loads((tmp_path / "r" / "agent.json").read_text())
    assert "canteen" in agent["prompt"]["refusal_policy"]
