/* FTE Location & Workforce Planner — client-side logic.
   Vanilla JS only, no frameworks. Talks to the JSON API under /api/*. */

const FTE = (() => {
  const DIM_LABELS = {
    Customer_Account: "Customer Account",
    VM_Product: "VM Product",
    Component: "Component",
    Country: "Country",
    Location: "Location",
  };

  // Fixed color per FTE category, used consistently by the pie chart, bar
  // chart, matrix breakdown cells, and every legend.
  const CATEGORY_COLORS = {
    Internal: "#2f6fed",
    SWC: "#8b5cf6",
    External: "#f59e0b",
    Others: "#64748b",
  };
  function categoryColor(cat) { return CATEGORY_COLORS[cat] || "#94a3b8"; }

  const state = {
    periods: [],
    categories: [],
    dims: {},
    filters: {},
    period: null,
    category: "Total",
    view: "status",
    fromPeriod: null,
    toPeriod: null,
  };

  function qs(sel, root = document) { return root.querySelector(sel); }
  function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  async function api(path, params = {}) {
    const url = new URL(path, window.location.origin);
    for (const [key, val] of Object.entries(params)) {
      if (val === undefined || val === null || val === "") continue;
      if (Array.isArray(val)) {
        val.forEach(v => url.searchParams.append(key, v));
      } else {
        url.searchParams.set(key, val);
      }
    }
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  }

  function currentFilterParams() {
    return { ...state.filters };
  }

  // -------------------------------------------------------------------
  // Filter bar
  // -------------------------------------------------------------------
  function buildFilterBar(onChange) {
    const bar = qs("#filter-bar");
    if (!bar) return;
    state.periods = JSON.parse(bar.dataset.periods || "[]");
    state.categories = JSON.parse(bar.dataset.categories || "[]");
    state.dims = JSON.parse(bar.dataset.dims || "{}");
    state.period = state.periods[state.periods.length - 1] || null;
    state.category = state.categories.includes("Total") ? "Total" : (state.categories[0] || "Total");
    state.fromPeriod = state.periods[0] || null;
    state.toPeriod = state.periods[state.periods.length - 1] || null;

    bar.innerHTML = "";

    // Period selector
    if (!bar.dataset.simple) {
      bar.appendChild(makeSelectField("Period", state.periods, state.period, val => {
        state.period = val; onChange();
      }));
    }
    // Category selector
    bar.appendChild(makeSelectField("FTE Type", state.categories, state.category, val => {
      state.category = val; onChange();
    }));
    // Dimension filters
    for (const [dim, values] of Object.entries(state.dims)) {
      bar.appendChild(makeMultiSelectField(DIM_LABELS[dim] || dim, dim, values, onChange));
    }

    // Populate from/to period selects if present on this page
    const fromSel = qs("#from-period");
    const toSel = qs("#to-period");
    if (fromSel && toSel) {
      fromSel.innerHTML = state.periods.map(p => `<option value="${p}">${p}</option>`).join("");
      toSel.innerHTML = state.periods.map(p => `<option value="${p}">${p}</option>`).join("");
      fromSel.value = state.fromPeriod;
      toSel.value = state.toPeriod;
      fromSel.addEventListener("change", () => { state.fromPeriod = fromSel.value; onChange(); });
      toSel.addEventListener("change", () => { state.toPeriod = toSel.value; onChange(); });
    }
  }

  function makeSelectField(label, options, current, onChange) {
    const wrap = document.createElement("div");
    wrap.className = "filter-field";
    const lbl = document.createElement("label");
    lbl.textContent = label;
    const sel = document.createElement("select");
    options.forEach(opt => {
      const o = document.createElement("option");
      o.value = opt; o.textContent = opt;
      if (opt === current) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => onChange(sel.value));
    wrap.appendChild(lbl); wrap.appendChild(sel);
    return wrap;
  }

  function makeMultiSelectField(label, dim, values, onChange) {
    const wrap = document.createElement("div");
    wrap.className = "filter-field";
    const lbl = document.createElement("label");
    lbl.textContent = label + " (Ctrl/Cmd+click for multiple)";
    const sel = document.createElement("select");
    sel.multiple = true;
    sel.size = Math.min(4, Math.max(2, values.length > 6 ? 4 : values.length));
    values.forEach(v => {
      const o = document.createElement("option");
      o.value = v; o.textContent = v;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => {
      const selected = Array.from(sel.selectedOptions).map(o => o.value);
      if (selected.length) state.filters[dim] = selected;
      else delete state.filters[dim];
      onChange();
    });
    wrap.appendChild(lbl); wrap.appendChild(sel);
    return wrap;
  }

  // -------------------------------------------------------------------
  // Matrix rendering
  // -------------------------------------------------------------------
  function renderMatrix(matrix) {
    const table = qs("#matrix-table");
    if (!table) return;
    if (!matrix.customers.length || !matrix.locations.length) {
      table.innerHTML = "<tr><td>No data for the current filters.</td></tr>";
      return;
    }
    let html = "<thead><tr><th>Customer Account</th>";
    matrix.locations.forEach(loc => { html += `<th>${loc}</th>`; });
    html += "</tr></thead><tbody>";

    matrix.customers.forEach(cust => {
      const warning = matrix.customer_warnings[cust];
      const custLabel = warning ? `⚠ ${cust}` : cust;
      html += `<tr><th class="${warning ? 'customer-col-warn' : ''}" title="${warning || ''}">${custLabel}</th>`;
      matrix.locations.forEach(loc => {
        const cell = matrix.cells[cust][loc];
        html += renderCell(cell);
      });
      html += "</tr>";
    });
    html += "</tbody>";
    table.innerHTML = html;
  }

  function renderCell(cell) {
    const view = state.view || "status";
    const fteVal = cell.fte;
    const isNegative = fteVal !== null && fteVal < 0;
    let cls = "empty-cell";
    let content = "-";

    if (isNegative) {
      cls = "negative-cell";
      content = view === "status" ? "⚠" : `${fteVal}`;
      if (view === "both") content = `⚠<span class="fte-sub">${fteVal} FTE</span>`;
    } else if (cell.is_base) {
      cls = "base-cell";
      if (view === "status") content = "★ BASE";
      else if (view === "fte") content = cell.has_fte ? `${fteVal}` : "-";
      else content = `★ BASE${cell.has_fte ? `<span class="fte-sub">${fteVal} FTE</span>` : ""}`;
    } else if (cell.has_fte) {
      cls = "support-cell";
      if (view === "status") content = "✓";
      else if (view === "fte") content = `${fteVal}`;
      else content = `✓<span class="fte-sub">${fteVal} FTE</span>`;
    }
    return `<td class="${cls}">${content}</td>`;
  }

  // -------------------------------------------------------------------
  // Matrix breakdown view (Internal + SWC + External + Others = Total,
  // color-coded per category)
  // -------------------------------------------------------------------
  function renderMatrixBreakdown(matrix) {
    const table = qs("#matrix-table");
    const legendEl = qs("#matrix-category-legend");
    if (!table) return;
    if (!matrix.customers.length || !matrix.locations.length) {
      table.innerHTML = "<tr><td>No data for the current filters.</td></tr>";
      if (legendEl) legendEl.innerHTML = "";
      return;
    }
    if (!matrix.categories.length) {
      table.innerHTML = "<tr><td>This workbook has no Internal/SWC/External/Others breakdown — only period totals.</td></tr>";
      if (legendEl) legendEl.innerHTML = "";
      return;
    }

    let html = "<thead><tr><th>Customer Account</th>";
    matrix.locations.forEach(loc => { html += `<th>${loc}</th>`; });
    html += "</tr></thead><tbody>";

    matrix.customers.forEach(cust => {
      const warning = matrix.customer_warnings[cust];
      const custLabel = warning ? `⚠ ${cust}` : cust;
      html += `<tr><th class="${warning ? 'customer-col-warn' : ''}" title="${warning || ''}">${custLabel}</th>`;
      matrix.locations.forEach(loc => {
        const cell = matrix.cells[cust][loc];
        html += renderBreakdownCell(cell, matrix.categories);
      });
      html += "</tr>";
    });
    html += "</tbody>";
    table.innerHTML = html;
    if (legendEl) legendEl.innerHTML = renderCategoryLegend(matrix.categories);
  }

  function renderBreakdownCell(cell, categories) {
    if (!cell.has_fte) return `<td class="empty-cell">-</td>`;

    const isNegative = cell.total < 0;
    const parts = categories
      .map(cat => `<span style="color:${categoryColor(cat)}">${cell.values[cat]}</span>`)
      .join('<span class="op">+</span>');
    const cls = isNegative ? "negative-cell" : cell.is_base ? "base-cell" : "support-cell";
    return `<td class="${cls} breakdown-cell">
      <div class="breakdown-line">${parts}</div>
      <div class="breakdown-total">= <strong>${cell.total}</strong></div>
    </td>`;
  }

  function renderCategoryLegend(categories) {
    if (!categories.length) return "";
    return `<div class="category-legend">${categories.map(cat =>
      `<span class="legend-item"><span class="legend-swatch" style="background:${categoryColor(cat)}"></span>${cat}</span>`
    ).join("")}</div>`;
  }

  // -------------------------------------------------------------------
  // Charts (hand-rolled SVG/CSS -- no charting library dependency)
  // -------------------------------------------------------------------
  function renderCategoryPie(elId, breakdown) {
    const el = qs(elId);
    if (!el) return;
    const data = (breakdown.by_category || []).filter(d => d.fte > 0);
    const total = data.reduce((s, d) => s + d.fte, 0);
    if (!data.length || total <= 0) {
      el.innerHTML = '<div class="chart-empty">No category breakdown for the current filters.</div>';
      return;
    }

    const cx = 80, cy = 80, r = 78, hole = 46;
    let angle = -90;
    let slices = "";
    data.forEach(d => {
      const frac = d.fte / total;
      const sweep = Math.max(frac * 360, 0.001);
      const a1 = angle * Math.PI / 180;
      const a2 = (angle + sweep) * Math.PI / 180;
      const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
      const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
      const largeArc = sweep > 180 ? 1 : 0;
      slices += `<path d="M${cx},${cy} L${x1.toFixed(2)},${y1.toFixed(2)} A${r},${r} 0 ${largeArc} 1 ${x2.toFixed(2)},${y2.toFixed(2)} Z" fill="${categoryColor(d.category)}"><title>${d.category}: ${d.fte} (${(frac * 100).toFixed(1)}%)</title></path>`;
      angle += sweep;
    });
    const svg = `<svg viewBox="0 0 160 160" class="pie-chart">${slices}<circle cx="${cx}" cy="${cy}" r="${hole}" fill="var(--panel-bg)" /></svg>`;
    const center = `<div class="pie-chart-center"><div class="pie-total">${Math.round(total)}</div><div class="pie-total-label">Total FTE</div></div>`;
    const legend = `<div class="pie-chart-legend">${data.map(d =>
      `<span class="legend-item"><span class="legend-swatch" style="background:${categoryColor(d.category)}"></span>${d.category}<span class="legend-pct">${((d.fte / total) * 100).toFixed(0)}%</span><span class="legend-value">${d.fte}</span></span>`
    ).join("")}</div>`;
    el.innerHTML = `<div class="pie-chart-wrap">${svg}${center}${legend}</div>`;
  }

  function renderLocationBar(elId, breakdown) {
    const el = qs(elId);
    if (!el) return;
    const categories = breakdown.categories || [];
    const rows = breakdown.by_location || [];
    if (!categories.length || !rows.length) {
      el.innerHTML = '<div class="chart-empty">No category breakdown for the current filters.</div>';
      return;
    }
    const maxTotal = Math.max(...rows.map(r => r.total), 1);
    const barRows = rows.map(r => {
      const segs = categories.map(cat => {
        const val = r[cat] || 0;
        if (val <= 0) return "";
        const pct = (val / maxTotal) * 100;
        return `<div class="bar-seg" style="width:${pct}%;background:${categoryColor(cat)}" title="${cat}: ${val}"></div>`;
      }).join("");
      return `<div class="bar-row">
        <div class="bar-label" title="${r.location}">${r.location}</div>
        <div class="bar-track">${segs}</div>
        <div class="bar-total">${r.total}</div>
      </div>`;
    }).join("");
    el.innerHTML = `<div class="bar-chart">${barRows}</div>${renderCategoryLegend(categories)}`;
  }

  // -------------------------------------------------------------------
  // Generic table renderers
  // -------------------------------------------------------------------
  function renderSummaryCards(summary) {
    const el = qs("#summary-cards");
    if (!el) return;
    const cards = [
      ["Customers", summary.customers],
      ["Locations", summary.locations],
      ["Total FTE", summary.total_fte],
      ["Base Locations", summary.base_locations],
      ["Additional Locations", summary.additional_locations],
      ["Transfer Opportunities", summary.transfer_opportunities],
    ];
    el.innerHTML = cards.map(([label, val]) =>
      `<div class="card"><div class="card-label">${label}</div><div class="card-value">${val}</div></div>`
    ).join("");
  }

  function renderLocationSummary(rows) {
    const table = qs("#location-summary-table");
    if (!table) return;
    if (!rows.length) { table.innerHTML = "<tr><td>No data.</td></tr>"; return; }
    let html = "<thead><tr><th>Location</th><th>Total FTE</th><th>Customers Supported</th><th>Base For</th></tr></thead><tbody>";
    rows.forEach(r => {
      html += `<tr><td>${r.location}</td><td>${r.total_fte}</td><td>${r.customer_count}</td><td>${r.base_for_count}</td></tr>`;
    });
    table.innerHTML = html + "</tbody>";
  }

  function renderCustomerSummary(rows) {
    const table = qs("#customer-summary-table");
    if (!table) return;
    if (!rows.length) { table.innerHTML = "<tr><td>No data.</td></tr>"; return; }
    let html = "<thead><tr><th>Customer</th><th>Base Location(s)</th><th>Additional Locations</th><th>Total FTE</th><th>Status</th></tr></thead><tbody>";
    rows.forEach(r => {
      const status = r.warning ? `<span class="status-reduction">⚠ ${r.warning}</span>` : `<span class="status-growth">OK</span>`;
      html += `<tr><td>${r.customer}</td><td>${r.base_locations.join(", ") || "-"}</td><td>${r.additional_locations.join(", ") || "-"}</td><td>${r.total_fte}</td><td>${status}</td></tr>`;
    });
    table.innerHTML = html + "</tbody>";
  }

  function statusClass(status) {
    return { Growth: "status-growth", Reduction: "status-reduction", New: "status-new", Discontinued: "status-discontinued", "No Change": "status-stable" }[status] || "";
  }

  function renderComparison(rows) {
    const table = qs("#comparison-table");
    if (!table) return;
    if (!rows.length) { table.innerHTML = "<tr><td>Select two different periods to compare.</td></tr>"; return; }
    let html = "<thead><tr><th>Customer</th><th>Location</th><th>From FTE</th><th>To FTE</th><th>Change</th><th>Change %</th><th>Status</th></tr></thead><tbody>";
    rows.forEach(r => {
      html += `<tr><td>${r.customer}</td><td>${r.location}</td><td>${r.from_fte}</td><td>${r.to_fte}</td><td>${r.change}</td><td>${r.change_pct}%</td><td class="${statusClass(r.status)}">${r.status}</td></tr>`;
    });
    table.innerHTML = html + "</tbody>";
  }

  function renderCapacity(rows) {
    const table = qs("#capacity-table");
    if (!table) return;
    if (!rows.length) { table.innerHTML = "<tr><td>Select two different periods to compare.</td></tr>"; return; }
    let html = "<thead><tr><th>Location</th><th>Current FTE</th><th>Future FTE</th><th>Change</th><th>Status</th></tr></thead><tbody>";
    rows.forEach(r => {
      const cls = r.status === "Growth" ? "status-growth" : r.status === "Potential Released Capacity" ? "status-reduction" : "status-stable";
      html += `<tr><td>${r.location}</td><td>${r.current_fte}</td><td>${r.future_fte}</td><td>${r.change}</td><td class="${cls}">${r.status}</td></tr>`;
    });
    table.innerHTML = html + "</tbody>";
  }

  function renderTransfer(rows) {
    const table = qs("#transfer-table");
    if (!table) return;
    if (!rows.length) { table.innerHTML = "<tr><td>No transfer opportunities for the selected periods.</td></tr>"; return; }
    let html = "<thead><tr><th>From Location (Releasing)</th><th>To Location (Growing)</th><th>Released FTE</th><th>Required FTE</th><th>Matchable FTE</th></tr></thead><tbody>";
    rows.forEach(r => {
      html += `<tr><td>${r.from_location}</td><td>${r.to_location}</td><td>${r.released_fte}</td><td>${r.required_fte}</td><td><strong>${r.matchable_fte}</strong></td></tr>`;
    });
    table.innerHTML = html + "</tbody>";
  }

  function renderManualMappings(rows) {
    const table = qs("#manual-mapping-table");
    if (!table) return;
    if (!rows.length) { table.innerHTML = "<tr><td>No manual mappings yet.</td></tr>"; return; }
    let html = "<thead><tr><th>From</th><th>To</th><th>FTE</th><th>Notes</th><th></th></tr></thead><tbody>";
    rows.forEach(r => {
      html += `<tr><td>${r.from_customer} / ${r.from_location}</td><td>${r.to_customer} / ${r.to_location}</td><td>${r.fte_amount}</td><td>${r.notes || ""}</td><td><button data-id="${r.id}" class="btn btn-link delete-mapping">Remove</button></td></tr>`;
    });
    table.innerHTML = html + "</tbody>";
    qsa(".delete-mapping", table).forEach(btn => {
      btn.addEventListener("click", async () => {
        await fetch(`/api/manual-mapping/${btn.dataset.id}`, { method: "DELETE", credentials: "same-origin" });
        loadManualMappings();
      });
    });
  }

  function updateExportLink() {
    const link = qs("#export-link");
    if (!link) return;
    const params = new URLSearchParams();
    params.set("period", state.period || "");
    params.set("category", state.category || "Total");
    if (state.fromPeriod) params.set("from_period", state.fromPeriod);
    if (state.toPeriod) params.set("to_period", state.toPeriod);
    for (const [dim, values] of Object.entries(state.filters)) {
      values.forEach(v => params.append(dim, v));
    }
    link.href = "/export?" + params.toString();
  }

  // -------------------------------------------------------------------
  // Page loaders
  // -------------------------------------------------------------------
  async function loadDashboardData() {
    const [summary, matrix, locSummary, custSummary, breakdown] = await Promise.all([
      api("/api/summary", { period: state.period, category: state.category, ...currentFilterParams() }),
      api("/api/matrix", { period: state.period, category: state.category, ...currentFilterParams() }),
      api("/api/location-summary", { period: state.period, category: state.category, ...currentFilterParams() }),
      api("/api/customer-summary", { period: state.period, category: state.category, ...currentFilterParams() }),
      api("/api/category-breakdown", { period: state.period, ...currentFilterParams() }),
    ]);
    renderSummaryCards(summary);
    renderMatrix(matrix);
    renderLocationSummary(locSummary);
    renderCustomerSummary(custSummary);
    renderCategoryPie("#category-pie", breakdown);
    renderLocationBar("#location-bar", breakdown);
    updateExportLink();
  }

  async function loadMatrixOnly() {
    if (state.view === "breakdown") {
      const matrix = await api("/api/matrix-breakdown", { period: state.period, ...currentFilterParams() });
      renderMatrixBreakdown(matrix);
    } else {
      const matrix = await api("/api/matrix", { period: state.period, category: state.category, ...currentFilterParams() });
      renderMatrix(matrix);
      const legendEl = qs("#matrix-category-legend");
      if (legendEl) legendEl.innerHTML = "";
    }
    updateExportLink();
  }

  async function loadAnalysisData() {
    const [comparison, capacity] = await Promise.all([
      api("/api/comparison", { from_period: state.fromPeriod, to_period: state.toPeriod, category: state.category, ...currentFilterParams() }),
      api("/api/capacity", { from_period: state.fromPeriod, to_period: state.toPeriod, category: state.category, ...currentFilterParams() }),
    ]);
    renderComparison(comparison);
    renderCapacity(capacity);
    updateExportLink();
  }

  async function loadTransferData() {
    const rows = await api("/api/transfer-opportunities", { from_period: state.fromPeriod, to_period: state.toPeriod, category: state.category, ...currentFilterParams() });
    renderTransfer(rows);
    updateExportLink();
  }

  async function loadManualMappings() {
    const rows = await api("/api/manual-mapping");
    renderManualMappings(rows);
  }

  async function loadManagementData() {
    await loadDashboardData();
    await loadAnalysisData_ManagementSubset();
  }

  async function loadAnalysisData_ManagementSubset() {
    const [comparison, transfers] = await Promise.all([
      api("/api/comparison", { from_period: state.fromPeriod, to_period: state.toPeriod, category: state.category, ...currentFilterParams() }),
      api("/api/transfer-opportunities", { from_period: state.fromPeriod, to_period: state.toPeriod, category: state.category, ...currentFilterParams() }),
    ]);
    renderComparison(comparison);
    renderTransfer(transfers.slice(0, 10));
    updateExportLink();
  }

  function initDashboard() {
    buildFilterBar(loadDashboardData);
    loadDashboardData();
  }

  function initMapping() {
    buildFilterBar(loadMatrixOnly);
    qsa("#view-toggle button").forEach(btn => {
      btn.addEventListener("click", () => {
        qsa("#view-toggle button").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        state.view = btn.dataset.view;
        loadMatrixOnly();
      });
    });
    loadMatrixOnly();
  }

  function initAnalysis() {
    buildFilterBar(loadAnalysisData);
    loadAnalysisData();
  }

  function initTransfer() {
    buildFilterBar(loadTransferData);
    loadTransferData();
    loadManualMappings();
    const form = qs("#manual-mapping-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      await fetch("/api/manual-mapping", { method: "POST", body: fd, credentials: "same-origin" });
      form.reset();
      loadManualMappings();
    });
  }

  function initManagement() {
    buildFilterBar(loadManagementData);
    loadManagementData();
  }

  return {
    initDashboard, initMapping, initAnalysis, initTransfer, initManagement,
  };
})();
