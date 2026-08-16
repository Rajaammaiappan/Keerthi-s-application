"""
Rule-based "assistant" for the FTE dataset: a curated list of predefined
questions, plus a small query-builder (pick a metric, run it against
whatever filters/period are currently set). Both are answered purely from
analysis_engine/mapping_engine -- there is no external AI/LLM call, so
every answer is exact and reproducible from the same data that powers the
rest of the app.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app import analysis_engine as ae
from app.mapping_engine import apply_filters, base_location_status, customer_base_warnings, fte_for_period_category


class AssistantError(Exception):
    """Raised when a question/metric can't be answered as asked (e.g. missing periods)."""


def _fmt(n) -> str:
    n = round(float(n), 1)
    return str(int(n)) if n == int(n) else str(n)


def _table(columns: list[str], rows: list[list]) -> dict:
    return {"columns": columns, "rows": rows}


def _require_period_pair(from_period: Optional[str], to_period: Optional[str]) -> None:
    if not from_period or not to_period or from_period == to_period:
        raise AssistantError("Pick two different periods (From / To) above, then ask again.")


# ---------------------------------------------------------------------------
# Predefined questions
# ---------------------------------------------------------------------------

PREDEFINED_QUESTIONS = [
    {"id": "total_fte", "label": "What's the total FTE?", "needs": ["period"],
     "keywords": ["total fte", "total", "overall fte", "how much fte"]},
    {"id": "top_location", "label": "Which location has the most FTE?", "needs": ["period"],
     "keywords": ["top location", "most fte location", "highest location", "biggest location"]},
    {"id": "top_customer", "label": "Which customer has the most FTE?", "needs": ["period"],
     "keywords": ["top customer", "most fte customer", "biggest customer", "highest customer"]},
    {"id": "base_issues", "label": "Are there any base-location issues?", "needs": [],
     "keywords": ["base issue", "base location issue", "missing base", "multiple base"]},
    {"id": "negative_fte", "label": "Are there any negative FTE records?", "needs": [],
     "keywords": ["negative fte", "negative", "data quality"]},
    {"id": "releasing_capacity", "label": "Which locations are releasing capacity?", "needs": ["from_period", "to_period"],
     "keywords": ["releasing capacity", "released capacity", "freeing up capacity", "capacity release"]},
    {"id": "growing_locations", "label": "Which locations are growing?", "needs": ["from_period", "to_period"],
     "keywords": ["growing location", "growth", "growing"]},
    {"id": "transfer_opportunities", "label": "What transfer opportunities exist?", "needs": ["from_period", "to_period"],
     "keywords": ["transfer opportunit", "transfer", "matchable"]},
    {"id": "category_split", "label": "What's the Internal / SWC / External / Others split?", "needs": ["period"],
     "keywords": ["category split", "internal swc external", "breakdown", "split"]},
    {"id": "external_dependency", "label": "Which location relies most on External FTE?", "needs": ["period"],
     "keywords": ["external dependency", "external fte", "relies on external", "external reliance"]},
]


def _answer_total_fte(long_df, filters, period, **_):
    filtered = apply_filters(long_df, filters)
    df = fte_for_period_category(filtered, period, "Total")
    return {"summary": f"Total FTE for **{period}**: **{_fmt(df['FTE'].sum())}**.", "table": None}


def _answer_top_location(long_df, filters, period, **_):
    rows = ae.location_summary(long_df, filters, period, "Total")
    if not rows:
        return {"summary": f"No location data for {period} with the current filters.", "table": None}
    top = rows[0]
    return {
        "summary": f"**{top['location']}** has the most FTE in {period}: {_fmt(top['total_fte'])}, "
                   f"supporting {top['customer_count']} customer(s).",
        "table": _table(
            ["Location", "Total FTE", "Customers Supported"],
            [[r["location"], _fmt(r["total_fte"]), r["customer_count"]] for r in rows[:5]],
        ),
    }


def _answer_top_customer(long_df, filters, period, **_):
    rows = ae.customer_summary(long_df, filters, period, "Total")
    if not rows:
        return {"summary": f"No customer data for {period} with the current filters.", "table": None}
    top = rows[0]
    return {
        "summary": f"**{top['customer']}** has the most FTE in {period}: {_fmt(top['total_fte'])}.",
        "table": _table(
            ["Customer", "Total FTE", "Base Location(s)"],
            [[r["customer"], _fmt(r["total_fte"]), ", ".join(r["base_locations"]) or "-"] for r in rows[:5]],
        ),
    }


