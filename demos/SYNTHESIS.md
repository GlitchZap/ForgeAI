# How the demo documents were made

All companies, people, prices and part numbers are fictional. The documents were written by an LLM (Claude, via
Claude Code) using the prompt below, once per document set, then committed unchanged. They are deliberately
imperfect, like real company files: inconsistent units, a few blank cells, overlapping rules across files, an
outdated note, and one topic each brief asks for that the documents do NOT cover (to exercise the groundability
guard).

## Synthesis prompt

> Write the internal documents for a fictional ship-management company, "Meridian Marine Services", for this use
> case: {use case}. Produce {n} documents in the formats {formats}. Requirements:
> - Realistic, specific content: numbered clauses, concrete numbers (days, amounts in INR or USD, lead times),
>   named roles to contact (no real people or companies).
> - At least two facts that only make sense when two documents are read together (e.g. an approval limit in one
>   file and a price in another).
> - Some mess: inconsistent units or naming, a few empty cells in CSVs, one outdated note.
> - Do NOT cover {deliberate gap}; the brief will ask for it anyway.
> - 300-900 words per prose document; 25-40 rows per CSV.

| Set | Use case | Deliberate gap |
|---|---|---|
| `hr_policy` | HR policy assistant for shore staff | payroll tax / salary deduction questions |
| `ship_spares` | ship-spares procurement assistant | warranty claims process |
| `holdout/crew_it` | IT help for crew on board (not run during development) | satellite internet pricing |
| `holdout/port_ops` | port-call planning assistant that needs live weather (not run during development) | customs duty rates |

`leave_policy.pdf` in `hr_policy` is rendered from Markdown by `scripts/make_pdfs.py` so the PDF ingestion path
is exercised.
