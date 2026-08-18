# Build Prompt: OptiView — FTE Location & Workforce Planning Tool

Build a local-only web application called **OptiView** that turns a raw workforce/FTE
Excel tracker into an interactive Location Mapping Matrix and workforce-planning
dashboard. This app runs entirely on the user's own machine via `localhost` —
no cloud deployment, no hosting config, no external network calls, no telemetry.
Everything must work fully offline once the local server is running.

## Tech approach

- Python web backend serving server-rendered HTML pages plus a small JSON API
  that the frontend calls for live filtering (no full page reloads).
- Server-side templating for the HTML pages, one shared base layout that every
  page extends (top navigation bar, page content block, footer).
- Plain HTML/CSS/JavaScript on the frontend — no frontend framework, no build
  step, no bundler. All interactivity is hand-written vanilla JS calling the
  JSON API and re-rendering DOM fragments.
- Excel file parsing and analysis on the backend using a dataframe library.
- The whole thing must be capable of running as a **single self-contained
  script** with no external template/static-file directories required (i.e.
  the HTML/CSS/JS can be embedded as in-memory strings rather than loaded from
  disk), so it can optionally be packaged into one portable file later. Do not
  design around any cloud platform's file layout or environment variables.

## Data model

Nothing about customers, locations, periods, or categories is hard-coded —
everything is detected dynamically from whatever Excel file is uploaded.

Expected logical columns (any order, flexible header spelling):
`S.No, VM Product, Customer Account, Component, Country, Location, Base location`,
plus one or more FTE columns per period. Each period optionally breaks down into
four categories — **Internal, SWC, External, Others** — plus a period total.

Support **two different header layouts** for the FTE columns, auto-detected:
1. **Flat single-row headers**, e.g. `FTE_Dec_2025_Internal`, `FTE_Dec_2025_SWC`,
   `FTE_Dec_2025_External`, `FTE_Dec_2025_Others`, and `FTE_Dec_2025` for the total.
   Parse the month/year and category out of the column name with a regex; sort
   periods chronologically regardless of the order they appear in the sheet.
2. **Two-row merged headers** (a common template): row 1 has the period label
   merged across a group of 5 columns (e.g. `FTE_Dec_2025` spanning one block),
   row 2 has `Internal | SWC | External | Others | <period total repeated>`
   as sub-headers under that group. Detect this layout automatically (row 2
   containing category words is the signal), forward-fill the merged period
   label across the group, and flatten it into the same internal representation
   as format 1 before the rest of the app touches it.

`Base location` should accept Yes/No, Y/N, TRUE/FALSE, 1/0 as equivalent.

Normalize the parsed workbook into one long/tidy in-memory table: one row per
(dimension columns..., Period, Category, FTE value), so every downstream
feature works off one consistent shape regardless of which header layout or
column order the source file used.

## Core capabilities (build these as separate, composable modules)

- **Column/period detection** — flexible header matching (synonyms for each
  dimension column), FTE column parsing for both layouts above, warnings for
  unrecognized columns or missing required fields (Customer Account, Location).
- **Filtering** — filter the normalized dataset by any dimension (VM Product,
  Customer Account, Component, Country, Location), by period, and by category
  (Total / Internal / SWC / External / Others).
- **Location Mapping Matrix** — Customer Account (rows) × Location (columns).
  Mark each cell as the designated base location, a supporting/additional
  location, or empty, with the FTE value(s) for whichever period/category is
  selected. Flag customers with zero or multiple base locations as a data
  quality issue.
- **Breakdown view** — a second matrix mode where each cell shows the full
  Internal + SWC + External + Others = Total composition, color-coded per
  category (pick a distinct color for each of the four categories and reuse
  those exact colors everywhere breakdown data appears: matrix cells, charts,
  legends), with a legend explaining the colors.
- **Summary analytics** — total FTE / customer count / location count /
  base-location count cards; per-location and per-customer summary tables;
  period-over-period comparison (Growth / Reduction / New / Discontinued / No
  Change classification); location capacity/demand classification (Growth /
  Stable / Potential Released Capacity based on FTE change between two
  periods); a simple transfer-opportunity matcher that pairs locations
  releasing capacity against locations with growing demand, ranked by the
  smaller of the two magnitudes.
