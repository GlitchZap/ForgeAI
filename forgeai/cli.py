"""CLI.
  python -m forgeai doctor                                   # is Ollama up, are the models pulled?
  python -m forgeai run --brief b.md --docs folder/ --out runs/x [--interactive | --answers a.json]
  python -m forgeai chat runs/x/agent.json                   # generic chat runner for any definition
  python -m forgeai label runs/x  |  python -m forgeai agreement runs/x   # judge calibration vs human labels
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .llm import OllamaLLM


def _llm(args) -> OllamaLLM:
    kw = {}
    if getattr(args, "model", None):
        kw["model"] = args.model
    if getattr(args, "judge_model", None):
        kw["judge_model"] = args.judge_model
    return OllamaLLM(**kw)


def cmd_compare(args) -> int:
    from .compare import compare_baseline
    print(json.dumps(compare_baseline(Path(args.run), Path(args.baseline), _llm(args)), indent=2))
    print(f"-> {Path(args.run) / 'baseline_comparison.md'}")
    return 0


def cmd_regress(args) -> int:
    from .compare import regress
    out = Path(args.out or Path(args.run) / "regression")
    print(json.dumps(regress(Path(args.run), Path(args.docs), _llm(args), out), indent=2))
    print(f"-> {out / 'regression.md'}")
    return 0


def cmd_report(args) -> int:
    """Re-render report.md from a finished run's saved JSON (no model calls)."""
    from .report import write_report
    from .schemas import AgentDefinition, ChangeLog, EvalCase, Requirements, Scorecard
    run = Path(args.run)

    def j(name):
        return json.loads((run / name).read_text(encoding="utf-8"))
    write_report(run, Requirements.model_validate(j("requirements.json")), AgentDefinition.model_validate(j("agent.json")),
                 [EvalCase.model_validate(c) for c in j("evalset.json")], [Scorecard.model_validate(s) for s in j("scorecards.json")],
                 [ChangeLog.model_validate(c) for c in j("iteration_log.json")], j("tool_selection.json"),
                 j("evalgen_log.json"), j("run.json"), j("tournament.json") if (run / "tournament.json").exists() else None)
    print(f"-> {run / 'report.md'}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn
    uvicorn.run("forgeai.server:app", host=args.host, port=args.port)
    return 0


def cmd_doctor(args) -> int:
    h = _llm(args).health()
    print(json.dumps(h, indent=2))
    if not h.get("ok"):
        for m in (h.get("missing") or {}).values():
            print(f"  -> run: ollama pull {m}")
    return 0 if h.get("ok") else 1


def cmd_run(args) -> int:
    from .pipeline import Factory
    llm = _llm(args)
    h = llm.health()
    if not h.get("ok"):
        print("Ollama preflight failed:", json.dumps(h, indent=2), file=sys.stderr)
        return 2
    brief = Path(args.brief).read_text(encoding="utf-8")
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8")) if args.answers else None
    ask = (lambda q: input(f"\n[intake] {q}\n> ")) if args.interactive else None
    checkpoint = None
    if args.approve:
        from .intake import requirements_markdown
        from .schemas import Requirements

        def checkpoint(req: Requirements) -> Requirements:
            p = Path(args.out) / "requirements.edit.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(req.model_dump_json(indent=2), encoding="utf-8")
            print(requirements_markdown(req))
            input(f"\nEdit {p} if needed, then press Enter to approve...")
            return Requirements.model_validate_json(p.read_text(encoding="utf-8"))

    def show(ev):
        if ev["status"] != "progress":
            print(f"[{ev['stage']}] {ev['status']} " + json.dumps({k: v for k, v in ev.items() if k not in ('ts', 'stage', 'status')}, ensure_ascii=False))
    meta = Factory(llm, args.out, on_event=show, max_iters=args.iters, candidates=args.candidates,
                   budget_tokens=args.budget, budget_seconds=args.time_budget).run(
        brief, args.docs, args.name or Path(args.out).name, answers=answers, ask=ask, checkpoint=checkpoint)
    print(f"\nDone: {json.dumps(meta['final'])}  report: {Path(args.out) / 'report.md'}")
    return 0


def cmd_chat(args) -> int:
    from .agent_runtime import AgentRuntime
    from .schemas import AgentDefinition
    d = AgentDefinition.model_validate_json(Path(args.definition).read_text(encoding="utf-8"))
    if args.docs:
        d.docs_path = args.docs
    rt = AgentRuntime(d, _llm(args))
    print(f"{d.name} v{d.version} | tools: {[t.name for t in d.tools] or 'none'} | retrieval: {rt.index.mode}. Ctrl+C to exit.")
    history: list[dict] = []
    while True:
        try:
            q = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if not q:
            continue
        tr = rt.ask(q, history)
        print(f"agent> {tr.reply.answer}")
        if tr.reply.citations:
            print(f"   sources: {', '.join(tr.reply.citations)}")
        for c in tr.tool_calls:
            print(f"   tool: {c['tool']}({c['args']})")
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": tr.reply.answer}]


def cmd_label(args) -> int:
    from .calibrate import export_labels
    print(export_labels(Path(args.run)))
    return 0


def cmd_agreement(args) -> int:
    from .calibrate import agreement
    print(json.dumps(agreement(Path(args.run)), indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="forgeai")
    ap.add_argument("--model")
    ap.add_argument("--judge-model")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    r = sub.add_parser("run")
    r.add_argument("--brief", required=True)
    r.add_argument("--docs", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--name")
    r.add_argument("--answers", help="JSON list of answers to the clarifying questions")
    r.add_argument("--interactive", action="store_true", help="answer clarifying questions in the terminal")
    r.add_argument("--approve", action="store_true", help="human checkpoint: review/edit requirements before generation")
    r.add_argument("--iters", type=int, default=3)
    r.add_argument("--candidates", type=int, default=3, help="prompt tournament size (1 disables it)")
    r.add_argument("--budget", type=int, help="token budget for the whole run (early stop when the next iteration won't fit)")
    r.add_argument("--time-budget", type=float, help="wall-clock budget in seconds")
    r.set_defaults(fn=cmd_run)
    cp = sub.add_parser("compare", help="factory agent vs hand-written baseline on the run's eval set")
    cp.add_argument("run")
    cp.add_argument("--baseline", required=True)
    cp.set_defaults(fn=cmd_compare)
    rg = sub.add_parser("regress", help="documents changed: regenerate and re-run the old eval set")
    rg.add_argument("run")
    rg.add_argument("--docs", required=True)
    rg.add_argument("--out")
    rg.set_defaults(fn=cmd_regress)
    rp = sub.add_parser("report", help="re-render report.md from a finished run")
    rp.add_argument("run")
    rp.set_defaults(fn=cmd_report)
    sv = sub.add_parser("serve", help="web API + UI")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(fn=cmd_serve)
    c = sub.add_parser("chat")
    c.add_argument("definition")
    c.add_argument("--docs", help="override the document folder")
    c.set_defaults(fn=cmd_chat)
    lb = sub.add_parser("label")
    lb.add_argument("run")
    lb.set_defaults(fn=cmd_label)
    ag = sub.add_parser("agreement")
    ag.add_argument("run")
    ag.set_defaults(fn=cmd_agreement)
    args = ap.parse_args(argv)
    return args.fn(args)
