import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app.mapping_engine import build_matrix, base_location_status, customer_base_warnings


def _long_df():
    return pd.DataFrame([
        {"_row_id": 1, "Customer_Account": "Ford", "Location": "Cob", "Base_Location_Flag": True,
         "Period": "Dec-2025", "Category": "Total", "FTE": 10, "VM_Product": "A", "Component": "C1", "Country": "IN"},
        {"_row_id": 1, "Customer_Account": "Ford", "Location": "Cob", "Base_Location_Flag": True,
         "Period": "Mar-2026", "Category": "Total", "FTE": 8, "VM_Product": "A", "Component": "C1", "Country": "IN"},
        {"_row_id": 2, "Customer_Account": "Ford", "Location": "Ban", "Base_Location_Flag": False,
         "Period": "Dec-2025", "Category": "Total", "FTE": 5, "VM_Product": "A", "Component": "C1", "Country": "IN"},
        {"_row_id": 3, "Customer_Account": "Toyota", "Location": "Cob", "Base_Location_Flag": False,
         "Period": "Dec-2025", "Category": "Total", "FTE": 3, "VM_Product": "A", "Component": "C1", "Country": "IN"},
        {"_row_id": 4, "Customer_Account": "JLR", "Location": "Cob", "Base_Location_Flag": True,
         "Period": "Dec-2025", "Category": "Total", "FTE": 4, "VM_Product": "A", "Component": "C1", "Country": "IN"},
        {"_row_id": 5, "Customer_Account": "JLR", "Location": "Ban", "Base_Location_Flag": True,
         "Period": "Dec-2025", "Category": "Total", "FTE": 2, "VM_Product": "A", "Component": "C1", "Country": "IN"},
    ])


def test_base_location_status_and_warnings():
    long_df = _long_df()
    status = base_location_status(long_df)
    warnings = customer_base_warnings(status)
    assert warnings["Ford"] is None          # exactly one base -> OK
    assert warnings["Toyota"] == "BASE LOCATION NOT DEFINED"
    assert warnings["JLR"] == "MULTIPLE BASE LOCATIONS"


def test_build_matrix_cells():
    long_df = _long_df()
    matrix = build_matrix(long_df, filters={}, period="Dec-2025", category="Total")
    assert "Ford" in matrix["customers"]
    ford_cob = matrix["cells"]["Ford"]["Cob"]
    assert ford_cob["is_base"] is True
    assert ford_cob["fte"] == 10
    ford_ban = matrix["cells"]["Ford"]["Ban"]
    assert ford_ban["is_base"] is False
    assert ford_ban["has_fte"] is True


def test_build_matrix_respects_filters():
    long_df = _long_df()
    matrix = build_matrix(long_df, filters={"Customer_Account": ["Ford"]}, period="Dec-2025", category="Total")
    assert matrix["customers"] == ["Ford"]
