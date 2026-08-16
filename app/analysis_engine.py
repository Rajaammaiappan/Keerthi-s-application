"""
Higher-level analytics built on top of the normalized dataset:
summary cards, location/customer summaries, period-over-period comparison,
capacity classification, and simple transfer-opportunity matching.
"""
from __future__ import annotations

import pandas as pd

from app.mapping_engine import apply_filters, fte_for_period_category, base_location_status

REDUCTION_THRESHOLD = 0  # any negative change flags "released capacity"


def summary_cards(long_df: pd.DataFrame, filters: dict, period: str, category: str) -> dict:
    filtered = apply_filters(long_df, filters)
    period_df = fte_for_period_category(filtered, period, category)

    base_status = base_location_status(filtered)
    base_counts = base_status.groupby("Customer_Account")["is_base"].sum()

    total_fte = float(period_df["FTE"].sum())
    total_customers = filtered["Customer_Account"].nunique()
    total_locations = filtered["Location"].nunique()
    base_locations = int((base_status["is_base"]).sum())
    additional_locations = int(len(base_status) - base_locations)
    transfer_opportunities = len(identify_transfer_opportunities(long_df, filters, period, period))

    return {
        "customers": total_customers,
        "locations": total_locations,
        "total_fte": round(total_fte, 1),
        "base_locations": base_locations,
        "additional_locations": additional_locations,
        "transfer_opportunities": transfer_opportunities,
        "accounts_with_base_issues": int(sum(1 for v in base_counts if v != 1)),
    }


def location_summary(long_df: pd.DataFrame, filters: dict, period: str, category: str) -> list[dict]:
    filtered = apply_filters(long_df, filters)
    period_df = fte_for_period_category(filtered, period, category)

    grouped = period_df.groupby("Location").agg(
        total_fte=("FTE", "sum"),
        customers=("Customer_Account", lambda s: sorted(set(s))),
    ).reset_index()

    base_status = base_location_status(filtered)
    base_counts = base_status[base_status["is_base"]].groupby("Location").size()

    rows = []
    for r in grouped.itertuples():
        rows.append({
            "location": r.Location,
            "total_fte": round(float(r.total_fte), 1),
            "customer_count": len(r.customers),
            "customers": r.customers,
            "base_for_count": int(base_counts.get(r.Location, 0)),
        })
    rows.sort(key=lambda x: x["total_fte"], reverse=True)
    return rows


def customer_summary(long_df: pd.DataFrame, filters: dict, period: str, category: str) -> list[dict]:
    filtered = apply_filters(long_df, filters)
    period_df = fte_for_period_category(filtered, period, category)
    base_status = base_location_status(filtered)

    grouped = period_df.groupby("Customer_Account")["FTE"].sum()

    rows = []
    for customer, base_grp in base_status.groupby("Customer_Account"):
        base_locs = sorted(base_grp[base_grp["is_base"]]["Location"].tolist())
        additional_locs = sorted(base_grp[~base_grp["is_base"]]["Location"].tolist())
        rows.append({
            "customer": customer,
            "base_locations": base_locs,
            "additional_locations": additional_locs,
            "total_fte": round(float(grouped.get(customer, 0.0)), 1),
            "warning": (
                "MULTIPLE BASE LOCATIONS" if len(base_locs) > 1
                else "BASE LOCATION NOT DEFINED" if len(base_locs) == 0
                else None
            ),
        })
    rows.sort(key=lambda x: x["total_fte"], reverse=True)
    return rows


