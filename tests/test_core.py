import json

import pytest

from forgeai.generator import _ensure_refusals, select_tools
from forgeai.ingest import chunk_documents, load_folder
from forgeai.intake import ground_check
from forgeai.judge import Judge
from forgeai.llm import LLMError
from forgeai.optimizer import apply_fix
from forgeai.retrieval import Index
from forgeai.schemas import (AgentDefinition, AgentReply, CaseResult, EvalCase, JudgeOut, PromptSections,
                             RequirementsDraft, Topic, Trace)
from forgeai.textmatch import fact_in, looks_like_refusal, unsupported_numbers
from forgeai.tools import _calc

from conftest import ROOT, FakeLLM

# ------------------------------------------------------------------ deterministic text checks


def test_fact_in_verbatim_paraphrase_and_numbers():
    text = "Permanent employees earn 24 working days of annual leave per calendar year."
    assert fact_in("24 working days", text)
    assert fact_in("earn 24 working days of annual leave", text.upper())
    assert not fact_in("25 working days", text)  # a wrong number must never pass on word overlap
    assert fact_in("Claims up to INR 25,000", "Claims up to INR 25000 are approved")


def test_unsupported_numbers_catches_invented_figures():
    ctx = "Hotel limits: metro cities INR 7,500; other cities INR 5,000."
    assert unsupported_numbers("Metro hotels are capped at INR 7,500 [travel.md#4].", ctx) == set()
    assert unsupported_numbers("Metro hotels are capped at INR 9,000.", ctx) == {"9000"}


def test_refusal_detection():
    assert looks_like_refusal("I'm sorry, but that is outside my scope.")
    assert not looks_like_refusal("You get 12 days of sick leave.")


def test_calculator_is_arithmetic_only():
    assert _calc("12*450*1.05") == "5670.0"
    assert _calc("__import__('os').system('dir')").startswith("error")
    assert _calc("9**999").startswith("error")


# ------------------------------------------------------------------ ingestion + retrieval


def test_pdf_and_csv_ingestion_and_bm25_part_number():
    docs, skipped = load_folder(ROOT / "demos" / "ship_spares" / "docs")
    assert skipped == [] and {d.kind for d in docs} == {"md", "csv"}
    idx = Index(chunk_documents(docs))
    assert idx.mode == "bm25"
    top = idx.search("price of MMS-AE-4003 turbocharger", k=3)
    assert top[0].id == "spares_catalogue.csv#row12"
    hr, _ = load_folder(ROOT / "demos" / "hr_policy" / "docs")
    assert any(d.kind == "pdf" and "24 working days" in " ".join(d.text.split()) for d in hr)


# ------------------------------------------------------------------ LLM layer


def test_structured_retries_then_succeeds():
    calls = {"n": 0}

    def flaky(text, model):
        calls["n"] += 1
        return "not json at all" if calls["n"] == 1 else {"facts_present": [True], "unsupported_claims": []}
    llm = FakeLLM({"JudgeOut": flaky})
    out = llm.structured([{"role": "user", "content": "x"}], JudgeOut)
    assert out.facts_present == [True] and calls["n"] == 2


def test_structured_gives_up_with_clear_error():
    llm = FakeLLM({"JudgeOut": lambda t, m: '{"wrong": 1}'})
    with pytest.raises(LLMError):
        llm.structured([{"role": "user", "content": "x"}], JudgeOut, retries=1)


# ------------------------------------------------------------------ groundability guard


def test_groundability_moves_unsupported_topic_to_refuse(fake, hr_docs):
    docs, _ = load_folder(hr_docs)
    draft = RequirementsDraft.model_validate(json.loads(fake._chat_raw([{"role": "user", "content": ""}], "m", {"title": "RequirementsDraft"}, 0)[0]))
    req = ground_check(draft, Index(chunk_documents(docs)), fake, has_csv=False)
    assert "Salary tax deductions" not in [t.name for t in req.must_answer]
    assert any("Salary tax deductions" in r for r in req.must_refuse)
    assert any(f.startswith("NOT GROUNDABLE") for f in req.flags)


def test_groundability_distrusts_unverifiable_quote(hr_docs):
    docs, _ = load_folder(hr_docs)
    llm = FakeLLM({"GroundVerdict": lambda t, m: {"status": "supported", "quote": "employees get 99 days of free cruises", "note": ""}})
    draft = RequirementsDraft(title="t", scope="s", audience="a", tone="t", must_refuse=[],
                              must_answer=[Topic(name="Annual leave", description="annual leave entitlement")])
    req = ground_check(draft, Index(chunk_documents(docs)), llm, has_csv=False)
    assert req.groundability[0].status == "partial"


