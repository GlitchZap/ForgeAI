"""Deterministic text checks. These are the judge's ground floor: they cannot be sweet-talked."""
from __future__ import annotations

import re
import unicodedata

_STOP = set("a an the of to in on for and or is are was be by with at as it this that from per".split())
_REFUSAL = re.compile(
    r"\b(i (?:can(?:no|')t|cannot|am unable to|'m unable to|do not have|don't have)|not (?:able|covered|in (?:the|my) documents)"
    r"|outside (?:of )?(?:my|the) scope|no information (?:about|on)|unable to (?:help|answer|find)|please contact|i'm sorry, but)",
    re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[‐-―−]", "-", s).replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)  # 1,000 -> 1000
    s = re.sub(r"[^\w%.\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def content_tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[\w%]+(?:\.\d+)?", norm(s)) if t not in _STOP]


def numbers(s: str) -> set[str]:
    """Numbers with at least two digits (single digits are mostly list markers)."""
    return {n.rstrip(".") for n in re.findall(r"\d[\d.]*%?", norm(s)) if len(n.rstrip(".%")) >= 2}


def fact_in(fact: str, text: str, threshold: float = 0.8) -> bool:
    """Fact present if it appears verbatim (normalized) or nearly all its content words and ALL its numbers do."""
    f, t = norm(fact), norm(text)
    if not f:
        return False
    if f in t:
        return True
    if not numbers(fact) <= numbers(text) | set(re.findall(r"\d+", t)):
        return False
    toks = content_tokens(fact)
    if not toks:
        return False
    have = set(content_tokens(text))
    return sum(tok in have for tok in toks) / len(toks) >= threshold


def looks_like_refusal(answer: str) -> bool:
    return bool(_REFUSAL.search(answer or ""))


def strip_citations(s: str) -> str:
    return re.sub(r"\[[^\]]*#[\w]+\]|\b[\w.\-]+\.(?:pdf|md|txt|csv)#\w+", " ", s)


def unsupported_numbers(answer: str, context: str) -> set[str]:
    """Numbers in the answer that appear nowhere in what the agent was shown: the cheapest hallucination detector."""
    return numbers(strip_citations(answer)) - numbers(context) - set(re.findall(r"\d+", norm(context)))


# stems of words that say nothing about WHAT a topic covers ("policy", "information", "questions"...)
GENERIC_STEMS = {"polic", "rule", "rules", "infor", "quest", "answe", "provi", "help", "helps", "staff", "emplo", "gener",
                 "detai", "guida", "proce", "manag", "topic", "relat", "speci", "their", "about", "under", "requi"}


def stems(s: str) -> set[str]:
    # crude 5-char prefix stemming: "deductions"/"deducted" -> "deduc"; enough to compare topic vs text vocabulary
    return {w[:5] for w in content_tokens(s.replace("_", " ")) if len(w) > 2 and not w.isdigit()}


def key_stems(s: str) -> set[str]:
    """Stems that say what something is about."""
    return stems(s) - GENERIC_STEMS


def jaccard(a: str, b: str) -> float:
    x, y = set(content_tokens(a)), set(content_tokens(b))
    return len(x & y) / max(len(x | y), 1)