def period_comparison(long_df: pd.DataFrame, filters: dict, from_period: str, to_period: str, category: str) -> list[dict]:
    filtered = apply_filters(long_df, filters)
    from_df = fte_for_period_category(filtered, from_period, category)
    to_df = fte_for_period_category(filtered, to_period, category)

    from_grp = from_df.groupby(["Customer_Account", "Location"])["FTE"].sum()
    to_grp = to_df.groupby(["Customer_Account", "Location"])["FTE"].sum()

    keys = set(from_grp.index) | set(to_grp.index)
    rows = []
    for key in keys:
        customer, location = key
        from_val = float(from_grp.get(key, 0.0))
        to_val = float(to_grp.get(key, 0.0))
        change = to_val - from_val
        pct = (change / from_val * 100) if from_val else (100.0 if to_val else 0.0)
        if from_val == 0 and to_val > 0:
            status = "New"
        elif to_val == 0 and from_val > 0:
            status = "Discontinued"
        elif change > 0:
            status = "Growth"
        elif change < 0:
            status = "Reduction"
        else:
            status = "No Change"
        rows.append({
            "customer": customer,
            "location": location,
            "from_fte": round(from_val, 1),
            "to_fte": round(to_val, 1),
            "change": round(change, 1),
            "change_pct": round(pct, 1),
            "status": status,
        })
    rows.sort(key=lambda x: x["change"])
    return rows


def capacity_view(long_df: pd.DataFrame, filters: dict, from_period: str, to_period: str, category: str) -> list[dict]:
    filtered = apply_filters(long_df, filters)
    from_df = fte_for_period_category(filtered, from_period, category)
    to_df = fte_for_period_category(filtered, to_period, category)

    from_grp = from_df.groupby("Location")["FTE"].sum()
    to_grp = to_df.groupby("Location")["FTE"].sum()
    locations = sorted(set(from_grp.index) | set(to_grp.index))

    rows = []
    for loc in locations:
        current = float(from_grp.get(loc, 0.0))
        future = float(to_grp.get(loc, 0.0))
        change = future - current
        if change < REDUCTION_THRESHOLD:
            status = "Potential Released Capacity"
        elif change > 0:
            status = "Growth"
        else:
            status = "Stable"
        rows.append({
            "location": loc,
            "current_fte": round(current, 1),
            "future_fte": round(future, 1),
            "change": round(change, 1),
            "status": status,
        })
    rows.sort(key=lambda x: x["change"])
    return rows


def identify_transfer_opportunities(long_df: pd.DataFrame, filters: dict, from_period: str, to_period: str, category: str = "Total") -> list[dict]:
    """
    Very simple heuristic: locations releasing FTE (reducing) are matched
    against locations/customers requiring FTE (growing) in the same window,
    ranked by the smaller of the two magnitudes (the "matchable" amount).
    """
    if from_period == to_period:
        return []
    cap = capacity_view(long_df, filters, from_period, to_period, category)
    releasing = [c for c in cap if c["status"] == "Potential Released Capacity"]
    growing = [c for c in cap if c["status"] == "Growth"]

    opportunities = []
    for r in releasing:
        for g in growing:
            matchable = min(abs(r["change"]), abs(g["change"]))
            if matchable <= 0:
                continue
            opportunities.append({
                "from_location": r["location"],
                "to_location": g["location"],
                "released_fte": abs(r["change"]),
                "required_fte": g["change"],
                "matchable_fte": round(matchable, 1),
            })
    opportunities.sort(key=lambda x: x["matchable_fte"], reverse=True)
    return opportunities


def data_quality_report(long_df: pd.DataFrame, dataset_warnings: list[str]) -> dict:
    base_status = base_location_status(long_df)
    no_base = base_status.groupby("Customer_Account")["is_base"].sum()
    issues_missing = sorted(no_base[no_base == 0].index.tolist())
    issues_multi = sorted(no_base[no_base > 1].index.tolist())

    negative = long_df[long_df["FTE"] < 0]
    negative_records = negative[["Customer_Account", "Location", "Period", "Category", "FTE"]].drop_duplicates()

    return {
        "parse_warnings": dataset_warnings,
        "missing_base_customers": issues_missing,
        "multiple_base_customers": issues_multi,
        "negative_fte_records": negative_records.to_dict(orient="records"),
    }
