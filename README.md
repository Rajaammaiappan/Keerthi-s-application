# OptiView — FTE Location & Workforce Planning Tool

A Python/FastAPI web application that turns a raw workforce/FTE Excel tracker
into an interactive **Location Mapping Matrix** and workforce-planning
dashboard: which locations support which customer accounts, where the base
location is, how FTE shifts across periods, and where transfer opportunities
exist.

Nothing about customers, locations, periods, or categories is hard-coded —
everything is detected dynamically from whatever Excel file is uploaded.

## What the application does

1. You upload a workforce/FTE Excel file (`.xlsx` / `.xls`).
2. The app detects the dimension columns (Customer Account, Location, Base
   location, VM Product, Component, Country) and every `FTE_<Period>[_<Category>]`
   column, regardless of column order or exact naming.
3. It builds a normalized dataset and shows:
   - **Dashboard** — summary cards + a matrix + location/customer summaries
   - **Location Mapping** — the full Customer × Location matrix with a
     Status / FTE / Status+FTE view toggle
   - **FTE Analysis** — period-over-period comparison and location
     capacity/demand view
   - **Transfer Mapping** — automatically identified transfer opportunities
     (locations releasing capacity matched against locations with growing
     demand), plus a form to record manual mapping decisions
   - **Data Quality** — accounts with no base location or multiple base
     locations, and any negative-FTE records
   - **Management View** — a simplified, non-technical summary
4. Any view can be filtered by Customer Account, VM Product, Component,
   Country, Location, Period, and FTE Type (Total/Internal/SWC/External/Others).
5. You can download a fully analyzed multi-sheet Excel workbook at any time.

## Features

- Drag-and-drop Excel upload with validation and friendly error messages
- Dynamic column & FTE-period/category detection (works with different
  workbooks — different customers, locations, periods, row counts)
- Base-location validation: flags accounts with **no** base location or
  **multiple** base locations (never silently guesses)
- Live filtering (AJAX, no page reloads) across every dimension
- Period comparison (Growth / Reduction / New / Discontinued / No Change)
- Location capacity/demand classification (Growth / Stable / Potential
  Released Capacity)
- Automatic transfer-opportunity matching + manual mapping entry
- One-click download of a multi-sheet analyzed Excel report

## Project structure

```
fte-location-planner/
├── app/
│   ├── main.py              # FastAPI app & routes (pages + JSON API)
│   ├── models.py             # Dataclasses for the normalized dataset
│   ├── excel_processor.py    # Upload parsing & dynamic column detection
│   ├── mapping_engine.py     # Filters, base-location logic, matrix builder
│   ├── analysis_engine.py    # Summaries, comparison, capacity, transfers
│   ├── export_engine.py      # Builds the downloadable analyzed workbook
│   ├── utils.py              # Column matching, normalization, session store
│   ├── templates/            # Jinja2 HTML templates
│   └── static/                # CSS + vanilla JS
├── tests/                    # pytest suite
├── requirements.txt
├── render.yaml
├── Procfile
└── README.md
```

## Local installation

```bash
python -m venv venv
```

macOS/Linux:
```bash
source venv/bin/activate
```

Windows:
```bash
venv\Scripts\activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Run:
```bash
uvicorn app.main:app --reload
```

Open:
```
http://127.0.0.1:8000
```

## Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Render deployment

1. Create a GitHub repository and push this project to it.
2. In Render, click **New → Web Service** and select the repository.
3. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Environment:** Python 3.11
4. Deploy. Render sets the `PORT` environment variable automatically — the
   app never hard-codes a port.
5. Once live, open the Render URL, upload your Excel file, and verify the
   dashboard, matrix, filters, period switching, and export all work.

The included `render.yaml` lets you use Render's "Blueprint" deploy option
instead of configuring the service by hand.

## Expected Excel structure

Any order, flexible column naming:

```
S.No | VM Product | Customer Account | Component | Country | Location | Base location
FTE_<Month>_<Year>_Internal | FTE_<Month>_<Year>_SWC | FTE_<Month>_<Year>_External
FTE_<Month>_<Year>_Others | FTE_<Month>_<Year>
```

`Base location` accepts Yes/No, Y/N, TRUE/FALSE, or 1/0.

Any number of periods, categories, locations, and customer accounts is
supported — nothing is hard-coded.

**Two-row header template is also supported.** The standard
`FTE_Location_Planner` template merges the period label across a group of
columns on row 1 (e.g. `FTE_Dec_2025` spanning 5 columns) and puts the
`Internal | SWC | External | Others | <period total>` sub-headers on row 2.
The app detects this layout automatically and flattens it before parsing —
no manual conversion needed.

## Notes on data storage

The app keeps the parsed dataset in memory for the duration of your browser
session (via a cookie), so no database is required for this use case. If you
need multi-user persistence across server restarts, the natural next step is
swapping `app/utils.py`'s `DatasetStore` for a database- or file-backed store.
