from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import excel_processor, mapping_engine, analysis_engine as ae, export_engine
from app.excel_processor import ExcelProcessingError
from app.utils import store, SESSION_COOKIE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fte_planner")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="FTE Location Mapping & Workforce Planning Tool")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# manual mappings: dataset_id -> list[dict]
_manual_mappings: dict[str, list[dict]] = {}

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
MAX_UPLOAD_MB = 25


def get_dataset(request: Request):
    dataset_id = request.cookies.get(SESSION_COOKIE)
    if not dataset_id:
        return None, None
    dataset = store.get(dataset_id)
    return dataset_id, dataset


def require_dataset(request: Request):
    dataset_id, dataset = get_dataset(request)
    if dataset is None:
        raise HTTPException(status_code=400, detail="No dataset uploaded yet")
    return dataset_id, dataset


def parse_filters(request: Request) -> dict:
    q = request.query_params
    filters = {}
    for dim in mapping_engine.FILTERABLE_DIMS:
        values = q.getlist(dim)
        values = [v for v in values if v and v != "All"]
        if values:
            filters[dim] = values
    return filters


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    dataset_id, dataset = get_dataset(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "has_dataset": dataset is not None,
        "filename": dataset.source_filename if dataset else None,
    })


@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "Unsupported file type. Please upload a .xlsx or .xls file.",
        }, status_code=400)

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": f"File is too large. Maximum size is {MAX_UPLOAD_MB} MB.",
        }, status_code=400)

    tmp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    tmp_path.write_bytes(contents)

    try:
        dataset = excel_processor.process_workbook(tmp_path, file.filename)
    except ExcelProcessingError as exc:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": str(exc),
            "detail": (
                "Possible reasons: required column is missing, Excel format is invalid, "
                "FTE columns could not be detected, or the file is corrupted."
            ),
        }, status_code=400)
    except Exception:
        logger.exception("Unexpected error processing workbook")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "Unable to process the uploaded Excel file.",
            "detail": "An unexpected error occurred. Please check the file and try again.",
        }, status_code=500)
    finally:
        tmp_path.unlink(missing_ok=True)

    dataset_id = store.new_id()
    store.put(dataset_id, dataset)
    _manual_mappings[dataset_id] = []

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(SESSION_COOKIE, dataset_id, max_age=60 * 60 * 8)
    return response


@app.post("/reset")
async def reset(request: Request):
    dataset_id, _ = get_dataset(request)
    if dataset_id:
        store.delete(dataset_id)
        _manual_mappings.pop(dataset_id, None)
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


def _common_context(request: Request, dataset):
    return {
        "request": request,
        "filename": dataset.source_filename,
        "periods": dataset.periods,
        "categories": dataset.categories,
        "dims": dataset.dims,
        "warnings": dataset.warnings,
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    dataset_id, dataset = get_dataset(request)
    if dataset is None:
        return RedirectResponse(url="/")
    ctx = _common_context(request, dataset)
    return templates.TemplateResponse("dashboard.html", ctx)


@app.get("/mapping", response_class=HTMLResponse)
async def mapping_page(request: Request):
    dataset_id, dataset = get_dataset(request)
    if dataset is None:
        return RedirectResponse(url="/")
    ctx = _common_context(request, dataset)
    return templates.TemplateResponse("mapping.html", ctx)


@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request):
    dataset_id, dataset = get_dataset(request)
    if dataset is None:
        return RedirectResponse(url="/")
    ctx = _common_context(request, dataset)
    return templates.TemplateResponse("analysis.html", ctx)


@app.get("/transfer", response_class=HTMLResponse)
async def transfer_page(request: Request):
    dataset_id, dataset = get_dataset(request)
    if dataset is None:
        return RedirectResponse(url="/")
    ctx = _common_context(request, dataset)
    return templates.TemplateResponse("transfer.html", ctx)


@app.get("/data-quality", response_class=HTMLResponse)
async def data_quality_page(request: Request):
    dataset_id, dataset = get_dataset(request)
    if dataset is None:
        return RedirectResponse(url="/")
    ctx = _common_context(request, dataset)
    report = ae.data_quality_report(dataset.long_df, dataset.warnings)
    ctx["report"] = report
    return templates.TemplateResponse("data_quality.html", ctx)