def _answer_base_issues(long_df, filters, **_):
    filtered = apply_filters(long_df, filters)
    warnings = customer_base_warnings(base_location_status(filtered))
    issues = {c: w for c, w in warnings.items() if w}
    if not issues:
        return {"summary": "No base-location issues found — every customer has exactly one base location.", "table": None}
    return {
        "summary": f"{len(issues)} customer(s) have base-location issues.",
        "table": _table(["Customer", "Issue"], [[c, w] for c, w in sorted(issues.items())]),
    }


def _answer_negative_fte(long_df, filters, **_):
    filtered = apply_filters(long_df, filters)
    negative = filtered[filtered["FTE"] < 0][["Customer_Account", "Location", "Period", "Category", "FTE"]].drop_duplicates()
    if negative.empty:
        return {"summary": "No negative FTE records found.", "table": None}
    return {
        "summary": f"{len(negative)} negative FTE record(s) found — worth a data-quality check.",
        "table": _table(["Customer", "Location", "Period", "Category", "FTE"], negative.values.tolist()),
    }


def _answer_releasing_capacity(long_df, filters, from_period, to_period, **_):
    _require_period_pair(from_period, to_period)
    releasing = [r for r in ae.capacity_view(long_df, filters, from_period, to_period, "Total")
                 if r["status"] == "Potential Released Capacity"]
    if not releasing:
        return {"summary": f"No locations are releasing capacity between {from_period} and {to_period}.", "table": None}
    return {
        "summary": f"{len(releasing)} location(s) are releasing capacity between {from_period} and {to_period}.",
        "table": _table(
            ["Location", "Current FTE", "Future FTE", "Change"],
            [[r["location"], _fmt(r["current_fte"]), _fmt(r["future_fte"]), _fmt(r["change"])] for r in releasing],
        ),
    }


def _answer_growing_locations(long_df, filters, from_period, to_period, **_):
    _require_period_pair(from_period, to_period)
    growing = [r for r in ae.capacity_view(long_df, filters, from_period, to_period, "Total") if r["status"] == "Growth"]
    if not growing:
        return {"summary": f"No locations are growing between {from_period} and {to_period}.", "table": None}
    return {
        "summary": f"{len(growing)} location(s) are growing between {from_period} and {to_period}.",
        "table": _table(
            ["Location", "Current FTE", "Future FTE", "Change"],
            [[r["location"], _fmt(r["current_fte"]), _fmt(r["future_fte"]), _fmt(r["change"])] for r in growing],
        ),
    }


def _answer_transfer_opportunities(long_df, filters, from_period, to_period, **_):
    _require_period_pair(from_period, to_period)
    rows = ae.identify_transfer_opportunities(long_df, filters, from_period, to_period, "Total")
    if not rows:
        return {"summary": f"No transfer opportunities found between {from_period} and {to_period}.", "table": None}
    return {
        "summary": f"{len(rows)} potential transfer opportunit{'y' if len(rows) == 1 else 'ies'} "
                   f"between {from_period} and {to_period}.",
        "table": _table(
            ["From Location", "To Location", "Matchable FTE"],
            [[r["from_location"], r["to_location"], _fmt(r["matchable_fte"])] for r in rows[:10]],
        ),
    }


def _answer_category_split(long_df, filters, period, **_):
    result = ae.category_breakdown(long_df, filters, period)
    if not result["categories"]:
        return {"summary": "This workbook has no Internal/SWC/External/Others breakdown — only period totals.", "table": None}
    total = sum(d["fte"] for d in result["by_category"])
    if total <= 0:
        return {"summary": f"No FTE recorded for {period} with the current filters.", "table": None}
    parts = ", ".join(f"{d['category']} {round(d['fte'] / total * 100)}%" for d in result["by_category"])
    return {
        "summary": f"For {period}, the split is: {parts} (total {_fmt(total)} FTE).",
        "table": _table(
            ["Category", "FTE", "% of Total"],
            [[d["category"], _fmt(d["fte"]), f"{round(d['fte'] / total * 100)}%"] for d in result["by_category"]],
        ),
    }


