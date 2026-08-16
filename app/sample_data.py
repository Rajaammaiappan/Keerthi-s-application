"""
Generates a small demo workbook (in-memory) that exercises every rule the
app implements: multiple customers/locations/periods, all FTE categories,
positive/zero/negative FTE, multi-location customers, missing base flag,
and multiple base flags. Used only for the "Try with sample data" button —
never mixed with a user's uploaded data.
"""
from __future__ import annotations

import io
import random

import pandas as pd

CUSTOMERS = ["Ford", "JLR", "Toyota", "Airbus"]
LOCATIONS = ["Cob", "Ban", "Hyd", "Pun", "Mun"]
PERIODS = ["Dec_2025", "Mar_2026", "Jun_2026"]
VM_PRODUCTS = ["BS/OSS/AERO", "BS/OSS/ICE", "BS/OSS/EV"]
COMPONENTS = ["DIG/DATA", "DIG/APP", "NET/CTRL/SW"]
COUNTRIES = ["India", "France", "Morocco"]


def generate_sample_workbook() -> bytes:
    random.seed(42)
    rows = []
    sno = 1
    customer_base_loc = {
        "Ford": "Cob",
        "JLR": "Ban",
        "Toyota": None,       # intentionally missing base -> validation warning
        "Airbus": "Hyd",
    }

    for customer in CUSTOMERS:
        base_loc = customer_base_loc[customer]
        active_locations = random.sample(LOCATIONS, k=3)
        if base_loc and base_loc not in active_locations:
            active_locations.append(base_loc)
        for loc in active_locations:
            row = {
                "S.No": sno,
                "VM Product": random.choice(VM_PRODUCTS),
                "Customer Account": customer,
                "Component": random.choice(COMPONENTS),
                "Country": random.choice(COUNTRIES),
                "Location": loc,
            }
            if customer == "JLR":
                # intentionally create MULTIPLE base locations for validation demo
                row["Base location"] = "Yes" if loc in (base_loc, "Hyd") else "No"
            else:
                row["Base location"] = "Yes" if loc == base_loc else "No"

            fte_trend = random.randint(5, 20)
            for i, period in enumerate(PERIODS):
                internal = max(fte_trend - i * 2, 0)
                swc = random.randint(0, 4)
                external = random.randint(0, 3)
                others = 0
                if customer == "Toyota" and loc == active_locations[0] and i == 2:
                    external = -2  # intentional negative FTE edge case
                total = internal + swc + external + others
                row[f"FTE_{period}_Internal"] = internal
                row[f"FTE_{period}_SWC"] = swc
                row[f"FTE_{period}_External"] = external
                row[f"FTE_{period}_Others"] = others
                row[f"FTE_{period}"] = total
            rows.append(row)
            sno += 1

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="FTE_Data")
    buf.seek(0)
    return buf.read()
