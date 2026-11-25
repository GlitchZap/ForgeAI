"""Tool registry the factory chooses from. Each tool declares what it is FOR so selection can be audited."""
from __future__ import annotations

import ast
import datetime as dt
import operator

import httpx

from .ingest import Document


def _calc(expression: str) -> str:
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos,
           ast.FloorDiv: operator.floordiv}

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            if isinstance(n.op, ast.Pow) and abs(ev(n.right)) > 100:
                raise ValueError("exponent too large")
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.operand))
        raise ValueError("only arithmetic is allowed")
    try:
        r = ev(ast.parse(str(expression).replace(",", ""), mode="eval").body)
        return str(round(r, 6))
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError) as e:
        return f"error: {e}"


def _today(**_) -> str:
    d = dt.date.today()
    return f"{d.isoformat()} ({d.strftime('%A')})"


def _weather(city: str = "", latitude: float | None = None, longitude: float | None = None) -> str:
    try:
        with httpx.Client(timeout=10) as h:
            if latitude is None or longitude is None:
                g = h.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1}).json()
                if not g.get("results"):
                    return f"error: unknown place '{city}'"
                latitude, longitude, city = g["results"][0]["latitude"], g["results"][0]["longitude"], g["results"][0]["name"]
            w = h.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": latitude, "longitude": longitude, "current": "temperature_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "forecast_days": 3}).json()
        return f"{city}: current {w['current']} ; next days {w['daily']}"
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return f"error: weather service unavailable ({e})"


class CsvLookup:
    def __init__(self, docs: list[Document]):
        self.tables = {d.id: d.rows for d in docs if d.kind == "csv"}

    def __call__(self, query: str = "", column: str = "", file: str = "", **_) -> str:
        terms = [t for t in str(query).lower().split() if t]
        hits = []
        for name, rows in self.tables.items():
            if file and file != name:
                continue
            for r in rows:
                hay = (r.get(column, "") if column else " ".join(r.values())).lower()
                if terms and all(t in hay for t in terms):
                    hits.append(f"[{name}] " + "; ".join(f"{k}: {v}" for k, v in r.items() if v))
        if not hits:
            return f"no rows match '{query}'" + (f" in column '{column}'" if column else "")
        return "\n".join(hits[:8]) + (f"\n... {len(hits) - 8} more rows" if len(hits) > 8 else "")


REGISTRY = {
    "csv_lookup": {"purpose": "Exact lookup of rows in the CSV files in the document folder (part numbers, prices, stock, catalogue data).",
                   "args": {"query": "space-separated terms that must all appear in the row", "column": "optional column to search", "file": "optional csv file name"},
                   "requires_csv": True},
    "calculator": {"purpose": "Arithmetic on numbers the user or the documents provide (totals, pro-rating, unit conversion).",
                   "args": {"expression": "arithmetic expression, e.g. 12*450*1.18"}},
    "weather": {"purpose": "Live weather and 3-day forecast for a named place (open-meteo). Only for briefs that need weather.",
                "args": {"city": "place name"}},
    "current_date": {"purpose": "Today's date, for deadlines, notice periods, 'how many days until' questions.",
                     "args": {}},
}


# Words that show a brief really needs a tool. A model vote alone is not enough (3B models vote yes for weather on
# an HR brief); the need must also be visible in the requester's text.
# shortcut: English keyword lists; a brief in another language would attach no tools - upgrade to an LLM-quoted,
# deterministically verified evidence phrase if that matters.
TRIGGERS = {
    "csv_lookup": r"part|catalog|price|stock|sku|item|row|table|look ?up|supplier|inventor",
    "calculator": r"total|sum|calculat|discount|cost|multipl|percent|work out|add up|pro.?rat|convert",
    "weather": r"weather|forecast|wind|rain|storm|temperature|sea state|monsoon",
    "current_date": r"today|date|deadline|days (left|until|remain)|how many days|due|expir|countdown",
}


def build_tools(names: list[str], docs: list[Document]) -> dict:
    impl = {"csv_lookup": CsvLookup(docs), "calculator": lambda expression="", **_: _calc(expression),
            "weather": lambda city="", **kw: _weather(city, kw.get("latitude"), kw.get("longitude")),
            "current_date": _today}
    return {n: impl[n] for n in names if n in impl}


def describe(names: list[str]) -> str:
    return "\n".join(f"- {n}: {REGISTRY[n]['purpose']} Args: {REGISTRY[n]['args']}" for n in names if n in REGISTRY)