@app.get("/management", response_class=HTMLResponse)
async def management_page(request: Request):
    dataset_id, dataset = get_dataset(request)
    if dataset is None:
        return RedirectResponse(url="/")
    ctx = _common_context(request, dataset)
    return templates.TemplateResponse("management.html", ctx)


# ---------------------------------------------------------------------------
# JSON APIs (consumed by static/js/app.js for live filtering)
# ---------------------------------------------------------------------------

@app.get("/api/meta")
async def api_meta(request: Request):
    dataset_id, dataset = require_dataset(request)
    return {
        "periods": dataset.periods,
        "categories": dataset.categories,
        "dims": dataset.dims,
        "warnings": dataset.warnings,
    }


@app.get("/api/matrix")
async def api_matrix(request: Request, period: str, category: str = "Total"):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return build_json_safe(mapping_engine.build_matrix(dataset.long_df, filters, period, category))


@app.get("/api/matrix-breakdown")
async def api_matrix_breakdown(request: Request, period: str):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return build_json_safe(mapping_engine.build_matrix_breakdown(dataset.long_df, filters, period))


@app.get("/api/category-breakdown")
async def api_category_breakdown(request: Request, period: str):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return build_json_safe(ae.category_breakdown(dataset.long_df, filters, period))


@app.get("/api/summary")
async def api_summary(request: Request, period: str, category: str = "Total"):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return ae.summary_cards(dataset.long_df, filters, period, category)


@app.get("/api/location-summary")
async def api_location_summary(request: Request, period: str, category: str = "Total"):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return ae.location_summary(dataset.long_df, filters, period, category)


@app.get("/api/customer-summary")
async def api_customer_summary(request: Request, period: str, category: str = "Total"):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return ae.customer_summary(dataset.long_df, filters, period, category)


@app.get("/api/comparison")
async def api_comparison(request: Request, from_period: str, to_period: str, category: str = "Total"):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return ae.period_comparison(dataset.long_df, filters, from_period, to_period, category)


@app.get("/api/capacity")
async def api_capacity(request: Request, from_period: str, to_period: str, category: str = "Total"):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return ae.capacity_view(dataset.long_df, filters, from_period, to_period, category)


@app.get("/api/transfer-opportunities")
async def api_transfer(request: Request, from_period: str, to_period: str, category: str = "Total"):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    return ae.identify_transfer_opportunities(dataset.long_df, filters, from_period, to_period, category)


@app.get("/api/manual-mapping")
async def list_manual_mapping(request: Request):
    dataset_id, dataset = require_dataset(request)
    return _manual_mappings.get(dataset_id, [])


@app.post("/api/manual-mapping")
async def add_manual_mapping(
    request: Request,
    from_customer: str = Form(...),
    from_location: str = Form(...),
    to_customer: str = Form(...),
    to_location: str = Form(...),
    fte_amount: float = Form(...),
    notes: str = Form(""),
):
    dataset_id, dataset = require_dataset(request)
    entry = {
        "id": uuid.uuid4().hex[:8],
        "from_customer": from_customer,
        "from_location": from_location,
        "to_customer": to_customer,
        "to_location": to_location,
        "fte_amount": fte_amount,
        "notes": notes,
    }
    _manual_mappings.setdefault(dataset_id, []).append(entry)
    return entry


@app.delete("/api/manual-mapping/{mapping_id}")
async def delete_manual_mapping(request: Request, mapping_id: str):
    dataset_id, dataset = require_dataset(request)
    mappings = _manual_mappings.get(dataset_id, [])
    _manual_mappings[dataset_id] = [m for m in mappings if m["id"] != mapping_id]
    return {"ok": True}


@app.get("/export")
async def export(
    request: Request,
    period: str,
    category: str = "Total",
    from_period: Optional[str] = None,
    to_period: Optional[str] = None,
):
    dataset_id, dataset = require_dataset(request)
    filters = parse_filters(request)
    manual_mappings = _manual_mappings.get(dataset_id, [])
    content = export_engine.build_export_workbook(
        dataset, filters, period, category, from_period, to_period, manual_mappings
    )
    filename = "FTE_Location_Planning_Analysis.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def build_json_safe(obj):
    """Recursively convert numpy/pandas scalar types to plain Python for JSON."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: build_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [build_json_safe(v) for v in obj]
    if isinstance(obj, (np.generic,)):
        return obj.item()
    return obj


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("error.html", {
        "request": request, "message": "Page not found.", "detail": None,
    }, status_code=404)