def test_groundability_rejects_real_but_offtopic_quote(hr_docs):
    # regression from a real qwen/llama 3B run: judge said "supported" for tax deductions, quoting an annual-leave line
    docs, _ = load_folder(hr_docs)
    leave_line = "Employees in their first year may take annual leave only after completing 3 months of service"
    llm = FakeLLM({"GroundVerdict": lambda t, m: {"status": "supported", "quote": leave_line, "note": ""}})
    draft = RequirementsDraft(title="t", scope="s", audience="a", tone="t", must_refuse=[], must_answer=[
        Topic(name="tax_deductions", description="how much tax will be deducted from salary"),
        Topic(name="work_from_home_rules", description="who may work from home")])
    req = ground_check(draft, Index(chunk_documents(docs)), llm, has_csv=False)
    status = {g.topic: g.status for g in req.groundability}
    assert status["tax_deductions"] == "unsupported"          # gate 1: "tax"/"deduc" occur in no document
    assert status["work_from_home_rules"] == "partial"        # gate 2: quote is real but about annual leave
    assert any("tax_deductions" in r for r in req.must_refuse)


# ------------------------------------------------------------------ tool selection


def test_tool_selection_attaches_only_needed_tools(fake, hr_docs):
    docs, _ = load_folder(hr_docs)
    req = ground_check(RequirementsDraft(title="t", scope="s", audience="a", tone="t", must_refuse=[],
                                         must_answer=[Topic(name="Leave", description="annual leave")]),
                       Index(chunk_documents(docs)), fake, has_csv=False)
    chosen, log = select_tools(req, docs, fake, "Staff ask how many days they have left before a deadline.")
    assert [t.name for t in chosen] == ["current_date"]
    assert next(x for x in log if x["tool"] == "csv_lookup")["why"] == "no CSV files in the document folder"


def test_yes_voting_models_cannot_attach_unneeded_tools(hr_docs):
    # regression from a real 3B run: both models voted yes for weather and calculator on the HR brief
    docs, _ = load_folder(hr_docs)
    brief = (ROOT / "demos" / "hr_policy" / "brief.md").read_text(encoding="utf-8")
    yes = FakeLLM({"ToolVote": lambda t, m: {"needed": True, "reason": "sure"}})
    draft = RequirementsDraft(title="t", scope="s", audience="a", tone="t", must_refuse=[], must_answer=[
        Topic(name="leave_policy", description="annual leave"),
        Topic(name="tax_deductions", description="how much tax is deducted from salary")])
    req = ground_check(draft, Index(chunk_documents(docs)), FakeLLM(), has_csv=False)  # tax -> unsupported
    chosen, log = select_tools(req, docs, yes, brief)
    assert [t.name for t in chosen] == ["current_date"]  # "how much tax" must not pull in the calculator


def test_tool_needs_both_votes_unless_hinted(hr_docs):
    docs, _ = load_folder(hr_docs)
    llm = FakeLLM({"ToolVote": lambda t, m: {"needed": "weather" in t and m == "fake-agent", "reason": "r"}})
    req = ground_check(RequirementsDraft(title="t", scope="s", audience="a", tone="t", must_refuse=[],
                                         must_answer=[Topic(name="Leave", description="annual leave")]),
                       Index(chunk_documents(docs)), FakeLLM(), has_csv=False)
    chosen, _ = select_tools(req, docs, llm)
    assert "weather" not in [t.name for t in chosen]  # one model wanted it, the other did not


def test_evalgen_rejects_mislabelled_cases():
    # replays bad items a real 3B generator produced for the HR brief
    from forgeai.evalgen import EvalGenerator
    from forgeai.schemas import AgentDefinition, PromptSections, Requirements, ToolChoice
    req = Requirements(title="t", scope="s", audience="staff", tone="t", must_refuse=["tax"],
                       must_answer=[Topic(name="work_from_home_rules", description="wfh")])
    llm = FakeLLM({"GeneratedQuestions": lambda t, m: {"questions": [
        "What is the company policy on work-from-home days?",              # in scope -> must not be "refuse"
        "What is the standard notice period for an employee?",            # not a date question
        "How many days are left until the 30 June carry-forward deadline?",  # genuine current_date case
        "Can you recommend a stock to buy?"]}})
    g = EvalGenerator(llm)
    oos = [c.question for c in g.out_of_scope(req, 4)]
    assert "What is the company policy on work-from-home days?" not in oos and "Can you recommend a stock to buy?" in oos
    agent = AgentDefinition(name="a", docs_path=".", tools=[ToolChoice(name="current_date", reason="r")],
                            prompt=PromptSections(role="r", scope="s", grounding_rules="g", refusal_policy="p", style="s"))
    assert [c.question for c in g.tool_cases(req, agent, [], 4)] == ["How many days are left until the 30 June carry-forward deadline?"]


