"""
Reads an uploaded Excel workbook and converts it into a normalized,
long-format dataset, regardless of exact column order/naming, number of
rows, number of locations, number of periods, etc.

This is the only place that touches raw Excel structure. Everything
downstream (mapping_engine, analysis_engine) works purely off the
normalized Dataset object.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.models import Dataset, DetectedColumns
from app.utils import find_column, parse_fte_column, normalize_base_flag

logger = logging.getLogger("fte_planner.excel_processor")

REQUIRED_FIELDS = ["customer_account", "location"]


class ExcelProcessingError(Exception):
    """Raised for any problem that should surface as a friendly error page."""


# Some workbooks (e.g. the standard "FTE_Location_Planner" template) use a
# two-row header: row 1 has the period label merged across a group of
# columns (e.g. "FTE_Dec_2025" spanning 5 columns), row 2 has the
# per-column breakdown ("Internal", "SWC", "External", "Others", and the
# period's own total repeated). Plain pandas can't read that directly, so
# it's flattened here into single-row headers like "FTE_Dec_2025_Internal"
# that `parse_fte_column` already understands.
CATEGORY_HEADER_ALIASES = {"internal", "swc", "external", "others", "other"}


def _looks_like_two_row_header(raw: pd.DataFrame) -> bool:
    """True if row 2 (index 1) looks like Internal/SWC/External/Others sub-headers."""
    if len(raw) < 3:
        return False
    row2 = raw.iloc[1]
    matches = sum(
        1 for v in row2
        if isinstance(v, str) and v.strip().lower() in CATEGORY_HEADER_ALIASES
    )
    return matches >= 2


def _flatten_two_row_header(raw: pd.DataFrame) -> pd.DataFrame:
    row1 = list(raw.iloc[0])
    row2 = list(raw.iloc[1])

    # Excel merged cells only store a value in the top-left cell of the
    # range; the rest read back as NaN. Forward-fill row 1 so every column
    # in a merged period group picks up that group's label.
    filled_row1 = []
    last = None
    for v in row1:
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
            filled_row1.append(last)
        else:
            last = v
            filled_row1.append(v)

    combined = []
    for top, sub in zip(filled_row1, row2):
        if sub is not None and not (isinstance(sub, float) and pd.isna(sub)) and str(sub).strip() != "":
            sub_text = str(sub).strip()
            if sub_text.lower() in CATEGORY_HEADER_ALIASES:
                combined.append(f"{top}_{sub_text}")
            else:
                # The group's total sub-header repeats the period label
                # itself (e.g. "FTE_Dec_2025") -- use it as-is.
                combined.append(sub_text)
        else:
            combined.append(top)

    data = raw.iloc[2:].reset_index(drop=True)
    data.columns = [str(c).strip() if c is not None else "" for c in combined]
    return data


def _read_sheet(xls_or_path, sheet_name=None, engine: str | None = None) -> pd.DataFrame:
    kwargs = {"header": None}
    if sheet_name is not None:
        kwargs["sheet_name"] = sheet_name
    if engine is not None:
        kwargs["engine"] = engine
    raw = pd.read_excel(xls_or_path, **kwargs)
    if _looks_like_two_row_header(raw):
        return _flatten_two_row_header(raw)

    header_kwargs = {k: v for k, v in kwargs.items() if k != "header"}
    return pd.read_excel(xls_or_path, **header_kwargs)


def _read_workbook(path: Path) -> pd.DataFrame:
    try:
        if path.suffix.lower() == ".xls":
            df = _read_sheet(path, engine="xlrd")
        else:
            # Pick the first sheet that actually looks like tabular data
            # (more than 1 column, header row present). The `with` here
            # matters on Windows: an unclosed ExcelFile keeps the temp
            # upload locked, so the caller's later os.unlink() fails.
            with pd.ExcelFile(path) as xls:
                best_sheet = None
                best_cols = -1
                for name in xls.sheet_names:
                    try:
                        preview = pd.read_excel(xls, sheet_name=name, nrows=5)
                    except Exception:
                        continue
                    if preview.shape[1] > best_cols and preview.shape[1] > 2:
                        best_cols = preview.shape[1]
                        best_sheet = name
                if best_sheet is None:
                    best_sheet = xls.sheet_names[0]
                df = _read_sheet(xls, sheet_name=best_sheet)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed reading workbook")
        raise ExcelProcessingError("File is corrupted or not a valid Excel file") from exc

    if df.empty or df.shape[1] < 2:
        raise ExcelProcessingError("Excel format is invalid or file has no data")
    return df


def detect_columns(df: pd.DataFrame) -> DetectedColumns:
    cols = list(df.columns)
    detected = DetectedColumns(
        sno=find_column(cols, "sno"),
        vm_product=find_column(cols, "vm_product"),
        customer_account=find_column(cols, "customer_account"),
        component=find_column(cols, "component"),
        country=find_column(cols, "country"),
        location=find_column(cols, "location"),
        base_location=find_column(cols, "base_location"),
    )

    consumed = {
        v for v in [
            detected.sno, detected.vm_product, detected.customer_account,
            detected.component, detected.country, detected.location,
            detected.base_location,
        ] if v
    }

    fte_columns: dict[str, dict[str, str]] = {}
    unmatched = []
    for col in cols:
        if col in consumed:
            continue
        parsed = parse_fte_column(col)
        if parsed is None:
            unmatched.append(col)
            continue
        period_label, category, sort_key = parsed
        bucket = fte_columns.setdefault(period_label, {"__sort_key__": sort_key})
        bucket[category] = col

    detected.fte_columns = fte_columns
    detected.unmatched_columns = unmatched

    missing = [f for f in REQUIRED_FIELDS if getattr(detected, f) is None]
    if not fte_columns:
        missing.append("fte_columns")
    detected.missing_required = missing
    return detected


def _melt_to_long(df: pd.DataFrame, detected: DetectedColumns) -> pd.DataFrame:
    dim_map = {
        "SNo": detected.sno,
        "VM_Product": detected.vm_product,
        "Customer_Account": detected.customer_account,
        "Component": detected.component,
        "Country": detected.country,
        "Location": detected.location,
    }
    dim_cols = {k: v for k, v in dim_map.items() if v}

    work = pd.DataFrame(index=df.index)
    for logical_name, actual_col in dim_cols.items():
        work[logical_name] = df[actual_col].astype(str).str.strip()

    if detected.base_location:
        work["Base_Location_Flag"] = df[detected.base_location].apply(normalize_base_flag)
    else:
        work["Base_Location_Flag"] = None

    work["_row_id"] = df.index

    periods_sorted = sorted(
        detected.fte_columns.items(), key=lambda kv: kv[1]["__sort_key__"]
    )

    records = []
    for period_label, cat_cols in periods_sorted:
        for category, col_name in cat_cols.items():
            if category == "__sort_key__":
                continue
            values = pd.to_numeric(df[col_name], errors="coerce")
            for idx in df.index:
                fte_val = values.loc[idx]
                if pd.isna(fte_val):
                    continue
                records.append((idx, period_label, category, float(fte_val)))

    long_records = pd.DataFrame(
        records, columns=["_row_id", "Period", "Category", "FTE"]
    )
    long_df = long_records.merge(work, on="_row_id", how="left")
    return long_df


def process_workbook(path: Path, original_filename: str) -> Dataset:
    df = _read_workbook(path)
    # Drop fully-empty rows/columns that sometimes trail an Excel export
    df = df.dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]

    detected = detect_columns(df)
    if detected.missing_required:
        pretty = ", ".join(detected.missing_required)
        raise ExcelProcessingError(f"Required column(s) could not be detected: {pretty}")

    long_df = _melt_to_long(df, detected)

    warnings = []
    if not detected.base_location:
        warnings.append(
            "No 'Base location' column was found — base-location markers cannot be shown."
        )
    if detected.unmatched_columns:
        warnings.append(
            f"{len(detected.unmatched_columns)} column(s) were not recognized and were ignored: "
            + ", ".join(str(c) for c in detected.unmatched_columns[:10])
            + ("..." if len(detected.unmatched_columns) > 10 else "")
        )

    periods_sorted = [
        p for p, _ in sorted(detected.fte_columns.items(), key=lambda kv: kv[1]["__sort_key__"])
    ]
    categories_present = set()
    for cat_cols in detected.fte_columns.values():
        categories_present.update(k for k in cat_cols if k != "__sort_key__")
    ordered_categories = [c for c in ["Internal", "SWC", "External", "Others"] if c in categories_present]
    if "Total" in categories_present:
        ordered_categories.append("Total")
    elif ordered_categories:
        # No explicit total column — we'll compute Total as a derived sum downstream.
        ordered_categories.append("Total")

    dims = {}
    for dim in ["VM_Product", "Customer_Account", "Component", "Country", "Location"]:
        if dim in long_df.columns:
            dims[dim] = sorted(x for x in long_df[dim].dropna().unique().tolist() if x and x != "nan")

    negative_rows = long_df[long_df["FTE"] < 0]
    if not negative_rows.empty:
        warnings.append(
            f"{len(negative_rows)} record(s) contain negative FTE values — flagged for review."
        )

    return Dataset(
        raw_df=df,
        long_df=long_df,
        dims=dims,
        periods=periods_sorted,
        categories=ordered_categories,
        warnings=warnings,
        detected_columns=detected,
        source_filename=original_filename,
    )