def _answer_external_dependency(long_df, filters, period, **_):
    result = ae.category_breakdown(long_df, filters, period)
    if "External" not in result["categories"] or not result["by_location"]:
        return {"summary": "This workbook has no External-category data to compare.", "table": None}
    ranked = sorted(
        (r for r in result["by_location"] if r["total"] > 0),
        key=lambda r: r.get("External", 0) / r["total"],
        reverse=True,
    )
    if not ranked:
        return {"summary": f"No FTE recorded for {period} with the current filters.", "table": None}
    top = ranked[0]
    pct = round(top.get("External", 0) / top["total"] * 100)
    return {
        "summary": f"**{top['location']}** relies most on External FTE in {period}: "
                   f"{_fmt(top.get('External', 0))} of {_fmt(top['total'])} total ({pct}%).",
        "table": _table(
            ["Location", "External FTE", "Total FTE", "% External"],
            [[r["location"], _fmt(r.get("External", 0)), _fmt(r["total"]), f"{round(r.get('External', 0) / r['total'] * 100)}%"]
             for r in ranked[:5]],
        ),
    }


_PREDEFINED_HANDLERS = {
    "total_fte": _answer_total_fte,
    "top_location": _answer_top_location,
    "top_customer": _answer_top_customer,
    "base_issues": _answer_base_issues,
    "negative_fte": _answer_negative_fte,
    "releasing_capacity": _answer_releasing_capacity,
    "growing_locations": _answer_growing_locations,
    "transfer_opportunities": _answer_transfer_opportunities,
    "category_split": _answer_category_split,
    "external_dependency": _answer_external_dependency,
}


def answer_predefined(
    question_id: str, long_df: pd.DataFrame, filters: dict,
    period: Optional[str], from_period: Optional[str], to_period: Optional[str],
) -> dict:
    handler = _PREDEFINED_HANDLERS.get(question_id)
    if handler is None:
        raise AssistantError(f"Unknown question: {question_id}")
    return handler(long_df, filters, period=period, from_period=from_period, to_period=to_period)


# ---------------------------------------------------------------------------
# Free-text box: no NLP/LLM involved. Resolves locally, in order, to
# (1) an exact customer or location name, (2) a keyword match against the
# predefined questions above, or (3) a "try a quick question" fallback.
# ---------------------------------------------------------------------------

def _lookup_customer(long_df, filters, period, name):
    rows = ae.customer_summary(long_df, filters, period, "Total")
    match = next((r for r in rows if r["customer"].lower() == name.lower()), None)
    if not match:
        return None
    return {
        "summary": f"**{match['customer']}**: {_fmt(match['total_fte'])} FTE in {period}. "
                   f"Base: {', '.join(match['base_locations']) or '-'}. "
                   f"Additional: {', '.join(match['additional_locations']) or '-'}. "
                   f"Status: {match['warning'] or 'OK'}.",
        "table": None,
    }


def _lookup_location(long_df, filters, period, name):
    rows = ae.location_summary(long_df, filters, period, "Total")
    match = next((r for r in rows if r["location"].lower() == name.lower()), None)
    if not match:
        return None
    return {
        "summary": f"**{match['location']}**: {_fmt(match['total_fte'])} FTE in {period}, "
                   f"supporting {match['customer_count']} customer(s), base location for {match['base_for_count']} of them.",
        "table": None,
    }


def answer_freeform(
    text: str, long_df: pd.DataFrame, filters: dict,
    period: Optional[str], from_period: Optional[str], to_period: Optional[str],
) -> dict:
    q = (text or "").strip().lower()
    if not q:
        raise AssistantError("Type a question, or tap one of the quick options below.")

    filtered = apply_filters(long_df, filters)
    customers = {str(c).lower(): c for c in filtered["Customer_Account"].dropna().unique()}
    locations = {str(l).lower(): l for l in filtered["Location"].dropna().unique()}

    if q in customers and period:
        result = _lookup_customer(long_df, filters, period, customers[q])
        if result:
            return result
    if q in locations and period:
        result = _lookup_location(long_df, filters, period, locations[q])
        if result:
            return result

    best_id, best_score = None, 0
    for item in PREDEFINED_QUESTIONS:
        for kw in item.get("keywords", []):
            if kw in q or q in kw:
                score = len(kw)
                if score > best_score:
                    best_id, best_score = item["id"], score
    if best_id:
        return answer_predefined(best_id, long_df, filters, period, from_period, to_period)

    raise AssistantError(
        "I don't have a canned answer for that yet — try one of the quick questions below, "
        "or type a customer/location name exactly as it appears in your data."
    )


