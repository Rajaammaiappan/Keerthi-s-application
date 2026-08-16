import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app import analysis_engine as ae


def _long_df():
    rows = []
    for period, fte in [("Dec-2025", 18), ("Jun-2026", 10)]:
        rows.append({"_row_id": 1, "Customer_Account": "Ford", "Location": "Cob", "Base_Location_Flag": True,
                      "Period": period, "Category": "Total", "FTE": fte, "VM_Product": "A", "Component": "C1", "Country": "IN"})
    for period, fte in [("Dec-2025", 5), ("Jun-2026", 15)]:
        rows.append({"_row_id": 2, "Customer_Account": "Ford", "Location": "Pun", "Base_Location_Flag": False,
                      "Period": period, "Category": "Total", "FTE": fte, "VM_Product": "A", "Component": "C1", "Country": "IN"})
    return pd.DataFrame(rows)


def test_period_comparison_classifies_reduction_and_growth():
    long_df = _long_df()
    rows = ae.period_comparison(long_df, {}, "Dec-2025", "Jun-2026", "Total")
    by_loc = {(r["customer"], r["location"]): r for r in rows}
    assert by_loc[("Ford", "Cob")]["status"] == "Reduction"
    assert by_loc[("Ford", "Pun")]["status"] == "Growth"


def test_capacity_view_flags_released_capacity():
    long_df = _long_df()
    rows = ae.capacity_view(long_df, {}, "Dec-2025", "Jun-2026", "Total")
    by_loc = {r["location"]: r for r in rows}
    assert by_loc["Cob"]["status"] == "Potential Released Capacity"
    assert by_loc["Pun"]["status"] == "Growth"


def test_transfer_opportunities_matches_release_with_growth():
    long_df = _long_df()
    opportunities = ae.identify_transfer_opportunities(long_df, {}, "Dec-2025", "Jun-2026", "Total")
    assert len(opportunities) == 1
    opp = opportunities[0]
    assert opp["from_location"] == "Cob"
    assert opp["to_location"] == "Pun"
    assert opp["matchable_fte"] == 8.0
