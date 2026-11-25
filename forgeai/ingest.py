"""Load a document folder (pdf / md / txt / csv) and split it into citable chunks."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

SUPPORTED = {".pdf", ".md", ".txt", ".csv"}


@dataclass
class Document:
    id: str  # file name, used as the citation source
    kind: str
    text: str
    rows: list[dict] = field(default_factory=list)  # csv only


@dataclass
class Chunk:
    id: str  # "<doc>#<n>"
    doc: str
    text: str
    heading: str = ""


def load_folder(path: str | Path) -> tuple[list[Document], list[str]]:
    """Returns (documents, skipped file names). Unsupported files are reported, not silently dropped."""
    docs, skipped = [], []
    for p in sorted(Path(path).rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in SUPPORTED:
            skipped.append(p.name)
            continue
        if ext == ".pdf":
            text = "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
            docs.append(Document(p.name, "pdf", text))
        elif ext == ".csv":
            raw = p.read_text(encoding="utf-8-sig", errors="replace")
            try:
                dialect = csv.Sniffer().sniff(raw[:4000], delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()}
                    for r in csv.DictReader(io.StringIO(raw), dialect=dialect)]  # keeps quoted line breaks in a cell
            docs.append(Document(p.name, "csv", raw, rows))
        else:
            docs.append(Document(p.name, ext[1:], p.read_text(encoding="utf-8", errors="replace")))
    return docs, skipped


# "## Leave", "TRAVEL POLICY", "3. Hotels and allowance" - but not clauses like "3.3 Adoption leave: 12 weeks..."
_HEADING = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Z0-9 &/,\-]{4,}|(\d+\.|[A-Z]\.)\s+[A-Z][^.:;]{2,60})$")


def chunk_documents(docs: list[Document], size: int = 900, overlap: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    for d in docs:
        if d.kind == "csv":
            # shortcut: one row per chunk, capped at 2000 rows; group rows if catalogues get larger
            for i, r in enumerate(d.rows[:2000]):
                text = "; ".join(f"{k}: {v}" for k, v in r.items() if v)
                chunks.append(Chunk(f"{d.id}#row{i + 1}", d.id, f"[{d.id} row {i + 1}] {text}"))
            continue
        chunks.extend(_chunk_text(d, size, overlap))
    return chunks


_BLOCK_START = re.compile(r"^(\d+(\.\d+)+\s|\d+\.\s|[A-Z]\d+\.\s|[-*•]\s|#)")  # "1.2 ", "4. ", "A3. ", "- "


def _paragraphs(text: str) -> list[str]:
    """PDF extraction loses blank lines and hard-wraps sentences. When a text has few blank-line paragraphs,
    rebuild them: new paragraph at clause numbers / bullets / headings, otherwise re-join wrapped lines."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) >= max(3, len(text) // 1500):
        return paras
    out: list[str] = []
    for line in (l.strip() for l in text.splitlines()):
        if not line:
            continue
        if not out or _BLOCK_START.match(line) or (_HEADING.match(line) and len(line) < 90):
            out.append(line)
        else:
            out[-1] += " " + line
    return out


def _chunk_text(d: Document, size: int, overlap: int) -> list[Chunk]:
    paras = _paragraphs(d.text)
    out: list[Chunk] = []
    buf, heading, n = "", "", 0

    def flush():
        nonlocal buf, n
        if buf.strip():
            n += 1
            prefix = f"[{d.id}{' > ' + heading if heading else ''}] "
            out.append(Chunk(f"{d.id}#{n}", d.id, prefix + buf.strip(), heading))
        tail = buf[-overlap:] if overlap else ""
        buf = tail[tail.find(" ") + 1:] if " " in tail else tail  # start overlap on a word boundary

    for para in paras:
        first = para.splitlines()[0].strip()
        if _HEADING.match(first) and len(first) < 90:
            if len(buf) > overlap:
                flush()
                buf = ""
            heading = first.lstrip("# ").strip()
        while len(para) > size:  # hard-split very long paragraphs on sentence boundaries
            cut = para.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 3 else size
            buf += ("\n\n" if buf else "") + para[:cut]
            flush()
            para = para[cut:].strip()
        if len(buf) + len(para) > size:
            flush()
        buf += ("\n\n" if buf else "") + para
    flush()
    return out