# ---------------------------------------------------------------------------
# Query builder: pick a metric, run it against the current filters/period.
# Same underlying data as the predefined questions, but returns the full
# listing rather than just the top result.
# ---------------------------------------------------------------------------

METRICS = [
    {"id": "total_fte", "label": "Total FTE", "needs": ["period"]},
    {"id": "location_breakdown", "label": "FTE by Location", "needs": ["period"]},
    {"id": "customer_breakdown", "label": "FTE by Customer", "needs": ["period"]},
    {"id": "category_breakdown", "label": "FTE by Category (Internal/SWC/External/Others)", "needs": ["period"]},
    {"id": "base_status", "label": "Base-location status", "needs": []},
    {"id": "period_comparison", "label": "Period-over-period change", "needs": ["from_period", "to_period"]},
    {"id": "transfer_opportunities", "label": "Transfer opportunities", "needs": ["from_period", "to_period"]},
]


def _metric_location_breakdown(long_df, filters, period, **_):
    rows = ae.location_summary(long_df, filters, period, "Total")
    if not rows:
        return {"summary": f"No location data for {period} with the current filters.", "table": None}
    total = sum(r["total_fte"] for r in rows)
    return {
        "summary": f"{len(rows)} location(s), {_fmt(total)} FTE total for {period}.",
        "table": _table(
            ["Location", "Total FTE", "Customers Supported", "Base For"],
            [[r["location"], _fmt(r["total_fte"]), r["customer_count"], r["base_for_count"]] for r in rows],
        ),
    }


def _metric_customer_breakdown(long_df, filters, period, **_):
    rows = ae.customer_summary(long_df, filters, period, "Total")
    if not rows:
        return {"summary": f"No customer data for {period} with the current filters.", "table": None}
    total = sum(r["total_fte"] for r in rows)
    return {
        "summary": f"{len(rows)} customer(s), {_fmt(total)} FTE total for {period}.",
        "table": _table(
            ["Customer", "Total FTE", "Base Location(s)", "Additional Locations", "Status"],
            [[r["customer"], _fmt(r["total_fte"]), ", ".join(r["base_locations"]) or "-",
              ", ".join(r["additional_locations"]) or "-", r["warning"] or "OK"] for r in rows],
        ),
    }


def _metric_base_status(long_df, filters, **_):
    filtered = apply_filters(long_df, filters)
    warnings = customer_base_warnings(base_location_status(filtered))
    issues = sum(1 for w in warnings.values() if w)
    summary = (f"{len(warnings)} customer(s) checked — all OK." if not issues else
               f"{len(warnings)} customer(s) checked; {issues} with a base-location issue.")
    return {
        "summary": summary,
        "table": _table(["Customer", "Status"], [[c, w or "OK"] for c, w in sorted(warnings.items())]),
    }


def _metric_period_comparison(long_df, filters, from_period, to_period, **_):
    _require_period_pair(from_period, to_period)
    rows = ae.period_comparison(long_df, filters, from_period, to_period, "Total")
    if not rows:
        return {"summary": f"No data to compare between {from_period} and {to_period}.", "table": None}
    growth = sum(1 for r in rows if r["status"] == "Growth")
    reduction = sum(1 for r in rows if r["status"] == "Reduction")
    return {
        "summary": f"Between {from_period} and {to_period}: {growth} growing, {reduction} reducing, "
                   f"{len(rows)} customer/location combination(s) total.",
        "table": _table(
            ["Customer", "Location", "From FTE", "To FTE", "Change", "Status"],
            [[r["customer"], r["location"], _fmt(r["from_fte"]), _fmt(r["to_fte"]), _fmt(r["change"]), r["status"]]
             for r in rows[:15]],
        ),
    }


_METRIC_HANDLERS = {
    "total_fte": _answer_total_fte,
    "location_breakdown": _metric_location_breakdown,
    "customer_breakdown": _metric_customer_breakdown,
    "category_breakdown": _answer_category_split,
    "base_status": _metric_base_status,
    "period_comparison": _metric_period_comparison,
    "transfer_opportunities": _answer_transfer_opportunities,
}


def answer_query(
    metric_id: str, long_df: pd.DataFrame, filters: dict,
    period: Optional[str], from_period: Optional[str], to_period: Optional[str],
) -> dict:
    handler = _METRIC_HANDLERS.get(metric_id)
    if handler is None:
        raise AssistantError(f"Unknown metric: {metric_id}")
    return handler(long_df, filters, period=period, from_period=from_period, to_period=to_period)