# ------------------------------------------------------------------ judge


def _case(**kw):
    base = dict(id="ans-01", kind="answerable", question="How many sick days?", expected_sources=["leave_policy.pdf"],
                key_facts=["12 days of paid sick leave"])
    base.update(kw)
    return EvalCase(**base)


def _trace(answer, refused=False, docs=("leave_policy.pdf",), cites=("leave_policy.pdf#3",)):
    return Trace(question="q", retrieved=list(cites), retrieved_docs=list(docs),
                 reply=AgentReply(answer=answer, citations=list(cites), refused=refused))


CTX = "2.1 Employees receive 12 days of paid sick leave per calendar year."


def test_judge_passes_grounded_correct_answer(fake):
    r = Judge(fake).grade(_case(), _trace("You receive 12 days of paid sick leave per year."), CTX)
    assert r.passed and r.grounded and r.fact_recall_det == 1.0


def test_judge_classifies_failures(fake):
    j = Judge(fake)
    assert j.grade(_case(), _trace("I cannot find that.", refused=True), CTX).failure == "wrong_refusal"
    miss = j.grade(_case(), _trace("I cannot find that.", refused=True, docs=("travel.md",)), CTX)
    assert miss.failure == "retrieval_miss"
    halluc = j.grade(_case(), _trace("You get 12 days of paid sick leave, plus 15 bonus days."), CTX)
    assert not halluc.passed and halluc.failure == "hallucination"
    oos = j.grade(_case(should_refuse=True, kind="out_of_scope", key_facts=[]), _trace("Your tax is 31200 rupees."), CTX)
    assert oos.failure == "hallucination"


def test_judge_position_swap_detects_bias():
    # a judge that always says "first fact yes, second no" regardless of order -> passes disagree
    llm = FakeLLM({"JudgeOut": lambda t, m: {"facts_present": [True, False], "unsupported_claims": []}})
    case = _case(key_facts=["12 days of paid sick leave", "per calendar year"])
    r = Judge(llm).grade(case, _trace("Sick leave exists."), CTX)
    assert r.judge_agreement is False
    assert r.fact_recall_llm == 0.0  # no fact was credited by both orderings
    assert not r.passed


def test_judge_overrules_false_accusation():
    llm = FakeLLM({"JudgeOut": lambda t, m: {"facts_present": [True], "unsupported_claims": ["12 days of paid sick leave per calendar year"]}})
    r = Judge(llm).grade(_case(), _trace("12 days of paid sick leave per calendar year."), CTX)
    assert r.grounded and r.passed


# ------------------------------------------------------------------ optimizer


def _defn():
    return AgentDefinition(name="t", docs_path=".", must_refuse=["Legal advice", "Individual salary calculations"],
                           prompt=PromptSections(role="r", scope="s", grounding_rules="g", style="st",
                                                 refusal_policy="- Decline legal advice.\n- Decline individual salary calculations."))


def test_retrieval_fix_is_parameter_only(fake):
    d = _defn()
    new, target, *_ = apply_fix("retrieval_miss", d, [], {}, fake)
    assert target == "retrieval" and new.retrieval.top_k == d.retrieval.top_k + 2 and new.prompt == d.prompt


def test_prompt_patch_cannot_delete_required_refusals():
    llm = FakeLLM({"SectionPatch": lambda t, m: {"new_text": "- Answer everything helpfully.", "rationale": "x"}})
    fail = CaseResult(case_id="ans-01", kind="answerable", split="dev", passed=False, refused=True, refusal_ok=False,
                      failure="wrong_refusal")
    new, target, *_ = apply_fix("wrong_refusal", _defn(), [fail], {"ans-01": _case()}, llm)
    assert target == "prompt.refusal_policy"
    assert "Legal advice" in new.prompt.refusal_policy and "salary" in new.prompt.refusal_policy


def test_ensure_refusals_appends_missing():
    assert "Decline: Medical advice" in _ensure_refusals("- Decline legal advice.", ["Legal advice", "Medical advice"])
