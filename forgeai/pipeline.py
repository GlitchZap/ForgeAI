"""The factory: brief + folder -> requirements -> agent -> evals -> judge -> critic/optimizer loop -> report.
Every stage writes its artifact to the run directory as it finishes, so a crash still leaves evidence."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from .agent_runtime import AgentRuntime
from .evalgen import generate_evalset
from .generator import VARIANTS, generate_agent
from .ingest import chunk_documents, load_folder
from .intake import requirements_markdown, run_intake
from .judge import Judge
from .llm import LLM, BudgetExceeded
from .optimizer import apply_fix, choose_category
from .report import write_report
from .retrieval import Index
from .schemas import ChangeLog, CaseResult, EvalCase, Requirements, Scorecard


def _rate(rs: list[CaseResult]) -> float:
    return round(sum(r.passed for r in rs) / len(rs), 3) if rs else 0.0


def make_scorecard(it: int, results: list[CaseResult], tokens: int = 0, seconds: float = 0.0) -> Scorecard:
    kinds = sorted({r.kind for r in results})
    fails: dict[str, int] = {}
    for r in results:
        if r.failure:
            fails[r.failure] = fails.get(r.failure, 0) + 1
    judged = [r for r in results if r.judge_agreement is not None]
    return Scorecard(iteration=it, dev_pass_rate=_rate([r for r in results if r.split == "dev"]),
                     holdout_pass_rate=_rate([r for r in results if r.split == "holdout"]),
                     overall_pass_rate=_rate(results), by_kind={k: _rate([r for r in results if r.kind == k]) for k in kinds},
                     failures=fails,
                     judge_disagreement_rate=round(sum(not r.judge_agreement for r in judged) / len(judged), 3) if judged else 0.0,
                     tokens=tokens, seconds=round(seconds, 1), results=results)


class Factory:
    def __init__(self, llm: LLM, out_dir: str | Path, on_event: Callable[[dict], None] | None = None,
                 max_iters: int = 3, candidates: int = 3, budget_tokens: int | None = None,
                 budget_seconds: float | None = None):
        self.llm = llm
        self.out = Path(out_dir)
        self.on_event = on_event
        self.max_iters = max_iters
        self.candidates = candidates
        self.budget_tokens = budget_tokens
        self.budget_seconds = budget_seconds

    # ------------------------------------------------------------ helpers
    def emit(self, stage: str, status: str, **data):
        ev = {"ts": time.time(), "stage": stage, "status": status, **data}
        with open(self.out / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if self.on_event:
            self.on_event(ev)

    def write(self, name: str, obj) -> None:
        p = self.out / name
        if isinstance(obj, str):
            p.write_text(obj, encoding="utf-8")
            return
        if hasattr(obj, "model_dump"):
            data = obj.model_dump(mode="json")
        elif isinstance(obj, list):
            data = [o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in obj]
        else:
            data = obj
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def evaluate(self, rt: AgentRuntime, cases: list[EvalCase], judge: Judge, it, label: str = "") -> list[CaseResult]:
        self.llm.stage = f"eval_{label or f'iter{it}'}"
        out = []
        for i, c in enumerate(cases, 1):
            self.emit("evaluate", "case", iteration=it, label=label, done=i - 1, total=len(cases), case=c.id,
                      question=c.question[:200])
            tr = rt.ask(c.question)
            res = judge.grade(c, tr, rt.context_text(tr))
            res.trace = {"retrieved": [{"id": cid, "text": rt.index.by_id[cid].text[:500]} for cid in tr.retrieved
                                       if cid in rt.index.by_id],
                         "tool_calls": tr.tool_calls, "citations": tr.reply.citations,
                         "refusal_reason": tr.reply.refusal_reason}
            out.append(res)
            self.emit("evaluate", "progress", iteration=it, label=label, done=i, total=len(cases), case=c.id,
                      passed=res.passed, kind=c.kind, split=c.split, failure=res.failure)
        return out

    def _measured(self, fn):
        t, tok = time.time(), self.llm.tokens_used
        r = fn()
        return r, self.llm.tokens_used - tok, time.time() - t

    def _over_budget(self, t0: float, next_tokens: int, next_seconds: float) -> str | None:
        """Early stop if the NEXT iteration (estimated from the last one) would not fit in the budget."""
        if self.budget_tokens and self.llm.tokens_used + next_tokens > self.budget_tokens:
            return f"token budget: next iteration (~{next_tokens:,} tokens) would exceed {self.budget_tokens:,}"
        if self.budget_seconds and (time.time() - t0) + next_seconds > self.budget_seconds:
            return f"time budget: next iteration (~{next_seconds:.0f}s) would exceed {self.budget_seconds:.0f}s"
        return None

    # ------------------------------------------------------------ main
    def run(self, brief: str, docs_path: str | Path, name: str, answers: list[str] | None = None,
            ask: Callable[[str], str] | None = None,
            checkpoint: Callable[[Requirements], Requirements] | None = None) -> dict:
        self.out.mkdir(parents=True, exist_ok=True)
        for f in ("events.jsonl", "trace.jsonl"):
            (self.out / f).unlink(missing_ok=True)
        self.llm.trace_path = self.out / "trace.jsonl"
        self.llm.on_call = lambda phase, info: self.emit("llm", phase, **info)  # heartbeat for 1-3 min silent stretches
        self.llm.token_budget = self.budget_tokens  # hard ceiling; _over_budget is the soft, early one
        t0 = time.time()
        meta = {"name": name, "docs_path": str(docs_path), "model": self.llm.model, "judge_model": self.llm.judge_model,
                "embed_model": self.llm.embed_model, "provider": "groq" if type(self.llm).__name__ == "GroqLLM" else "ollama", "started": t0, "stop_reason": "",
                "budget": {"tokens": self.budget_tokens, "seconds": self.budget_seconds}}
        self.write("brief.md", brief)

        self.emit("ingest", "start", name=name, provider=meta["provider"], model=meta["model"])  # lets the UI label a run before run.json exists
        self.llm.stage = "ingest"
        docs, skipped = load_folder(docs_path)
        if not docs:
            raise ValueError(f"no supported documents in {docs_path} (pdf/md/txt/csv)")
        base_index = Index(chunk_documents(docs), self.llm)
        meta.update(documents=[d.id for d in docs], skipped_files=skipped, retrieval_mode=base_index.mode,
                    chunks=len(base_index.chunks))
        self.emit("ingest", "done", documents=len(docs), chunks=len(base_index.chunks), mode=base_index.mode, skipped=skipped)

        self.emit("intake", "start")
        self.llm.stage = "intake"
        req = run_intake(brief, docs, base_index, self.llm, answers=answers, ask=ask)
        if checkpoint:  # human approves/edits the requirements before anything is generated
            self.emit("checkpoint", "waiting")
            req = checkpoint(req)
            self.emit("checkpoint", "approved")
        self.write("requirements.json", req)
        self.write("requirements.md", requirements_markdown(req))
        self.emit("intake", "done", topics=len(req.must_answer), flags=req.flags,
                  unsupported=[g.topic for g in req.groundability if g.status == "unsupported"])

        self.emit("generate", "start")
        self.llm.stage = "generate"
        candidates, tool_log = generate_agent(req, docs, self.llm, str(Path(docs_path).resolve()), name, self.candidates, brief)
        self.write("tool_selection.json", tool_log)
        self.emit("generate", "done", tools=[t.name for t in candidates[0].tools], candidates=len(candidates))

        self.emit("evalgen", "start")
        self.llm.stage = "evalgen"
        cases, gen_log = generate_evalset(req, candidates[0], base_index.chunks, self.llm)
        self.write("evalset.json", cases)
        self.write("evalgen_log.json", gen_log)
        kinds: dict[str, int] = {}
        for c in cases:
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
        self.emit("evalgen", "done", cases=len(cases), kinds=kinds)
        by_id = {c.id: c for c in cases}
        dev_cases = [c for c in cases if c.split == "dev"]
        judge = Judge(self.llm)

        scorecards: list[Scorecard] = []
        changes: list[ChangeLog] = []
        tournament: list[dict] = []
        best = candidates[0]
        try:
            # ---- prompt tournament: candidates compete on DEV cases only; holdout stays untouched
            if len(candidates) > 1:
                self.emit("tournament", "start", candidates=len(candidates))
                for i, cand in enumerate(candidates):
                    res, tok, sec = self._measured(lambda: self.evaluate(AgentRuntime(cand, self.llm, docs, index=base_index),
                                                                         dev_cases, judge, 0, f"candidate{i}"))
                    tournament.append({"candidate": i, "variant": VARIANTS[i] or "default", "dev_pass_rate": _rate(res),
                                       "prompt_chars": len(cand.system_prompt), "tokens": tok, "seconds": round(sec, 1),
                                       "failures": [r.case_id for r in res if not r.passed]})
                    self.write(f"candidate_{i}.json", cand)
                    self.emit("tournament", "progress", candidate=i, dev=_rate(res))
                # winner: best dev pass rate; ties go to the shorter prompt (less to go wrong, less verbosity)
                win = max(tournament, key=lambda t: (t["dev_pass_rate"], -t["prompt_chars"]))
                best = candidates[win["candidate"]]
                self.write("tournament.json", tournament)
                self.emit("tournament", "done", winner=win["candidate"], dev=win["dev_pass_rate"])
            self.write("agent_v0.json", best)

            rt = AgentRuntime(best, self.llm, docs, index=base_index)
            self.emit("iteration", "start", iteration=0)
            res, tok, sec = self._measured(lambda: self.evaluate(rt, cases, judge, 0))
            best_sc = make_scorecard(0, res, tok, sec)
            best_rt = rt
            scorecards.append(best_sc)
            self.write("scorecards.json", scorecards)  # written per attempt so the UI never waits for the end
            self.emit("iteration", "done", iteration=0, dev=best_sc.dev_pass_rate, holdout=best_sc.holdout_pass_rate)

            exhausted: set[str] = set()
            no_gain_streak = 0
            for it in range(1, self.max_iters + 1):
                last = scorecards[-1]
                stop = self._over_budget(t0, last.tokens, last.seconds)
                if stop:
                    meta["stop_reason"] = f"early stop - {stop}"
                    break
                if no_gain_streak >= 2:
                    meta["stop_reason"] = "early stop - two iterations in a row bought no dev improvement"
                    break
                dev_fail = [r for r in best_sc.results if not r.passed and r.split == "dev"]
                cat = choose_category(dev_fail, exhausted)
                fix = None
                while cat is not None:
                    fails = [r for r in dev_fail if r.failure == cat]
                    self.emit("diagnose", "done", iteration=it, category=cat, cases=[r.case_id for r in fails])
                    self.llm.stage = f"fix_iter{it}"
                    fix = apply_fix(cat, best, fails, by_id, self.llm)
                    if fix is not None:
                        break
                    exhausted.add(cat)
                    cat = choose_category(dev_fail, exhausted)
                if fix is None:
                    meta["stop_reason"] = "no dev failures left" if not dev_fail else "no applicable fix left"
                    break
                new, target, before, after, why = fix
                self.emit("fix", "done", iteration=it, category=cat, target=target, rationale=why)

                rb, ra = best.retrieval, new.retrieval
                same_chunks = (rb.chunk_size, rb.chunk_overlap) == (ra.chunk_size, ra.chunk_overlap)
                new_rt = AgentRuntime(new, self.llm, docs, index=best_rt.index if same_chunks else None)
                self.emit("iteration", "start", iteration=it)
                res, tok, sec = self._measured(lambda: self.evaluate(new_rt, cases, judge, it))
                sc = make_scorecard(it, res, tok, sec)
                scorecards.append(sc)
                self.write("scorecards.json", scorecards)
                prev = {r.case_id: r.passed for r in best_sc.results}
                fixed = [r.case_id for r in sc.results if r.passed and not prev[r.case_id]]
                broke = [r.case_id for r in sc.results if not r.passed and prev[r.case_id]]
                kept = sc.dev_pass_rate > best_sc.dev_pass_rate  # holdout is never used to decide
                changes.append(ChangeLog(iteration=it, category=cat, target=target, before=before, after=after,
                                         rationale=f"{why} | fixed: {fixed or 'none'} | newly failing: {broke or 'none'}",
                                         addressed_cases=[r.case_id for r in fails], score_before=best_sc.dev_pass_rate,
                                         score_after=sc.dev_pass_rate, kept=kept))
                self.write(f"agent_v{new.version}.json", new)
                self.write("iteration_log.json", changes)
                self.emit("iteration", "done", iteration=it, dev=sc.dev_pass_rate, holdout=sc.holdout_pass_rate, kept=kept,
                          tokens=tok)
                if kept:
                    best, best_rt, best_sc = new, new_rt, sc
                    no_gain_streak = 0
                else:
                    exhausted.add(cat)
                    no_gain_streak += 1
            else:
                meta["stop_reason"] = f"iteration limit ({self.max_iters}) reached"
        except BudgetExceeded as e:
            meta["stop_reason"] = f"hard budget exhausted: {e}"
            if not scorecards:
                raise

        self.write("agent.json", best)
        self.write("scorecards.json", scorecards)
        self.write("iteration_log.json", changes)
        final = next(s for s in scorecards if s.iteration == max((c.iteration for c in changes if c.kept), default=0))
        meta.update(finished=time.time(), duration_s=round(time.time() - t0, 1), tokens=self.llm.tokens_used,
                    llm_calls=self.llm.calls, final_version=best.version,
                    final=final.model_dump(include={"dev_pass_rate", "holdout_pass_rate", "overall_pass_rate"}))
        self.write("run.json", meta)
        write_report(self.out, req, best, cases, scorecards, changes, tool_log, gen_log, meta, tournament)
        self.emit("report", "done", final=meta["final"], stop_reason=meta["stop_reason"])
        return meta