- **Category breakdown analytics** — total FTE by category (for a pie/donut
  chart) and FTE by category per location (for a stacked bar chart), computed
  independently of whichever category filter is currently selected.
- **Data quality report** — customers with no base location or multiple base
  locations, and any records with negative FTE values.
- **Manual transfer mappings** — let the user record their own from/to
  location + customer + FTE amount + notes as a simple in-memory list, viewable
  and deletable.
- **Excel export** — build a downloadable multi-sheet analyzed workbook:
  the current matrix (in whichever view mode — normal or breakdown — is active
  on screen, so the export always matches what the user is looking at),
  location summary, customer summary, period comparison, capacity view,
  transfer opportunities, manual mappings, data-quality findings, and the raw
  uploaded data for reference. Style header rows, autosize columns.
- **In-app assistant** — a floating chat-style widget (a small round button in
  a corner of the screen, present on every page, opening a popup panel on
  click — not a separate page/tab) that answers questions about the currently
  loaded dataset. No external AI/LLM call: every answer is computed locally
  from the same analytics functions above, so answers are exact and
  reproducible. Provide:
  - A row of quick-question pill buttons covering the most useful canned
    questions (total FTE, which location/customer has the most FTE, any
    base-location or negative-FTE data-quality issues, which locations are
    releasing capacity vs. growing between two periods, transfer
    opportunities, the category split, which location relies most on
    External FTE).
  - A "build your own" mode: a dropdown of broader metrics (full location
    breakdown, full customer breakdown, full category breakdown, base-location
    status for every customer, period-over-period change, transfer
    opportunities) that runs against whatever period/date-range is currently
    set, returning the full table rather than just a top result.
  - A free-text box: typed input resolves locally, in order, to (a) an exact
    customer or location name for an instant lookup, (b) a keyword match
    against the canned questions, or (c) a friendly fallback suggesting the
    quick options — no natural-language model involved.
  - Every answer renders as a short plain-language sentence plus an optional
    data table, appended to a running feed within the popup.

## Pages

- **Home / Upload** — drag-and-drop (or click-to-browse) Excel upload with
  friendly validation errors; a short note on the expected column shape.
- **Dashboard** — summary cards, the category pie chart, the category-by-location
  stacked bar chart, a preview of the location mapping matrix, and the
  location/customer summary tables.
- **Location Mapping** — the full matrix with a view toggle: status-only
  (★ base / ✓ supporting), FTE numbers only, both combined, and the color-coded
  breakdown view described above.
- **FTE Analysis** — period-over-period comparison table and the
  location capacity/demand view, with From/To period pickers.
- **Transfer Mapping** — the automatic transfer-opportunity table plus the
  manual-mapping entry form and list.
- **Data Quality** — the full data-quality report.
- **Management View** — a simplified, less technical rollup of the above for
  a non-technical audience.

Every page (except the upload page) shares one filter bar: period, FTE
category, and every dimension filter, all live/AJAX — changing a filter
re-fetches and re-renders in place without a full page reload. Every page also
carries a link to download the analyzed Excel export with the current filters
baked in.

## Design

Clean, professional look: a navy/blue color scheme, a sticky top navigation
bar with the app name as the brand mark, card-based panels with subtle
shadows and rounded corners, a consistent color per FTE category used
everywhere that category appears (matrix breakdown cells, pie chart, bar
chart, legends), accessible contrast, and a responsive layout that degrades
gracefully on narrower viewports. No sample-data generator or demo button —
the only way into the app is uploading a real file.

## Constraints

- Local-disk only: no cloud provider config, no `Procfile`-style deploy
  manifests, no environment-variable-driven service URLs, no external API
  calls of any kind (including no telemetry/analytics beacons). The app must
  be fully usable with the network disconnected once it's running.
- Uploaded files are processed as ephemeral temp files and discarded
  immediately after parsing; the parsed dataset lives only in server memory
  for the duration of the browser session (a session cookie is enough — no
  database).
- Do not hard-code any customer names, location names, periods, or category
  labels anywhere in the code — everything must come from whatever file the
  user uploads.
