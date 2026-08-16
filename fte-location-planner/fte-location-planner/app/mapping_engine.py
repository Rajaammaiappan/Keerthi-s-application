"""
Builds the core "Location Mapping Matrix": Customer Account (rows) x
Location (columns), with base-location markers, supporting-location
checkmarks, and FTE values for whichever period/category is selected.
"""
from __future__ import annotations

import pandas as pd

FILTERABLE_DIMS = ["VM_Product", "Customer_Account", "Component", "Country", "Location"]


def apply_filters(long_df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """filters: dict of dim_name -> list[str] (empty/missing list == All)."""
    df = long_df
    for dim in FILTERABLE_DIMS:
        values = filters.get(dim)
        if values:
            df = df[df[dim].isin(values)]
    return df


def fte_for_period_category(long_df: pd.DataFrame, period: str, category: str) -> pd.DataFrame:
    """Return rows for one period, resolving 'Total' whether or not the
    workbook had an explicit Total column."""
    df = long_df[long_df["Period"] == period]
    if category == "Total":
        if (df["Category"] == "Total").any():
            return df[df["Category"] == "Total"]
        return df[df["Category"] != "Total"]
    return df[df["Category"] == category]


def base_location_status(long_df: pd.DataFrame) -> pd.DataFrame:
    """
    Per Customer_Account x Location, whether it is ever flagged as a base
    location (independent of period/category — base location is a
    structural attribute of the account/product/component/location combo).
    Returns columns: Customer_Account, Location, is_base
    """
    dedup = long_df.drop_duplicates(subset=["_row_id"])
    grouped = (
        dedup.groupby(["Customer_Account", "Location"])["Base_Location_Flag"]
        .apply(lambda s: bool(s.fillna(False).any()))
        .reset_index()
        .rename(columns={"Base_Location_Flag": "is_base"})
    )
    return grouped


def customer_base_warnings(base_status: pd.DataFrame) -> dict:
    """Customer_Account -> warning string, or None if exactly one base."""
    warnings = {}
    for customer, grp in base_status.groupby("Customer_Account"):
        base_count = int(grp["is_base"].sum())
        if base_count == 0:
            warnings[customer] = "BASE LOCATION NOT DEFINED"
        elif base_count > 1:
            warnings[customer] = "MULTIPLE BASE LOCATIONS"
        else:
            warnings[customer] = None
    return warnings


def build_matrix(long_df: pd.DataFrame, filters: dict, period: str, category: str) -> dict:
    """
    Returns:
    {
      "customers": [...],
      "locations": [...],
      "cells": {customer: {location: {"fte": float|None, "is_base": bool, "has_fte": bool}}},
      "customer_warnings": {customer: str|None},
    }
    """
    filtered = apply_filters(long_df, filters)

    base_status = base_location_status(filtered)
    warnings = customer_base_warnings(base_status)

    period_df = fte_for_period_category(filtered, period, category) if period else filtered.iloc[0:0]
    fte_grouped = (
        period_df.groupby(["Customer_Account", "Location"])["FTE"].sum().reset_index()
    )

    customers = sorted(filtered["Customer_Account"].dropna().unique().tolist())
    locations = sorted(filtered["Location"].dropna().unique().tolist())

    base_lookup = {(r.Customer_Account, r.Location): r.is_base for r in base_status.itertuples()}
    fte_lookup = {(r.Customer_Account, r.Location): r.FTE for r in fte_grouped.itertuples()}

    cells: dict = {}
    for cust in customers:
        cells[cust] = {}
        for loc in locations:
            is_base = base_lookup.get((cust, loc), False)
            fte_val = fte_lookup.get((cust, loc))
            has_fte = fte_val is not None and fte_val != 0
            cells[cust][loc] = {
                "fte": fte_val,
                "is_base": is_base,
                "has_fte": has_fte,
            }

    return {
        "customers": customers,
        "locations": locations,
        "cells": cells,
        "customer_warnings": warnings,
    }
