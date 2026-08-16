import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from app import assistant_engine as asst


def _long_df():
    rows = []
    # Ford: base at Cob, supporting Ban -- full category breakdown.
    for loc, is_base, cats in [
        ("Cob", True, {"Internal": 8, "SWC": 2, "External": 0, "Others": 0}),
        ("Ban", False, {"Internal": 3, "SWC": 1, "External": 1, "Others": 0}),
    ]:
        for cat, fte in cats.items():
            rows.append({"_row_id": f"ford-{loc}", "Customer_Account": "Ford", "Location": loc,
                         "Base_Location_Flag": is_base, "Period": "Dec-2025", "Category": cat, "FTE": fte,
                         "VM_Product": "A", "Component": "C1", "Country": "IN"})
    # Toyota: no base location defined -- triggers a base-location issue.
    for cat, fte in {"Internal": -2, "SWC": 0, "External": 0, "Others": 0}.items():
        rows.append({"_row_id": "toyota-hyd", "Customer_Account": "Toyota", "Location": "Hyd",
                     "Base_Location_Flag": False, "Period": "Dec-2025", "Category": cat, "FTE": fte,
                     "VM_Product": "A", "Component": "C1", "Country": "IN"})
    # A later period for from/to comparisons.
    for loc, fte in [("Cob", 12), ("Ban", 6)]:
        rows.append({"_row_id": f"ford-{loc}-future", "Customer_Account": "Ford", "Location": loc,
                     "Base_Location_Flag": loc == "Cob", "Period": "Jun-2026", "Category": "Internal", "FTE": fte,
                     "VM_Product": "A", "Component": "C1", "Country": "IN"})
    return pd.DataFrame(rows)


def test_predefined_total_fte():
    # Ford Cob (10) + Ford Ban (5) + Toyota Hyd (-2) = 13
    result = asst.answer_predefined("total_fte", _long_df(), {}, "Dec-2025", None, None)
    assert "13" in result["summary"]
    assert result["table"] is None


def test_predefined_top_location():
    result = asst.answer_predefined("top_location", _long_df(), {}, "Dec-2025", None, None)
    assert "Cob" in result["summary"]
    assert result["table"]["rows"][0][0] == "Cob"


def test_predefined_base_issues_flags_toyota():
    result = asst.answer_predefined("base_issues", _long_df(), {}, "Dec-2025", None, None)
    customers = [r[0] for r in result["table"]["rows"]]
    assert "Toyota" in customers
    assert "Ford" not in customers


def test_predefined_negative_fte_flags_toyota():
    result = asst.answer_predefined("negative_fte", _long_df(), {}, "Dec-2025", None, None)
    assert "1" in result["summary"]
    assert result["table"]["rows"][0][0] == "Toyota"


def test_predefined_requires_period_pair_for_comparisons():
    with pytest.raises(asst.AssistantError):
        asst.answer_predefined("releasing_capacity", _long_df(), {}, "Dec-2025", None, None)


def test_predefined_category_split():
    result = asst.answer_predefined("category_split", _long_df(), {}, "Dec-2025", None, None)
    assert "Internal" in result["summary"]
    cats = [r[0] for r in result["table"]["rows"]]
    assert cats == ["Internal", "SWC", "External", "Others"]


def test_query_location_breakdown_lists_every_location():
    result = asst.answer_query("location_breakdown", _long_df(), {}, "Dec-2025", None, None)
    locations = {r[0] for r in result["table"]["rows"]}
    assert locations == {"Cob", "Ban", "Hyd"}


def test_query_period_comparison_between_periods():
    result = asst.answer_query("period_comparison", _long_df(), {}, None, "Dec-2025", "Jun-2026")
    assert "growing" in result["summary"]
    statuses = {r[-1] for r in result["table"]["rows"]}
    assert "Growth" in statuses


def test_unknown_question_id_raises():
    with pytest.raises(asst.AssistantError):
        asst.answer_predefined("not_a_real_question", _long_df(), {}, "Dec-2025", None, None)


def test_freeform_matches_customer_name():
    result = asst.answer_freeform("ford", _long_df(), {}, "Dec-2025", None, None)
    assert "Ford" in result["summary"]
    assert "15" in result["summary"]  # 8+2 (Cob) + 3+1+1 (Ban) = 15


def test_freeform_matches_location_name():
    result = asst.answer_freeform("Cob", _long_df(), {}, "Dec-2025", None, None)
    assert "Cob" in result["summary"]


def test_freeform_matches_keyword_to_predefined_question():
    result = asst.answer_freeform("what's the total fte", _long_df(), {}, "Dec-2025", None, None)
    assert "Total FTE" in result["summary"]


def test_freeform_unrecognized_text_raises_friendly_error():
    with pytest.raises(asst.AssistantError):
        asst.answer_freeform("asdkjhasdkjh nonsense", _long_df(), {}, "Dec-2025", None, None)


def test_freeform_blank_input_raises():
    with pytest.raises(asst.AssistantError):
        asst.answer_freeform("   ", _long_df(), {}, "Dec-2025", None, None)
