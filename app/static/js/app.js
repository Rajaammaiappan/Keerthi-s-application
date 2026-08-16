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
    const [summary, matrix, locSummary, custSummary] = await Promise.all([
      api("/api/summary", { period: state.period, category: state.category, ...currentFilterParams() }),
      api("/api/matrix", { period: state.period, category: state.category, ...currentFilterParams() }),
      api("/api/location-summary", { period: state.period, category: state.category, ...currentFilterParams() }),
      api("/api/customer-summary", { period: state.period, category: state.category, ...currentFilterParams() }),
    ]);
    renderSummaryCards(summary);
    renderMatrix(matrix);
    renderLocationSummary(locSummary);
    renderCustomerSummary(custSummary);
    updateExportLink();
  }

  async function loadMatrixOnly() {
    const matrix = await api("/api/matrix", { period: state.period, category: state.category, ...currentFilterParams() });
    renderMatrix(matrix);
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
