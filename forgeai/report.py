"""Honest report (req 7): what passes, what still fails and why, and how far to trust the numbers."""
from __future__ import annotations

from pathlib import Path

from .schemas import AgentDefinition, ChangeLog, EvalCase, Requirements, Scorecard

WHY = {
    "retrieval_miss": "the right document was never retrieved, so the agent could not see the answer",
    "hallucination": "the agent stated something its excerpts do not support",
    "wrong_refusal": "the answer was in the retrieved excerpts but the agent declined",
    "prompt_defect": "the agent saw the right material but answered out of scope, missed key facts, or skipped the tool",
}


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def wilson(passed: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval: with ~24 generated cases a pass rate is only known to about +/-15 points."""
    if n == 0:
        return 0.0, 0.0
    p = passed / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), min(1.0, c + h)


def write_report(out: Path, req: Requirements, agent: AgentDefinition, cases: list[EvalCase], scs: list[Scorecard],
                 changes: list[ChangeLog], tool_log: list[dict], gen_log: list[dict], meta: dict,
                 tournament: list[dict] | None = None) -> None:
    by_id = {c.id: c for c in cases}
    best_it = max((c.iteration for c in changes if c.kept), default=0)  # the shipped agent = last kept change
    final = next(s for s in scs if s.iteration == best_it)
    n_dev = sum(c.split == "dev" for c in cases)
    md = [f"# ForgeAI report: {meta.get('name') or req.title}", "",
          f"**Final agent:** v{agent.version}  |  **dev pass:** {_pct(final.dev_pass_rate)} ({n_dev} cases)  |  "
          f"**holdout pass:** {_pct(final.holdout_pass_rate)} ({len(cases) - n_dev} cases, never used to tune)  |  "
          f"**overall:** {_pct(final.overall_pass_rate)}", "",
          f"Stopped because: {meta.get('stop_reason') or 'n/a'}. Models: agent `{meta['model']}`, judge `{meta['judge_model']}`, "
          f"embeddings `{meta['embed_model']}` (retrieval mode: {meta.get('retrieval_mode')}). "
          f"{meta.get('llm_calls', 0)} LLM calls, {meta.get('tokens', 0):,} tokens, {meta.get('duration_s', 0)} s.", ""]

    gap = final.dev_pass_rate - final.holdout_pass_rate
    md += ["## How much to trust these numbers"]
    trust = []
    for label, rs in (("dev", [r for r in final.results if r.split == "dev"]),
                      ("holdout", [r for r in final.results if r.split == "holdout"]), ("overall", final.results)):
        lo, hi = wilson(sum(r.passed for r in rs), len(rs))
        trust.append(f"- {label}: {sum(r.passed for r in rs)}/{len(rs)} passed; 95% interval {_pct(lo)}-{_pct(hi)}.")
    grounded_cases = [r for r in final.results if r.retrieval_hit is not None]
    if grounded_cases:
        hits = sum(r.retrieval_hit for r in grounded_cases)
        trust.append(f"- Retrieval recall@{agent.retrieval.top_k} (all expected source documents retrieved): "
                     f"{hits}/{len(grounded_cases)} = {_pct(hits / len(grounded_cases))}.")
    if gap > 0.15:
        trust.append(f"- Dev beats holdout by {_pct(gap)}: the fixes may be overfitting the dev cases.")
    if meta["model"] == meta["judge_model"]:
        trust.append("- The judge is the same model as the agent: self-preference bias is NOT controlled in this run.")
    n_llm = sum(r.judge_agreement is not None for r in final.results)
    trust.append(f"- LLM-judge position-swap disagreement: {_pct(final.judge_disagreement_rate)} of the {n_llm} answers "
                 "the LLM judge graded (only facts credited by both orderings count; answers that passed on "
                 "deterministic checks alone skip the LLM judge).")
    reasons: dict[str, int] = {}
    for g in gen_log:
        if "rejected" in g:
            reasons[g["why"]] = reasons.get(g["why"], 0) + 1
    trust.append(f"- {len(cases)} generated cases kept; {sum(reasons.values())} rejected by validators"
                 + (": " + "; ".join(f"{n} {why}" for why, n in sorted(reasons.items(), key=lambda x: -x[1])) if reasons else "")
                 + ". Kept cases can still be imperfect (see failures below).")
    if meta.get("retrieval_mode") != "hybrid":
        trust.append("- Embeddings were unavailable, so retrieval ran on BM25 only.")
    assumed = [q for q in req.clarifications if q.assumed]
    if assumed:
        trust.append(f"- {len(assumed)} clarifying question(s) had no human answer; conservative defaults were assumed "
                     "(see requirements.md).")
    if meta.get("skipped_files"):
        trust.append(f"- Unsupported files were skipped: {', '.join(meta['skipped_files'])}.")
    md += trust + [""]

    if req.flags:
        md += ["## Requirement flags (groundability guard)"] + [f"- {f}" for f in req.flags] + [""]

    if tournament:
        win = max(tournament, key=lambda t: (t["dev_pass_rate"], -t["prompt_chars"]))
        md += ["## Prompt tournament (dev cases only)", "| Candidate | Variant | Dev pass | Prompt chars | Tokens |",
               "|---|---|---|---|---|"]
        md += [f"| {t['candidate']}{' **winner**' if t is win else ''} | {t['variant'][:60]} | {_pct(t['dev_pass_rate'])} | "
               f"{t['prompt_chars']} | {t['tokens']:,} |" for t in tournament]
        md += ["", "Ties go to the shorter prompt. Holdout cases were not used to pick the winner.", ""]

    md += ["## Per-iteration scorecard",
           "| Iter | Dev | Holdout | Overall | Failures (all splits) | Judge disagreement | Tokens | Seconds |",
           "|---|---|---|---|---|---|---|---|"]
    md += [f"| {s.iteration} | {_pct(s.dev_pass_rate)} | {_pct(s.holdout_pass_rate)} | {_pct(s.overall_pass_rate)} | "
           f"{', '.join(f'{k}: {v}' for k, v in sorted(s.failures.items())) or '-'} | {_pct(s.judge_disagreement_rate)} | "
           f"{s.tokens:,} | {s.seconds} |" for s in scs]
    md += ["", "Pass rate by case type (final): " + ", ".join(f"{k} {_pct(v)}" for k, v in final.by_kind.items()), ""]

    md += ["## Changes made"]
    if not changes:
        md += ["No changes were attempted."]
    for c in changes:
        md += [f"### Iteration {c.iteration}: {c.category} -> `{c.target}` ({'KEPT' if c.kept else 'REVERTED'})",
               f"- Why: {c.rationale}", f"- Addressed cases: {', '.join(c.addressed_cases)}",
               f"- Dev score: {_pct(c.score_before)} -> {_pct(c.score_after or 0)}",
               "<details><summary>Before / after</summary>\n\n```\n" + c.before[:1500] + "\n```\n```\n" + c.after[:1500] + "\n```\n</details>", ""]

    fails = [r for r in final.results if not r.passed]
    md += [f"## What still fails ({len(fails)} of {len(final.results)})"]
    if not fails:
        md += ["Nothing in this eval set. Treat that with suspicion: the set is generated and may be too easy."]
    for r in fails:
        c = by_id[r.case_id]
        md += [f"- **{r.case_id}** [{r.kind}, {r.split}] {c.question}",
               f"  - Category: {r.failure} - {WHY.get(r.failure or '', '')}",
               f"  - Evidence: {'; '.join(r.notes) or 'n/a'}"]
    md += ["", "## Tool selection"]
    for t in tool_log:
        votes = "; ".join(f"{'yes' if v['needed'] else 'no'}: {v['reason']}" for v in t.get("votes", []))
        ev = t.get("evidence_words")
        ev_txt = "" if ev is None else f" - evidence in brief: {', '.join(ev) if ev else 'none, so votes alone are not enough'}"
        md += [f"- **{t['tool']}**: {'ATTACHED' if t['attached'] else 'not attached'}"
               f"{' - ' + t['why'] if t.get('why') else ''}{ev_txt}{' (votes: ' + votes + ')' if votes else ''}"]
    md += ["", "## Artifacts", "requirements.md/json, agent.json (final), agent_v*.json (every version), evalset.json, "
           "scorecards.json, iteration_log.json, tool_selection.json, evalgen_log.json, trace.jsonl (every LLM call), events.jsonl"]
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
