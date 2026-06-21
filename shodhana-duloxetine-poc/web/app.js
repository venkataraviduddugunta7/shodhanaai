let dashboardData = null;
let opportunityRows = [];
let opportunityDetailData = null;
let pitchData = null;
let activeEmailTone = "formal";
let reviewData = {summary: {}, products: [], companies: [], issue_rows: []};
let reviewFilter = "pending";
const expandedCompanyGroups = new Set();
const expandedCountryGroups = new Set();
const expandedProductGroups = new Set();
const STANDARD_PRODUCTS = [
  "Duloxetine API",
  "Duloxetine Pellets",
  "Duloxetine Placebo Pellets",
  "Other / Review Required",
];

async function getJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function postJSON(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {}),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function showPage(page, updateUrl = true) {
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
  document.getElementById(`page-${page}`).classList.add("active");
  if (page === "advisor") {
    loadGrowthAdvisor();
  }
  if (updateUrl) {
    const path = pageToPath(page);
    if (window.location.pathname !== path) window.history.pushState({page}, "", path);
  }
}

async function refreshAll() {
  await Promise.all([loadDashboard(), loadOpportunities(), loadMappings(), loadReview(), loadGrowthAdvisor()]);
}

async function importSample(button) {
  await withBusy(button, "Importing", async () => {
    setStatus("Importing sample Excel...");
    const result = await postJSON("/api/import-sample", {});
    renderImportResult(result);
    await refreshAll();
    setStatus(`Initial cleaning complete: ${result.clean_rows} clean rows, ${result.duplicates_removed} duplicates removed. Review mappings next.`);
    showPage("review");
  });
}

async function importChemdoze(button) {
  const email = document.getElementById("chemdozeEmail").value.trim();
  const password = document.getElementById("chemdozePassword").value;
  const query = document.getElementById("chemdozeQuery").value.trim() || "Duloxetine";
  const fromDate = document.getElementById("chemdozeFromDate").value.trim();
  const toDate = document.getElementById("chemdozeToDate").value.trim();
  await withBusy(button, "Downloading", async () => {
    setStatus("Downloading Chemdoze Excel and rebuilding data...");
    const result = await postJSON("/api/import-chemdoze", {
      email,
      password,
      query,
      from_date: fromDate,
      to_date: toDate,
    });
    renderImportResult(result);
    await refreshAll();
    setStatus(`Chemdoze import complete: ${result.clean_rows} clean rows, ${result.duplicates_removed} duplicates removed. Review mappings next.`);
    showPage("review");
  });
}

async function uploadFile(button) {
  const file = document.getElementById("uploadFile").files[0];
  const sourceType = document.getElementById("sourceType").value;
  if (!file) {
    setStatus("Choose a file first.", true);
    return;
  }
  await withBusy(button, "Processing", async () => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_type", sourceType);
    const response = await fetch("/api/upload", {method: "POST", body: form});
    const result = await response.json();
    if (!response.ok || result.error) throw new Error(result.error || "Upload failed.");
    renderImportResult(result);
    await refreshAll();
    const count = result.clean_rows || result.rows || 0;
    setStatus(`Processed ${count} rows from ${file.name}.`);
    if (sourceType === "trade_data") showPage("review");
  });
}

function renderImportResult(result) {
  const map = result.detected_columns || {};
  document.getElementById("columnMap").textContent = Object.keys(map).length
    ? JSON.stringify(map, null, 2)
    : JSON.stringify(result, null, 2);
}

function dashboardFilters(prefix = "dash") {
  return {
    product_category: document.getElementById(`${prefix}Product`)?.value || "",
    importer_country: document.getElementById(`${prefix}ImporterCountry`)?.value || "",
    exporter_country: document.getElementById(`${prefix}ExporterCountry`)?.value || "",
    importer_name: document.getElementById(`${prefix}Importer`)?.value || "",
    exporter_name: document.getElementById(`${prefix}Exporter`)?.value || "",
    year: document.getElementById(`${prefix}Year`)?.value || "",
    month: document.getElementById(`${prefix}Month`)?.value || "",
    shodhana_status: document.getElementById(`${prefix}Status`)?.value || "",
  };
}

function queryFromFilters(filters) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (String(value || "").trim()) params.set(key, String(value).trim());
  });
  return params.toString();
}

function dashboardQuery() {
  return queryFromFilters(dashboardFilters("dash"));
}

function opportunityQuery() {
  return queryFromFilters(dashboardFilters("op"));
}

function populateFilterOptions(options) {
  populateSelect("dashProduct", options.product_categories || [], "All products");
  populateSelect("dashImporterCountry", options.importer_countries || [], "All importer countries");
  populateSelect("dashExporterCountry", options.exporter_countries || [], "All exporter countries");
  populateSelect("dashYear", options.years || [], "All years");
  populateSelect("dashMonth", options.months || [], "All months");
  populateSelect("opProduct", options.product_categories || [], "All products");
  populateSelect("opImporterCountry", options.importer_countries || [], "All importer countries");
  populateSelect("opExporterCountry", options.exporter_countries || [], "All exporter countries");
  populateSelect("opYear", options.years || [], "All years");
  populateSelect("opMonth", options.months || [], "All months");
}

function populateSelect(id, values, placeholder) {
  const select = document.getElementById(id);
  if (!select) return;
  const current = select.value;
  select.innerHTML = `<option value="">${esc(placeholder)}</option>` + values.map((value) => `<option value="${esc(value)}">${esc(value)}</option>`).join("");
  select.value = values.map(String).includes(String(current)) ? current : "";
}

function clearDashboardFilters() {
  ["dashProduct", "dashImporterCountry", "dashExporterCountry", "dashImporter", "dashExporter", "dashYear", "dashMonth", "dashStatus"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  loadDashboard();
}

async function loadDashboard() {
  dashboardData = await getJSON(`/api/dashboard?${dashboardQuery()}`);
  const stats = dashboardData.stats || {};
  document.getElementById("uploadBadge").textContent = stats.total_records
    ? `${num(stats.total_records)} records loaded`
    : "No file loaded";
  populateFilterOptions(dashboardData.filter_options || {});
  renderDashboardCards(stats);
  renderQualityCards(stats);
  renderHorizontalBars("productQuantityChart", dashboardData.product_split || [], "quantity_kg");
  renderHorizontalBars("countryDemandChart", dashboardData.country_demand || [], "quantity_kg");
  renderHorizontalBars("topCountryChart", dashboardData.top_countries || [], "quantity_kg");
  renderHorizontalBars("topImporterChart", dashboardData.top_importers || [], "quantity_kg");
  renderHorizontalBars("topExporterChart", dashboardData.top_exporters || [], "quantity_kg");
  renderLineChart("monthQuantityTrend", dashboardData.month_trend || [], "quantity_kg", "KG");
  renderLineChart("monthPriceTrend", dashboardData.price_trend || [], "avg_price_per_kg", "$/KG");
  renderPriceRange(dashboardData.price_range || []);
  renderCompetitors(dashboardData.competitor_intelligence || []);
  renderCustomers(dashboardData.customer_intelligence || []);
}

async function loadReview() {
  reviewData = await getJSON("/api/cleaning-review");
  renderReviewSummary(reviewData.summary || {});
  renderIssueRows(reviewData.issue_rows || []);
}

function renderReviewSummary(summary) {
  const cards = [
    ["Total Raw Records", summary.total_raw_records],
    ["Cleaned Records", summary.cleaned_records],
    ["Pending Product Maps", summary.pending_product_mappings],
    ["Pending Company Maps", summary.pending_company_mappings],
    ["Pending Country Maps", summary.pending_country_mappings],
    ["Review Required Rows", summary.review_required_records],
  ];
  document.getElementById("reviewSummaryCards").innerHTML = cards.map(statCard).join("");
}

function renderDashboardCards(stats) {
  const cards = [
    ["Total Records", stats.total_records],
    ["Clean Records", stats.clean_records],
    ["Total Quantity KG", stats.total_quantity_kg],
    ["Total Value USD", money(stats.total_value_usd)],
    ["Avg Price/KG", money(stats.avg_price_per_kg)],
    ["Unique Importers", stats.unique_importers],
    ["Unique Exporters", stats.unique_exporters],
    ["Unique Countries", stats.unique_countries],
    ["Review Required", stats.review_required_records],
    ["Competitor Supplied", stats.competitor_supplied_records],
    ["Shodhana Supplied", stats.shodhana_supplied_records],
  ];
  document.getElementById("dashboardCards").innerHTML = cards.map(statCard).join("");
}

function renderQualityCards(stats) {
  const cards = [
    ["Total Raw Records", stats.total_raw_records || stats.total_records],
    ["Clean Products", stats.clean_product_records],
    ["Review Products", stats.review_required_records],
    ["Unique Raw Products", stats.unique_raw_products],
    ["Valid KG Rows", stats.valid_kg_records],
    ["Invalid Quantity", stats.invalid_qty_records],
    ["Price/KG Rows", stats.price_records],
    ["Missing Value/Qty", stats.missing_value_or_quantity_records],
    ["Manual Review", stats.manual_review_records],
    ["Duplicates Removed", stats.duplicates_removed],
  ];
  document.getElementById("qualityCards").innerHTML = cards.map(statCard).join("");
}

function statCard([label, value]) {
  return `<div class="stat-card"><span>${esc(label)}</span><strong>${formatValue(value)}</strong></div>`;
}

function renderBarList(id, rows, metric) {
  const max = Math.max(...rows.map((row) => Number(row[metric] || 0)), 1);
  const html = rows.length ? rows.map((row) => {
    const value = Number(row[metric] || 0);
    const width = Math.max(3, (value / max) * 100);
    return `<div class="bar-row">
      <div class="bar-label" title="${esc(row.label)}">${esc(row.label || "Unknown")}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
      <div class="bar-value">${num(value)}</div>
    </div>`;
  }).join("") : `<div class="empty">No data loaded.</div>`;
  document.getElementById(id).innerHTML = html;
}

function renderHorizontalBars(id, rows, metric) {
  const max = Math.max(...rows.map((row) => Number(row[metric] || 0)), 1);
  document.getElementById(id).innerHTML = rows.length ? `<div class="bar-list chart-list">
    ${rows.map((row) => {
      const value = Number(row[metric] || 0);
      const width = Math.max(3, (value / max) * 100);
      return `<div class="bar-row wide">
        <div class="bar-label" title="${esc(row.label)}">${esc(row.label || "Unknown")}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
        <div class="bar-value">${num(value)}</div>
      </div>`;
    }).join("")}
  </div>` : `<div class="empty">No data loaded.</div>`;
}

function renderLineChart(id, rows, metric, suffix) {
  const container = document.getElementById(id);
  if (!rows.length) {
    container.innerHTML = `<div class="empty">No trend data loaded.</div>`;
    return;
  }
  const width = 640;
  const height = 230;
  const pad = 34;
  const values = rows.map((row) => Number(row[metric] || 0));
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = pad + (index * ((width - pad * 2) / Math.max(rows.length - 1, 1)));
    const y = height - pad - ((value / max) * (height - pad * 2));
    return {x, y, value, label: rows[index].label};
  });
  const polyline = points.map((point) => `${point.x},${point.y}`).join(" ");
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" class="line-chart" role="img">
    <line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" class="axis"></line>
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}" class="axis"></line>
    <polyline points="${polyline}" class="trend-line"></polyline>
    ${points.map((point, index) => `<circle cx="${point.x}" cy="${point.y}" r="4" class="trend-dot"><title>${esc(point.label)}: ${num(point.value)} ${esc(suffix)}</title></circle>
      ${index % Math.ceil(points.length / 6 || 1) === 0 ? `<text x="${point.x}" y="${height - 8}" text-anchor="middle" class="axis-label">${esc(point.label)}</text>` : ""}`).join("")}
  </svg>`;
}

function renderPriceRange(rows) {
  const container = document.getElementById("priceRangeChart");
  if (!rows.length) {
    container.innerHTML = `<div class="empty">No price data loaded.</div>`;
    return;
  }
  const maxPrice = Math.max(...rows.map((row) => Number(row.max_price || 0)), 1);
  container.innerHTML = `<div class="price-range-list">
    ${rows.map((row) => {
      const min = Number(row.min_price || 0);
      const avg = Number(row.avg_price || 0);
      const max = Number(row.max_price || 0);
      const left = Math.min(96, Math.max(0, (min / maxPrice) * 100));
      const width = Math.max(4, ((max - min) / maxPrice) * 100);
      const avgPos = Math.min(98, Math.max(2, (avg / maxPrice) * 100));
      return `<div class="price-range-row">
        <div class="price-range-head">
          <strong>${esc(row.product)}</strong>
          <span>${num(row.priced_rows)} priced rows</span>
        </div>
        <div class="price-range-track">
          <div class="price-range-band" style="left:${left}%; width:${width}%"></div>
          <div class="price-range-marker" style="left:${avgPos}%"><span>${money(avg)}</span></div>
        </div>
        <div class="price-range-values">
          <span>Min ${money(min)}</span>
          <span>Avg ${money(avg)}</span>
          <span>Max ${money(max)}</span>
        </div>
      </div>`;
    }).join("")}
  </div>`;
}

function renderCompetitors(rows) {
  const container = document.getElementById("competitorTable");
  container.innerHTML = rows.length ? `<table>
    <thead><tr><th>Exporter</th><th>Product</th><th>Countries</th><th>Qty KG</th><th>Value USD</th><th>Avg $/KG</th><th>Shipments</th><th>Last Shipment</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.exporter_name)}</strong></td>
      <td>${esc(row.product_category)}</td>
      <td>${esc(row.countries_supplied)}</td>
      <td>${num(row.total_quantity_kg)}</td>
      <td>${money(row.total_value_usd)}</td>
      <td class="score">${money(row.avg_price_per_kg)}</td>
      <td>${num(row.shipment_count)}</td>
      <td>${esc(row.last_shipment_date)}</td>
    </tr>`).join("")}</tbody>
  </table>` : `<div class="empty">No competitor rows for current filters.</div>`;
}

function renderCustomers(rows) {
  const container = document.getElementById("customerTable");
  container.innerHTML = rows.length ? `<table>
    <thead><tr><th>Importer</th><th>Country</th><th>Product</th><th>Supplier</th><th>Qty KG</th><th>Value USD</th><th>Avg $/KG</th><th>Shipments</th><th>Dates</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.importer)}</strong></td>
      <td>${esc(row.country)}</td>
      <td>${esc(row.product)}</td>
      <td>${esc(row.current_supplier)}</td>
      <td>${num(row.total_quantity_kg)}</td>
      <td>${money(row.total_value_usd)}</td>
      <td class="score">${money(row.avg_price_per_kg)}</td>
      <td>${num(row.shipment_count)}</td>
      <td>${esc(row.first_shipment_date)}<br><span class="muted">${esc(row.last_shipment_date)}</span></td>
      <td>${esc(row.shodhana_status)}</td>
    </tr>`).join("")}</tbody>
  </table>` : `<div class="empty">No customer rows for current filters.</div>`;
}

async function loadOpportunities() {
  const data = await getJSON(`/api/opportunities?${opportunityQuery()}`);
  opportunityRows = data.rows || [];
  document.getElementById("opportunityCount").textContent = `${opportunityRows.length} rows`;
  renderOpportunities(opportunityRows);
}

function renderOpportunities(rows) {
  const container = document.getElementById("opportunityTable");
  if (!rows.length) {
    container.innerHTML = `<div class="empty">No opportunities loaded.</div>`;
    return;
  }
  container.innerHTML = `<table>
    <thead>
      <tr>
        <th>Rank</th>
        <th>Importer</th>
        <th>Country</th>
        <th>Product Category</th>
        <th>Current Supplier</th>
        <th>Qty KG</th>
        <th>Avg $/KG</th>
        <th>Market Avg</th>
        <th>Price Diff</th>
        <th>Shipments</th>
        <th>Last Shipment</th>
        <th>Buyer Status</th>
        <th>Status</th>
        <th>Score</th>
        <th>Category</th>
        <th>Recommended Action</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      ${rows.map((row) => {
        const canPitch = true;
        const pitchTooltip = "Generate a customer-specific pitch package for this opportunity.";
        return `<tr>
        <td class="score">#${row.rank}</td>
        <td><strong>${esc(row.importer)}</strong><br><span class="muted">${esc((row.reasons || []).join(', '))}</span></td>
        <td>${esc(row.country)}<br><span class="muted">${esc(row.market_category)}</span></td>
        <td>${esc(row.product)}</td>
        <td>${esc(row.current_supplier)}</td>
        <td>${num(row.total_quantity_kg)}</td>
        <td class="score">${money(row.avg_price_per_kg)}</td>
        <td>${money(row.market_avg_price_per_kg)}</td>
        <td class="${Number(row.price_difference || 0) > 0 ? 'score' : 'muted'}">${money(row.price_difference)}</td>
        <td>${num(row.shipment_count)}</td>
        <td>${esc(row.last_shipment_date)}</td>
        <td>${statusText(row.customer_identification_status)}${Number(row.manual_review_rows || 0) ? `<br><span class="warning-text">${num(row.manual_review_rows)} review rows</span>` : ""}</td>
        <td>${esc(row.shodhana_status)}<br><span class="muted">${esc(row.tier)}</span></td>
        <td class="score">${row.score}</td>
        <td>${esc(row.opportunity_category)}</td>
        <td class="reason-cell">${esc(row.recommended_action)}</td>
        <td class="action-cell">
          <div class="action-grid two-actions">
            <button class="small tip" data-tooltip="Open customer, shipment, supplier, and price detail." onclick="viewOpportunity('${esc(row.opportunity_id)}')">Details</button>
            <button class="small tip" data-tooltip="${esc(pitchTooltip)}" ${canPitch ? `onclick="openPitch('${esc(row.opportunity_id)}')"` : "disabled"}>${canPitch ? "Generate Pitch" : "Pitch Locked"}</button>
          </div>
        </td>
      </tr>`;
      }).join("")}
    </tbody>
  </table>`;
  setTooltipTitles();
}

async function aiAction(action, index) {
  const opportunity = opportunityRows[index];
  if (!opportunity) return;
  const data = await postJSON("/api/ai-action", {action, opportunity});
  setOutput(data.content || "");
  showPage("pitch");
}

async function openPitch(id, regenerate = false) {
  const data = regenerate
    ? await postJSON("/api/pitch/regenerate", {id})
    : await getJSON(`/api/pitch?id=${encodeURIComponent(id)}`);
  pitchData = data;
  renderPitch(data);
  showPage("pitch", false);
  const path = `/pitch/${id}`;
  if (window.location.pathname !== path) window.history.pushState({page: "pitch", id}, "", path);
}

async function loadPitchFromPath() {
  const match = window.location.pathname.match(/^\/pitch\/([^/]+)/);
  if (!match) {
    renderPitch(null);
    return;
  }
  await openPitch(match[1], false);
}

async function regeneratePitch() {
  const id = pitchData?.opportunity_id || pitchData?.detail?.opportunity?.opportunity_id;
  if (!id) {
    setStatus("Open an opportunity before regenerating pitch.", true);
    return;
  }
  await openPitch(id, true);
  setStatus("Pitch regenerated.");
}

function renderPitch(data) {
  const container = document.getElementById("pitchContent");
  const tools = document.getElementById("pitchTools");
  const meta = document.getElementById("pitchMeta");
  if (!data?.pitch) {
    tools.classList.add("hidden");
    meta.textContent = "Select an opportunity and click Generate Pitch.";
    container.innerHTML = `<div class="empty">No pitch loaded yet. Open the Opportunities page and generate a pitch for a target customer.</div>`;
    return;
  }
  tools.classList.remove("hidden");
  const pitch = data.pitch || {};
  const detail = data.detail || {};
  const opp = detail.opportunity || {};
  const created = data.created_at ? new Date(Number(data.created_at) * 1000).toLocaleString() : "Just now";
  meta.textContent = `Generated for ${opp.importer || "customer"} on ${created}`;
  const email = (pitch.email_drafts || {})[activeEmailTone] || "";
  container.innerHTML = `
    <div class="approval-note">${esc(pitch.human_approval_note || "AI-generated output is a draft. Sales/business team must review before sending externally.")}</div>
    <div class="stats-grid">
      ${[
        ["Customer", opp.importer || ""],
        ["Country", opp.country || ""],
        ["Product", opp.product || ""],
        ["Opportunity Score", opp.score],
        ["Opportunity", opp.opportunity_category || ""],
        ["Status", opp.shodhana_status || ""],
        ["Total KG", opp.total_quantity_kg],
        ["Avg Price/KG", money(opp.avg_price_per_kg)],
      ].map(statCard).join("")}
    </div>
    <div class="grid two">
      ${pitchSection("Customer Intelligence Summary", `<pre class="section-copy">${esc(pitch.customer_summary)}</pre>`)}
      ${pitchSection("Buying Pattern", `<p>${esc(pitch.buying_pattern)}</p>`)}
    </div>
    <div class="grid two">
      ${pitchSection("Current Supplier", `<p>${esc(pitch.current_supplier)}</p>`)}
      ${pitchSection("Price Analysis", `<p>${esc(pitch.price_analysis)}</p>`)}
    </div>
    <div class="grid two">
      ${pitchSection("Why Shodhana Should Target", `<p>${esc(pitch.why_target)}</p>`)}
      ${pitchSection("Recommended Commercial Strategy", `<pre class="section-copy">${esc(pitch.commercial_strategy || pitch.price_strategy)}</pre>`)}
    </div>
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Pitch Email Draft</h3>
          <p>Choose the tone the sales team wants to review.</p>
        </div>
        <div class="segmented">
          ${["formal", "short", "relationship"].map((tone) => `<button class="small ${tone === activeEmailTone ? "" : "ghost"}" onclick="setEmailTone('${tone}')">${toneLabel(tone)}</button>`).join("")}
        </div>
      </div>
      <pre class="email-draft" id="activeEmailDraft">${esc(email)}</pre>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>PPT Outline</h3></div>
      ${renderPptOutline(pitch.ppt_outline || [])}
    </div>
    <div class="panel">
      <div class="panel-head"><h3>Follow-up Plan</h3></div>
      ${renderFollowUpPlan(pitch.follow_up_plan || "")}
    </div>
    <div class="panel">
      <div class="panel-head">
        <h3><span class="material-symbols-outlined" style="vertical-align: middle; margin-right: 8px;">history</span> Outreach Communication History</h3>
      </div>
      <div id="sentEmailsLogs">Loading communications...</div>
    </div>
  `;
  setTooltipTitles();
  loadSentEmailsList();
}

function pitchSection(title, body) {
  return `<div class="panel pitch-section"><div class="panel-head"><h3>${esc(title)}</h3></div>${body}</div>`;
}

function setEmailTone(tone) {
  activeEmailTone = tone;
  renderPitch(pitchData);
}

function toneLabel(tone) {
  return {
    formal: "Formal",
    short: "Short Direct",
    relationship: "Relationship",
  }[tone] || tone;
}

function renderPptOutline(slides) {
  if (!slides.length) return `<div class="empty">No PPT outline generated.</div>`;
  return `<div class="ppt-outline">
    ${slides.map((slide, index) => `<div class="ppt-slide">
      <div class="ppt-slide-number">Slide ${index + 1}</div>
      <h4>${esc(slide.title)}</h4>
      <ul>${(slide.bullets || []).map((bullet) => `<li>${esc(bullet)}</li>`).join("")}</ul>
      <p><strong>Speaker note:</strong> ${esc(slide.speaker_note)}</p>
    </div>`).join("")}
  </div>`;
}

function renderFollowUpPlan(plan) {
  const lines = String(plan || "").split("\n").filter(Boolean);
  return lines.length ? `<ol class="follow-up-list">${lines.map((line) => `<li>${esc(line)}</li>`).join("")}</ol>` : `<div class="empty">No follow-up plan generated.</div>`;
}

async function copyPitchEmail() {
  if (!pitchData?.pitch) return;
  const email = (pitchData.pitch.email_drafts || {})[activeEmailTone] || "";
  try {
    await navigator.clipboard.writeText(email);
    setStatus(`${toneLabel(activeEmailTone)} email copied.`);
  } catch {
    setStatus("Copy failed.", true);
  }
}

function exportPitchText() {
  if (!pitchData?.pitch) return;
  downloadTextFile(pitchFileName("pitch.txt"), buildPitchText(pitchData));
}

function exportPptMarkdown() {
  if (!pitchData?.pitch) return;
  downloadTextFile(pitchFileName("ppt-outline.md"), buildPptMarkdown(pitchData.pitch.ppt_outline || []));
}

function exportSummaryMarkdown() {
  if (!pitchData?.pitch) return;
  downloadTextFile(pitchFileName("customer-summary.md"), buildSummaryMarkdown(pitchData));
}

function buildPitchText(data) {
  const pitch = data.pitch || {};
  return [
    "# Shodhana AI Customer Pitch Draft",
    "## Customer Intelligence Summary\n" + (pitch.customer_summary || ""),
    "## Buying Pattern\n" + (pitch.buying_pattern || ""),
    "## Current Supplier\n" + (pitch.current_supplier || ""),
    "## Price Analysis\n" + (pitch.price_analysis || ""),
    "## Why Shodhana Should Target\n" + (pitch.why_target || ""),
    "## Recommended Commercial Strategy\n" + (pitch.commercial_strategy || pitch.price_strategy || ""),
    "## Formal Email Draft\n" + ((pitch.email_drafts || {}).formal || ""),
    "## Short Direct Email Draft\n" + ((pitch.email_drafts || {}).short || ""),
    "## Relationship-building Email Draft\n" + ((pitch.email_drafts || {}).relationship || ""),
    "## PPT Outline\n" + buildPptMarkdown(pitch.ppt_outline || []),
    "## Follow-up Plan\n" + (pitch.follow_up_plan || ""),
    pitch.human_approval_note || "AI-generated output is a draft. Sales/business team must review before sending externally.",
  ].join("\n\n");
}

function buildPptMarkdown(slides) {
  return slides.map((slide, index) => {
    const bullets = (slide.bullets || []).map((bullet) => `- ${bullet}`).join("\n");
    return `### Slide ${index + 1}: ${slide.title}\n${bullets}\n\nSpeaker note: ${slide.speaker_note}`;
  }).join("\n\n");
}

function buildSummaryMarkdown(data) {
  const pitch = data.pitch || {};
  const opp = data.detail?.opportunity || {};
  return [
    `# Customer Summary - ${opp.importer || "Opportunity"}`,
    pitch.customer_summary || "",
    "## Buying Pattern",
    pitch.buying_pattern || "",
    "## Current Supplier",
    pitch.current_supplier || "",
    "## Price Analysis",
    pitch.price_analysis || "",
    "## Approval Note",
    pitch.human_approval_note || "AI-generated output is a draft. Sales/business team must review before sending externally.",
  ].join("\n\n");
}

function pitchFileName(suffix) {
  const opp = pitchData?.detail?.opportunity || {};
  const base = String(opp.importer || "shodhana-pitch").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `${base || "shodhana-pitch"}-${suffix}`;
}

function downloadTextFile(filename, text) {
  const blob = new Blob([text], {type: "text/plain;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function viewOpportunity(id) {
  opportunityDetailData = await getJSON(`/api/opportunity-detail?id=${encodeURIComponent(id)}`);
  renderOpportunityDetail(opportunityDetailData);
  showPage("opportunity-detail", false);
  window.history.pushState({page: "opportunity-detail", id}, "", `/opportunities/${id}`);
}

async function loadOpportunityDetailFromPath() {
  const match = window.location.pathname.match(/^\/opportunities\/([^/]+)/);
  if (!match) return;
  opportunityDetailData = await getJSON(`/api/opportunity-detail?id=${encodeURIComponent(match[1])}`);
  renderOpportunityDetail(opportunityDetailData);
}

function renderOpportunityDetail(data) {
  const opp = data.opportunity || {};
  const price = data.price_analysis || {};
  document.getElementById("opportunityDetail").innerHTML = `
    <div class="stats-grid">
      ${[
        ["Importer", opp.importer || ""],
        ["Product", opp.product || ""],
        ["Opportunity Score", opp.score],
        ["Category", opp.opportunity_category || ""],
        ["Total KG", opp.total_quantity_kg],
        ["Avg Price/KG", money(opp.avg_price_per_kg)],
        ["Market Avg", money(opp.market_avg_price_per_kg)],
        ["Price Difference", money(opp.price_difference)],
        ["Buyer Status", opp.customer_identification_status || ""],
        ["Review Rows", opp.manual_review_rows || 0],
      ].map(statCard).join("")}
    </div>
    <div class="grid two">
      <div class="panel">
        <div class="panel-head"><h3>Customer Summary</h3></div>
        <table><tbody>
          <tr><th>Country</th><td>${esc(data.customer_summary?.country)}</td></tr>
          <tr><th>Market</th><td>${esc(data.customer_summary?.market_category)}</td></tr>
          <tr><th>Shipments</th><td>${num(data.customer_summary?.shipment_count)}</td></tr>
          <tr><th>Last Shipment</th><td>${esc(data.customer_summary?.last_shipment_date)}</td></tr>
          <tr><th>Buyer Status</th><td>${statusText(opp.customer_identification_status)}</td></tr>
          <tr><th>Status</th><td>${esc(opp.shodhana_status)}</td></tr>
        </tbody></table>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>Why This Customer Matters</h3></div>
        <div class="reason-list">${(data.why_important || []).map((reason) => `<span>${esc(reason)}</span>`).join("") || "<span>Monitor until stronger signal appears.</span>"}</div>
        <p class="detail-action">${esc(data.recommended_action)}</p>
      </div>
    </div>
    <div class="grid two">
      <div class="panel">
        <div class="panel-head"><h3>Supplier History</h3></div>
        ${supplierHistoryTable(data.supplier_history || [])}
      </div>
      <div class="panel">
        <div class="panel-head"><h3>Price Analysis</h3></div>
        <table><tbody>
          <tr><th>Customer Avg Price/KG</th><td class="score">${money(price.customer_avg_price_per_kg)}</td></tr>
          <tr><th>Market Avg Price/KG</th><td>${money(price.market_avg_price_per_kg)}</td></tr>
          <tr><th>Difference</th><td>${money(price.price_difference)}</td></tr>
          <tr><th>Market Min</th><td>${money(price.market_min_price_per_kg)}</td></tr>
          <tr><th>Market Max</th><td>${money(price.market_max_price_per_kg)}</td></tr>
        </tbody></table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>Shipment History</h3></div>
      ${shipmentHistoryTable(data.shipment_history || [])}
    </div>`;
}

function supplierHistoryTable(rows) {
  return rows.length ? `<div class="table-wrap"><table>
    <thead><tr><th>Supplier</th><th>Country</th><th>Qty KG</th><th>Value</th><th>Avg $/KG</th><th>Shipments</th><th>Last Shipment</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.supplier)}</strong></td><td>${esc(row.exporter_country)}</td><td>${num(row.total_quantity_kg)}</td><td>${money(row.total_value_usd)}</td><td class="score">${money(row.avg_price_per_kg)}</td><td>${num(row.shipment_count)}</td><td>${esc(row.last_shipment_date)}</td><td>${esc(row.shodhana_status)}</td>
    </tr>`).join("")}</tbody>
  </table></div>` : `<div class="empty">No supplier history.</div>`;
}

function shipmentHistoryTable(rows) {
  return rows.length ? `<div class="table-wrap tall"><table>
    <thead><tr><th>Date</th><th>Exporter</th><th>Exporter Country</th><th>Qty KG</th><th>Value</th><th>Price/KG</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td>${esc(row.shipment_date)}</td><td><strong>${esc(row.standard_exporter_name)}</strong></td><td>${esc(row.exporter_country)}</td><td>${num(row.quantity_kg)}</td><td>${money(row.value_usd)}</td><td class="score">${money(row.price_per_kg)}</td><td>${esc(row.shodhana_status)}</td>
    </tr>`).join("")}</tbody>
  </table></div>` : `<div class="empty">No shipment history.</div>`;
}

async function generatePitchForDetail() {
  if (!opportunityDetailData?.opportunity) return;
  const opp = opportunityDetailData.opportunity;
  await openPitch(opp.opportunity_id);
}

function downloadExport(kind, source = "dashboard") {
  const query = source === "opportunity" ? opportunityQuery() : dashboardQuery();
  const routes = {
    cleaned: "/api/export/cleaned.xlsx",
    opportunities: "/api/export/opportunities.xlsx",
    summary: "/api/export/dashboard-summary.csv",
  };
  window.location.href = `${routes[kind]}?${query}`;
}

async function loadMappings() {
  const [products, companies, countries] = await Promise.all([
    getJSON("/api/mappings/products"),
    getJSON("/api/mappings/companies"),
    getJSON("/api/mappings/countries"),
  ]);
  renderProductMappings(products.rows || []);
  renderCompanyMappings(companies.rows || []);
  renderCountryMappings(countries.rows || []);
}

async function setReviewFilter(filter) {
  reviewFilter = filter;
  document.querySelectorAll(".filter-row button").forEach((button) => {
    button.classList.toggle("active-filter", button.textContent.toLowerCase().includes(filterLabel(filter)));
  });
  const data = await getJSON(`/api/review-records?filter=${encodeURIComponent(filter)}`);
  renderIssueRows(data.rows || []);
}

function filterLabel(filter) {
  return {
    pending: "pending",
    low_confidence: "low",
    review_products: "review",
    invalid_units: "invalid",
    missing_price: "missing",
  }[filter] || filter;
}

function renderIssueRows(rows) {
  const container = document.getElementById("reviewIssueTable");
  if (!rows.length) {
    container.innerHTML = `<div class="empty">No rows for this filter.</div>`;
    return;
  }
  container.innerHTML = `<table>
    <thead><tr><th>Product</th><th>Importer</th><th>Exporter</th><th>Unit</th><th>Value</th><th>Price/KG</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_product_description)}</strong><br><span class="muted">${esc(row.standard_product)} (${percent(row.product_confidence)})</span></td>
      <td>${esc(row.standard_importer_name)}<br><span class="muted">${percent(row.importer_confidence)}</span></td>
      <td>${esc(row.standard_exporter_name)}<br><span class="muted">${percent(row.exporter_confidence)}</span></td>
      <td>${esc(row.units)}<br><span class="muted">${esc(row.quantity_status)}</span></td>
      <td>${money(row.value_usd)}</td>
      <td class="score">${row.price_per_kg == null ? "Missing" : money(row.price_per_kg)}</td>
      <td>${statusText(row.data_status)}</td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function renderProductReview(rows) {
  const container = document.getElementById("productReviewTable");
  document.getElementById("productReviewCount").textContent = `${rows.length} rows`;
  if (!rows.length) {
    container.innerHTML = `<div class="empty">Upload trade data to create product mapping suggestions.</div>`;
    return;
  }
  container.innerHTML = `<table>
    <thead>
      <tr>
        <th>Raw Product Description</th>
        <th>Suggested Standard Product</th>
        <th>Confidence</th>
        <th>Reason</th>
        <th>Status</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_product_description)}</strong></td>
      <td>${productSelect(row.id, row.approved_standard_product || row.suggested_standard_product)}</td>
      <td class="${confidenceClass(row.confidence_score)}">${percent(row.confidence_score)}</td>
      <td class="reason-cell">${esc(row.reason_for_suggestion || "")}</td>
      <td>${statusText(row.status)}</td>
      <td class="action-cell"><div class="mapping-actions">
        <button class="small" onclick="mappingAction('product', ${row.id}, 'approve')">Approve</button>
        <button class="small secondary" onclick="mappingAction('product', ${row.id}, 'edit')">Edit</button>
        <button class="small ghost" onclick="mappingAction('product', ${row.id}, 'reject')">Reject</button>
      </div></td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function renderCompanyReview(rows) {
  const container = document.getElementById("companyReviewTable");
  document.getElementById("companyReviewCount").textContent = `${rows.length} rows`;
  if (!rows.length) {
    container.innerHTML = `<div class="empty">Upload trade data to create company mapping suggestions.</div>`;
    return;
  }
  container.innerHTML = `<table>
    <thead>
      <tr>
        <th>Raw Company Name</th>
        <th>Suggested Standard Company</th>
        <th>Confidence</th>
        <th>Role</th>
        <th>Status</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_company_name)}</strong></td>
      <td><input class="inline-edit" id="company-map-${row.id}" value="${esc(row.approved_standard_company_name || row.suggested_standard_company_name)}" style="font-weight:bold;"></td>
      <td class="${confidenceClass(row.confidence_score)}">${percent(row.confidence_score)}</td>
      <td>${esc(row.source_roles || "")}</td>
      <td>${statusText(row.status)}</td>
      <td class="action-cell"><div class="mapping-actions">
        <button class="small" onclick="mappingAction('company', ${row.id}, 'approve')">Approve</button>
        <button class="small secondary" onclick="mappingAction('company', ${row.id}, 'edit')">Edit</button>
        <button class="small ghost" onclick="mappingAction('company', ${row.id}, 'reject')">Reject</button>
      </div></td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function toggleGroupExpand(index, groupName) {
  const body = document.getElementById(`company-group-body-${index}`);
  const icon = document.getElementById(`expand-icon-${index}`);
  if (body && icon) {
    const isHidden = body.classList.toggle("hidden");
    icon.classList.toggle("expanded", !isHidden);
    if (!isHidden) {
      expandedCompanyGroups.add(groupName);
    } else {
      expandedCompanyGroups.delete(groupName);
    }
  }
}

async function removeRawMapping(button, id) {
  await withBusy(button, "Removing...", async () => {
    try {
      await postJSON("/api/mapping-action", {
        kind: "company",
        id: id,
        action: "reject",
        value: ""
      });
      showToast("Removed variation from group. Re-running cleaning is recommended to update golden data.");
      await loadReview();
      await loadMappings();
    } catch (err) {
      showToast("Failed to remove variation: " + err.message, true);
    }
  });
}

async function assignUnassignedVariation(button, id) {
  const finalVal = document.getElementById(`unassigned-target-${id}`).value.trim();
  
  if (!finalVal) {
    showToast("Please select an existing group or type a new standard name.", true);
    return;
  }
  
  await withBusy(button, "Assigning...", async () => {
    try {
      await postJSON("/api/mapping-action", {
        kind: "company",
        id: id,
        action: "approve",
        value: finalVal
      });
      showToast(`Assigned variation to standard name "${finalVal}". Re-run cleaning to update golden data.`);
      await loadReview();
      await loadMappings();
    } catch (err) {
      showToast("Failed to assign variation: " + err.message, true);
    }
  });
}

function filterCompanyRegistry() {
  const searchInput = document.getElementById("companyRegistrySearch");
  if (!searchInput) return;
  const query = searchInput.value.toLowerCase().trim();
  const cards = document.querySelectorAll(".company-accordion-list .company-group-card");
  
  cards.forEach((card) => {
    const input = card.querySelector(".group-name-input");
    const name = input ? input.value.toLowerCase() : "";
    
    const rawItems = card.querySelectorAll(".raw-variation-item strong");
    let rawMatch = false;
    rawItems.forEach((item) => {
      if (item.textContent.toLowerCase().includes(query)) {
        rawMatch = true;
      }
    });

    if (name.includes(query) || rawMatch || card.id === "company-group-card-unassigned") {
      card.classList.remove("hidden");
    } else {
      card.classList.add("hidden");
    }
  });
}

function toggleSelectDropdown(id) {
  const dropdown = document.getElementById(`unassigned-options-${id}`);
  if (dropdown) {
    const isHidden = dropdown.classList.toggle("hidden");
    if (!isHidden) {
      document.querySelectorAll(".custom-select-options").forEach((el) => {
        if (el.id !== `unassigned-options-${id}`) el.classList.add("hidden");
      });
    }
  }
}

function filterSelectOptions(id) {
  const query = document.getElementById(`unassigned-target-${id}`).value.toLowerCase().trim();
  const dropdown = document.getElementById(`unassigned-options-${id}`);
  if (dropdown) {
    dropdown.classList.remove("hidden");
    const options = dropdown.querySelectorAll(".custom-select-option");
    options.forEach((opt) => {
      if (opt.textContent.toLowerCase().includes(query)) {
        opt.classList.remove("hidden");
      } else {
        opt.classList.add("hidden");
      }
    });
  }
}

function selectDropdownOption(id, value) {
  const input = document.getElementById(`unassigned-target-${id}`);
  const dropdown = document.getElementById(`unassigned-options-${id}`);
  if (input) {
    input.value = value;
  }
  if (dropdown) {
    dropdown.classList.add("hidden");
  }
}

function selectDropdownOptionAndFocus(id) {
  const input = document.getElementById(`unassigned-target-${id}`);
  const dropdown = document.getElementById(`unassigned-options-${id}`);
  if (input) {
    input.value = "";
    input.focus();
  }
  if (dropdown) {
    dropdown.classList.add("hidden");
  }
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".custom-select-wrapper")) {
    document.querySelectorAll(".custom-select-options").forEach((el) => el.classList.add("hidden"));
  }
});


function productSelect(id, value) {
  return `<select class="inline-edit" id="product-map-${id}">
    ${STANDARD_PRODUCTS.map((option) => `<option value="${esc(option)}" ${option === value ? "selected" : ""}>${esc(option)}</option>`).join("")}
  </select>`;
}

async function mappingAction(kind, id, action) {
  const valueEl = document.getElementById(`${kind}-map-${id}`);
  const value = valueEl ? valueEl.value.trim() : "";
  const result = await postJSON("/api/mapping-action", {kind, id, action, value});
  setStatus(`${result.kind} mapping ${result.status.toLowerCase()}. Click Re-run Cleaning to rebuild golden data.`);
  await loadReview();
  await loadMappings();
}

async function bulkApproveMappings(kind, minConfidence, button) {
  await withBusy(button, "Approving", async () => {
    const threshold = Number(minConfidence || 0.9);
    const result = await postJSON("/api/mapping-bulk-action", {kind, min_confidence: threshold});
    setStatus(`${result.approved_count} ${kind} mappings approved at ${Math.round(threshold * 100)}%+ confidence. Click Re-run Cleaning to rebuild golden data.`);
    await loadReview();
    await loadMappings();
  });
}

async function rerunCleaning(button) {
  await withBusy(button, "Re-running", async () => {
    const result = await postJSON("/api/rerun-cleaning", {});
    setStatus(`Cleaning re-run complete: ${result.clean_rows} rows regenerated, ${result.duplicates_removed} duplicates removed.`);
    await refreshAll();
    showPage("dashboard");
  });
}

function toggleProductGroupExpand(index, groupName) {
  const body = document.getElementById(`product-group-body-${index}`);
  const icon = document.getElementById(`product-expand-icon-${index}`);
  if (body && icon) {
    const isHidden = body.classList.toggle("hidden");
    icon.classList.toggle("expanded", !isHidden);
    if (!isHidden) {
      expandedProductGroups.add(groupName);
    } else {
      expandedProductGroups.delete(groupName);
    }
  }
}

async function removeProductRawMapping(button, id) {
  await withBusy(button, "Removing...", async () => {
    try {
      await postJSON("/api/mapping-action", {
        kind: "product",
        id: id,
        action: "reject",
        value: ""
      });
      showToast("Removed variation from group. Re-running cleaning is recommended to update golden data.");
      await loadReview();
      await loadMappings();
    } catch (err) {
      showToast("Failed to remove variation: " + err.message, true);
    }
  });
}

async function assignUnassignedProductVariation(button, id) {
  const finalVal = document.getElementById(`unassigned-product-target-${id}`).value.trim();
  
  if (!finalVal) {
    showToast("Please select a standard product.", true);
    return;
  }
  
  await withBusy(button, "Assigning...", async () => {
    try {
      await postJSON("/api/mapping-action", {
        kind: "product",
        id: id,
        action: "approve",
        value: finalVal
      });
      showToast(`Assigned variation to standard name "${finalVal}". Re-run cleaning to update golden data.`);
      await loadReview();
      await loadMappings();
    } catch (err) {
      showToast("Failed to assign variation: " + err.message, true);
    }
  });
}

function filterProductRegistry() {
  const searchInput = document.getElementById("productRegistrySearch");
  if (!searchInput) return;
  const query = searchInput.value.toLowerCase().trim();
  const cards = document.querySelectorAll("#productMappings .company-group-card");
  
  cards.forEach((card) => {
    const input = card.querySelector(".group-name-input");
    const name = input ? input.value.toLowerCase() : "";
    
    const rawItems = card.querySelectorAll(".raw-variation-item strong");
    let rawMatch = false;
    rawItems.forEach((item) => {
      if (item.textContent.toLowerCase().includes(query)) {
        rawMatch = true;
      }
    });

    if (name.includes(query) || rawMatch || card.id === "product-group-card-unassigned") {
      card.classList.remove("hidden");
    } else {
      card.classList.add("hidden");
    }
  });
}

function toggleProductSelectDropdown(id) {
  const dropdown = document.getElementById(`unassigned-product-options-${id}`);
  if (dropdown) {
    const isHidden = dropdown.classList.toggle("hidden");
    if (!isHidden) {
      document.querySelectorAll(".custom-select-options").forEach((el) => {
        if (el.id !== `unassigned-product-options-${id}`) el.classList.add("hidden");
      });
    }
  }
}

function filterProductSelectOptions(id) {
  const query = document.getElementById(`unassigned-product-target-${id}`).value.toLowerCase().trim();
  const dropdown = document.getElementById(`unassigned-product-options-${id}`);
  if (dropdown) {
    dropdown.classList.remove("hidden");
    const options = dropdown.querySelectorAll(".custom-select-option");
    options.forEach((opt) => {
      if (opt.textContent.toLowerCase().includes(query)) {
        opt.classList.remove("hidden");
      } else {
        opt.classList.add("hidden");
      }
    });
  }
}

function selectProductDropdownOption(id, value) {
  const input = document.getElementById(`unassigned-product-target-${id}`);
  const dropdown = document.getElementById(`unassigned-product-options-${id}`);
  if (input) {
    input.value = value;
  }
  if (dropdown) {
    dropdown.classList.add("hidden");
  }
}

function renderProductMappings(rows) {
  const container = document.getElementById("productMappings");
  if (!rows.length) {
    container.innerHTML = `<div class="empty">Import data to create product mapping rows.</div>`;
    return;
  }

  const groups = {};
  const unassignedRecords = [];

  rows.forEach((row) => {
    if (row.status === "Rejected" || (!row.approved_standard_product && !row.suggested_standard_product)) {
      unassignedRecords.push(row);
      return;
    }

    const std = row.approved_standard_product || row.suggested_standard_product || "Other / Review Required";
    if (!groups[std]) {
      groups[std] = {
        name: std,
        ids: [],
        raw_descriptions: [],
        records: [],
        avg_confidence: 0,
        reasons: new Set(),
        statuses: new Set(),
      };
    }
    const g = groups[std];
    g.ids.push(row.id);
    g.raw_descriptions.push(row.raw_product_description);
    g.records.push(row);
    g.avg_confidence += row.confidence_score;
    if (row.reason_for_suggestion) g.reasons.add(row.reason_for_suggestion);
    g.statuses.add(row.status);
  });

  const groupList = Object.values(groups).map((g) => {
    g.avg_confidence = g.avg_confidence / g.ids.length;
    g.reasons = Array.from(g.reasons).join("; ");
    if (g.statuses.has("Pending")) g.status = "Pending";
    else if (g.statuses.has("Rejected")) g.status = "Rejected";
    else g.status = "Approved";
    return g;
  });

  groupList.sort((a, b) => {
    const aPending = a.status === "Pending" ? 1 : 0;
    const bPending = b.status === "Pending" ? 1 : 0;
    if (aPending !== bPending) {
      return bPending - aPending;
    }
    return b.avg_confidence - a.avg_confidence;
  });

  const existingStandardNames = STANDARD_PRODUCTS;

  let unassignedHtml = "";
  if (unassignedRecords.length > 0) {
    unassignedRecords.sort((a, b) => a.raw_product_description.localeCompare(b.raw_product_description));
    const isExpanded = expandedProductGroups.has("UNASSIGNED_CARD");
    const bodyClass = isExpanded ? "" : "hidden";
    const iconClass = isExpanded ? "expanded" : "";
    
    unassignedHtml = `
    <div class="company-group-card" id="product-group-card-unassigned" style="border-color: var(--md-sys-color-error); background: rgba(211, 47, 47, 0.01);">
      <div class="company-group-header" onclick="toggleProductGroupExpand('unassigned', 'UNASSIGNED_CARD')" style="background: rgba(211, 47, 47, 0.03);">
        <div class="header-left">
          <span class="material-symbols-outlined expand-icon ${iconClass}" id="product-expand-icon-unassigned" style="color:var(--md-sys-color-error);">keyboard_arrow_right</span>
          <strong style="color:var(--md-sys-color-error); font-weight: 600;">⚠️ Unallocated / Rejected Variations</strong>
          <span class="pill error" style="background: var(--md-sys-color-error); color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 4px;">${unassignedRecords.length} variations</span>
        </div>
        <div class="header-right" onclick="event.stopPropagation();">
          <span class="badge rejected">Needs Action</span>
        </div>
      </div>
      <div class="company-group-body ${bodyClass}" id="product-group-body-unassigned">
        <div class="raw-variations-list">
          ${unassignedRecords.map((rec) => {
            const targetId = `unassigned-product-target-${rec.id}`;
            const dropdownId = `unassigned-product-options-${rec.id}`;
            return `
            <div class="raw-variation-item" style="padding: 12px 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
              <div class="raw-name-text" style="flex: 1; min-width: 200px;">
                <span class="material-symbols-outlined muted" style="font-size:16px;">help_outline</span>
                <strong>${esc(rec.raw_product_description)}</strong>
                <span class="pill confidence-pill ${confidenceClass(rec.confidence_score)}">${percent(rec.confidence_score)}</span>
              </div>
              <div class="raw-action" style="display: flex; gap: 8px; align-items: center; flex: 2; min-width: 300px; max-width: 600px;">
                
                <div class="custom-select-wrapper" style="position: relative; width: 100%; max-width: 450px;">
                  <input type="text" class="inline-edit custom-select-input" id="${targetId}" 
                         placeholder="Select standard product..." 
                         onclick="event.stopPropagation(); toggleProductSelectDropdown(${rec.id})" 
                         oninput="filterProductSelectOptions(${rec.id})" 
                         style="width: 100%; padding: 8px; border: 1px solid var(--md-sys-color-outline); border-radius: 4px; box-sizing: border-box; background: #fff; font-weight: 500;">
                  <span class="material-symbols-outlined" style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); pointer-events: none; color: var(--md-sys-color-on-surface-variant);">arrow_drop_down</span>
                  
                  <div class="custom-select-options hidden" id="${dropdownId}" 
                       style="position: absolute; top: 100%; left: 0; right: 0; max-height: 200px; overflow-y: auto; background: #fff; border: 1px solid var(--md-sys-color-outline); border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); z-index: 1000; margin-top: 4px;">
                    ${existingStandardNames.map((name) => `
                      <div class="custom-select-option" onclick="selectProductDropdownOption(${rec.id}, '${esc(name).replace(/'/g, "\\'")}')" 
                           style="padding: 8px 12px; cursor: pointer; font-size: 13px; text-align: left; transition: background 0.15s ease;">
                        ${esc(name)}
                      </div>
                    `).join("")}
                  </div>
                </div>

                <button class="small" onclick="event.stopPropagation(); assignUnassignedProductVariation(this, ${rec.id})">
                  <span class="material-symbols-outlined" style="font-size:16px; vertical-align:middle;">check</span> Assign
                </button>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>
    </div>`;
  }

  container.innerHTML = `<div class="company-accordion-list">
    ${groupList.map((g, index) => {
      const inputId = `product-group-input-${index}`;
      const idsJson = JSON.stringify(g.ids);
      const isExpanded = expandedProductGroups.has(g.name);
      const bodyClass = isExpanded ? "" : "hidden";
      const iconClass = isExpanded ? "expanded" : "";
      
      return `
      <div class="company-group-card" id="product-group-card-${index}">
        <div class="company-group-header" onclick="toggleProductGroupExpand(${index}, '${esc(g.name).replace(/'/g, "\\'")}')">
          <div class="header-left">
            <span class="material-symbols-outlined expand-icon ${iconClass}" id="product-expand-icon-${index}">keyboard_arrow_right</span>
            <input class="inline-edit group-name-input" id="${inputId}" value="${esc(g.name)}" readonly onclick="event.stopPropagation();" title="Standard product name" style="border:none; background:transparent;">
            <span class="pill secondary" style="font-size: 11px; padding: 2px 8px;">${g.records.length} variations</span>
          </div>
          <div class="header-right" onclick="event.stopPropagation();">
            ${statusText(g.status)}
            <div class="mapping-actions">
              <button class="small" onclick='mappingGroupAction(this, "product", ${idsJson}, "approve", "${inputId}")'>Approve Group</button>
              <button class="small ghost" onclick='mappingGroupAction(this, "product", ${idsJson}, "reject", "${inputId}")'>Reject</button>
            </div>
          </div>
        </div>
        <div class="company-group-body ${bodyClass}" id="product-group-body-${index}">
          <div class="raw-variations-list">
            ${g.records.map((rec) => `
              <div class="raw-variation-item">
                <div class="raw-name-text">
                  <span class="material-symbols-outlined muted" style="font-size:16px;">subdirectory_arrow_right</span>
                  <strong>${esc(rec.raw_product_description)}</strong>
                  <span class="pill confidence-pill ${confidenceClass(rec.confidence_score)}">${percent(rec.confidence_score)}</span>
                </div>
                <div class="raw-action">
                  <button class="small ghost danger-btn" onclick="event.stopPropagation(); removeProductRawMapping(this, ${rec.id})" title="Remove from this group">
                    <span class="material-symbols-outlined" style="font-size:16px; vertical-align:middle;">close</span> Remove
                  </button>
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      </div>`;
    }).join("")}
    ${unassignedHtml}
  </div>`;

  const miniHtml = rows.length ? `<table>
    <thead><tr><th>Raw Product Description</th><th>Approved Standard Product</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_product_description)}</strong></td>
      <td>${esc(row.approved_standard_product || row.suggested_standard_product)}</td>
      <td>${statusText(row.status)}</td>
    </tr>`).join("")}</tbody>
  </table>` : `<div class="empty">Import data to create product mapping rows.</div>`;
  const miniTable = document.getElementById("productMiniTable");
  if (miniTable) miniTable.innerHTML = miniHtml;

  filterProductRegistry();
}

function toggleCountryGroupExpand(index, groupName) {
  const body = document.getElementById(`country-group-body-${index}`);
  const icon = document.getElementById(`country-expand-icon-${index}`);
  if (body && icon) {
    const isHidden = body.classList.toggle("hidden");
    icon.classList.toggle("expanded", !isHidden);
    if (!isHidden) {
      expandedCountryGroups.add(groupName);
    } else {
      expandedCountryGroups.delete(groupName);
    }
  }
}

async function removeCountryRawMapping(button, id) {
  await withBusy(button, "Removing...", async () => {
    try {
      await postJSON("/api/mapping-action", {
        kind: "country",
        id: id,
        action: "reject",
        value: ""
      });
      showToast("Removed variation from group. Re-running cleaning is recommended to update golden data.");
      await loadReview();
      await loadMappings();
    } catch (err) {
      showToast("Failed to remove variation: " + err.message, true);
    }
  });
}

async function assignUnassignedCountryVariation(button, id) {
  const finalVal = document.getElementById(`unassigned-country-target-${id}`).value.trim();
  
  if (!finalVal) {
    showToast("Please select an existing group or type a new standard country name.", true);
    return;
  }
  
  await withBusy(button, "Assigning...", async () => {
    try {
      await postJSON("/api/mapping-action", {
        kind: "country",
        id: id,
        action: "approve",
        value: finalVal
      });
      showToast(`Assigned variation to standard country name "${finalVal}". Re-run cleaning to update golden data.`);
      await loadReview();
      await loadMappings();
    } catch (err) {
      showToast("Failed to assign variation: " + err.message, true);
    }
  });
}

function filterCountryRegistry() {
  const searchInput = document.getElementById("countryRegistrySearch");
  if (!searchInput) return;
  const query = searchInput.value.toLowerCase().trim();
  const cards = document.querySelectorAll("#countryMappings .company-group-card");
  
  cards.forEach((card) => {
    const input = card.querySelector(".group-name-input");
    const name = input ? input.value.toLowerCase() : "";
    
    const rawItems = card.querySelectorAll(".raw-variation-item strong");
    let rawMatch = false;
    rawItems.forEach((item) => {
      if (item.textContent.toLowerCase().includes(query)) {
        rawMatch = true;
      }
    });

    if (name.includes(query) || rawMatch || card.id === "country-group-card-unassigned") {
      card.classList.remove("hidden");
    } else {
      card.classList.add("hidden");
    }
  });
}

function toggleCountrySelectDropdown(id) {
  const dropdown = document.getElementById(`unassigned-country-options-${id}`);
  if (dropdown) {
    const isHidden = dropdown.classList.toggle("hidden");
    if (!isHidden) {
      document.querySelectorAll(".custom-select-options").forEach((el) => {
        if (el.id !== `unassigned-country-options-${id}`) el.classList.add("hidden");
      });
    }
  }
}

function filterCountrySelectOptions(id) {
  const query = document.getElementById(`unassigned-country-target-${id}`).value.toLowerCase().trim();
  const dropdown = document.getElementById(`unassigned-country-options-${id}`);
  if (dropdown) {
    dropdown.classList.remove("hidden");
    const options = dropdown.querySelectorAll(".custom-select-option");
    options.forEach((opt) => {
      if (opt.textContent.toLowerCase().includes(query)) {
        opt.classList.remove("hidden");
      } else {
        opt.classList.add("hidden");
      }
    });
  }
}

function selectCountryDropdownOption(id, value) {
  const input = document.getElementById(`unassigned-country-target-${id}`);
  const dropdown = document.getElementById(`unassigned-country-options-${id}`);
  if (input) {
    input.value = value;
  }
  if (dropdown) {
    dropdown.classList.add("hidden");
  }
}

function selectCountryDropdownOptionAndFocus(id) {
  const input = document.getElementById(`unassigned-country-target-${id}`);
  const dropdown = document.getElementById(`unassigned-country-options-${id}`);
  if (input) {
    input.value = "";
    input.focus();
  }
  if (dropdown) {
    dropdown.classList.add("hidden");
  }
}

function renderCountryMappings(rows) {
  const container = document.getElementById("countryMappings");
  if (!rows.length) {
    container.innerHTML = `<div class="empty">Import data to create country mapping rows.</div>`;
    return;
  }

  const groups = {};
  const unassignedRecords = [];

  rows.forEach((row) => {
    if (row.status === "Rejected" || (!row.approved_standard_country_name && !row.suggested_standard_country_name)) {
      unassignedRecords.push(row);
      return;
    }

    const std = row.approved_standard_country_name || row.suggested_standard_country_name || "UNKNOWN";
    if (!groups[std]) {
      groups[std] = {
        name: std,
        ids: [],
        raw_names: [],
        records: [],
        avg_confidence: 0,
        roles: new Set(),
        reasons: new Set(),
        statuses: new Set(),
      };
    }
    const g = groups[std];
    g.ids.push(row.id);
    g.raw_names.push(row.raw_country_name);
    g.records.push(row);
    g.avg_confidence += row.confidence_score;
    if (row.source_roles) g.roles.add(row.source_roles);
    if (row.reason_for_suggestion) g.reasons.add(row.reason_for_suggestion);
    g.statuses.add(row.status);
  });

  const groupList = Object.values(groups).map((g) => {
    g.avg_confidence = g.avg_confidence / g.ids.length;
    g.roles = Array.from(g.roles).join(", ");
    g.reasons = Array.from(g.reasons).join("; ");
    if (g.statuses.has("Pending")) g.status = "Pending";
    else if (g.statuses.has("Rejected")) g.status = "Rejected";
    else g.status = "Approved";
    return g;
  });

  groupList.sort((a, b) => {
    const aPending = a.status === "Pending" ? 1 : 0;
    const bPending = b.status === "Pending" ? 1 : 0;
    if (aPending !== bPending) {
      return bPending - aPending;
    }
    return b.avg_confidence - a.avg_confidence;
  });

  const existingStandardNames = Object.keys(groups).sort();

  let unassignedHtml = "";
  if (unassignedRecords.length > 0) {
    unassignedRecords.sort((a, b) => a.raw_country_name.localeCompare(b.raw_country_name));
    const isExpanded = expandedCountryGroups.has("UNASSIGNED_CARD");
    const bodyClass = isExpanded ? "" : "hidden";
    const iconClass = isExpanded ? "expanded" : "";
    
    unassignedHtml = `
    <div class="company-group-card" id="country-group-card-unassigned" style="border-color: var(--md-sys-color-error); background: rgba(211, 47, 47, 0.01);">
      <div class="company-group-header" onclick="toggleCountryGroupExpand('unassigned', 'UNASSIGNED_CARD')" style="background: rgba(211, 47, 47, 0.03);">
        <div class="header-left">
          <span class="material-symbols-outlined expand-icon ${iconClass}" id="country-expand-icon-unassigned" style="color:var(--md-sys-color-error);">keyboard_arrow_right</span>
          <strong style="color:var(--md-sys-color-error); font-weight: 600;">⚠️ Unallocated / Rejected Variations</strong>
          <span class="pill error" style="background: var(--md-sys-color-error); color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 4px;">${unassignedRecords.length} variations</span>
        </div>
        <div class="header-right" onclick="event.stopPropagation();">
          <span class="badge rejected">Needs Action</span>
        </div>
      </div>
      <div class="company-group-body ${bodyClass}" id="country-group-body-unassigned">
        <div class="raw-variations-list">
          ${unassignedRecords.map((rec) => {
            const targetId = `unassigned-country-target-${rec.id}`;
            const dropdownId = `unassigned-country-options-${rec.id}`;
            return `
            <div class="raw-variation-item" style="padding: 12px 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
              <div class="raw-name-text" style="flex: 1; min-width: 200px;">
                <span class="material-symbols-outlined muted" style="font-size:16px;">help_outline</span>
                <strong>${esc(rec.raw_country_name)}</strong>
                <span class="pill confidence-pill ${confidenceClass(rec.confidence_score)}">${percent(rec.confidence_score)}</span>
                <span class="muted" style="font-size:11px;">(${esc(rec.source_roles || "")})</span>
              </div>
              <div class="raw-action" style="display: flex; gap: 8px; align-items: center; flex: 2; min-width: 300px; max-width: 600px;">
                
                <div class="custom-select-wrapper" style="position: relative; width: 100%; max-width: 450px;">
                  <input type="text" class="inline-edit custom-select-input" id="${targetId}" 
                         placeholder="Select existing or type new name..." 
                         onclick="event.stopPropagation(); toggleCountrySelectDropdown(${rec.id})" 
                         oninput="filterCountrySelectOptions(${rec.id})" 
                         style="width: 100%; padding: 8px; border: 1px solid var(--md-sys-color-outline); border-radius: 4px; box-sizing: border-box; background: #fff; font-weight: 500;">
                  <span class="material-symbols-outlined" style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); pointer-events: none; color: var(--md-sys-color-on-surface-variant);">arrow_drop_down</span>
                  
                  <div class="custom-select-options hidden" id="${dropdownId}" 
                       style="position: absolute; top: 100%; left: 0; right: 0; max-height: 200px; overflow-y: auto; background: #fff; border: 1px solid var(--md-sys-color-outline); border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); z-index: 1000; margin-top: 4px;">
                    <div class="custom-select-option" onclick="selectCountryDropdownOption(${rec.id}, '${esc(rec.raw_country_name).replace(/'/g, "\\'")}')" 
                         style="padding: 8px 12px; cursor: pointer; font-size: 13px; text-align: left; transition: background 0.15s ease; border-bottom: 1px dashed var(--md-sys-color-outline); font-weight: 600; color: var(--md-sys-color-primary);">
                      ✨ + Create New Group ("${esc(rec.raw_country_name)}")
                    </div>
                    <div class="custom-select-option" onclick="selectCountryDropdownOptionAndFocus(${rec.id})" 
                         style="padding: 8px 12px; cursor: pointer; font-size: 13px; text-align: left; transition: background 0.15s ease; border-bottom: 1px solid var(--md-sys-color-outline); font-weight: 600; color: var(--md-sys-color-secondary);">
                      ✍️ + Create New Group (type custom...)
                    </div>
                    ${existingStandardNames.map((name) => `
                      <div class="custom-select-option" onclick="selectCountryDropdownOption(${rec.id}, '${esc(name).replace(/'/g, "\\'")}')" 
                           style="padding: 8px 12px; cursor: pointer; font-size: 13px; text-align: left; transition: background 0.15s ease;">
                        ${esc(name)}
                      </div>
                    `).join("")}
                  </div>
                </div>

                <button class="small" onclick="event.stopPropagation(); assignUnassignedCountryVariation(this, ${rec.id})">
                  <span class="material-symbols-outlined" style="font-size:16px; vertical-align:middle;">check</span> Assign
                </button>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>
    </div>`;
  }

  container.innerHTML = `<div class="company-accordion-list">
    ${groupList.map((g, index) => {
      const inputId = `country-group-input-${index}`;
      const idsJson = JSON.stringify(g.ids);
      const isExpanded = expandedCountryGroups.has(g.name);
      const bodyClass = isExpanded ? "" : "hidden";
      const iconClass = isExpanded ? "expanded" : "";
      
      return `
      <div class="company-group-card" id="country-group-card-${index}">
        <div class="company-group-header" onclick="toggleCountryGroupExpand(${index}, '${esc(g.name).replace(/'/g, "\\'")}')">
          <div class="header-left">
            <span class="material-symbols-outlined expand-icon ${iconClass}" id="country-expand-icon-${index}">keyboard_arrow_right</span>
            <input class="inline-edit group-name-input" id="${inputId}" value="${esc(g.name)}" onclick="event.stopPropagation();" title="Edit standard country name">
            <span class="pill secondary" style="font-size: 11px; padding: 2px 8px;">${g.records.length} variations</span>
          </div>
          <div class="header-right" onclick="event.stopPropagation();">
            ${statusText(g.status)}
            <div class="mapping-actions">
              <button class="small" onclick='mappingGroupAction(this, "country", ${idsJson}, "approve", "${inputId}")'>Approve Group</button>
              <button class="small ghost" onclick='mappingGroupAction(this, "country", ${idsJson}, "reject", "${inputId}")'>Reject</button>
            </div>
          </div>
        </div>
        <div class="company-group-body ${bodyClass}" id="country-group-body-${index}">
          <div class="raw-variations-list">
            ${g.records.map((rec) => `
              <div class="raw-variation-item">
                <div class="raw-name-text">
                  <span class="material-symbols-outlined muted" style="font-size:16px;">subdirectory_arrow_right</span>
                  <strong>${esc(rec.raw_country_name)}</strong>
                  <span class="pill confidence-pill ${confidenceClass(rec.confidence_score)}">${percent(rec.confidence_score)}</span>
                  <span class="muted" style="font-size:11px;">(${esc(rec.source_roles || "")})</span>
                </div>
                <div class="raw-action">
                  <button class="small ghost danger-btn" onclick="event.stopPropagation(); removeCountryRawMapping(this, ${rec.id})" title="Remove from this group">
                    <span class="material-symbols-outlined" style="font-size:16px; vertical-align:middle;">close</span> Remove
                  </button>
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      </div>`;
    }).join("")}
    ${unassignedHtml}
  </div>`;

  filterCountryRegistry();
}


function renderCompanyMappings(rows) {
  const container = document.getElementById("companyMappings");
  if (!rows.length) {
    container.innerHTML = `<div class="empty">Import data to create company mapping rows.</div>`;
    return;
  }

  // Group company mapping rows by suggested/approved standard name, excluding unassigned/rejected ones
  const groups = {};
  const unassignedRecords = [];
  
  rows.forEach((row) => {
    if (row.status === "Rejected" || (!row.approved_standard_company_name && !row.suggested_standard_company_name)) {
      unassignedRecords.push(row);
      return;
    }

    const std = row.approved_standard_company_name || row.suggested_standard_company_name || "UNKNOWN";
    if (!groups[std]) {
      groups[std] = {
        name: std,
        ids: [],
        raw_names: [],
        records: [],
        avg_confidence: 0,
        roles: new Set(),
        reasons: new Set(),
        statuses: new Set(),
      };
    }
    const g = groups[std];
    g.ids.push(row.id);
    g.raw_names.push(row.raw_company_name);
    g.records.push(row);
    g.avg_confidence += row.confidence_score;
    if (row.source_roles) g.roles.add(row.source_roles);
    if (row.reason_for_suggestion) g.reasons.add(row.reason_for_suggestion);
    g.statuses.add(row.status);
  });

  // Calculate average confidence and format group properties
  const groupList = Object.values(groups).map((g) => {
    g.avg_confidence = g.avg_confidence / g.ids.length;
    g.roles = Array.from(g.roles).join(", ");
    g.reasons = Array.from(g.reasons).join("; ");
    if (g.statuses.has("Pending")) g.status = "Pending";
    else if (g.statuses.has("Rejected")) g.status = "Rejected";
    else g.status = "Approved";
    return g;
  });

  // Sort groups: Pending first (so unapproved ones appear on top), then by confidence
  groupList.sort((a, b) => {
    const aPending = a.status === "Pending" ? 1 : 0;
    const bPending = b.status === "Pending" ? 1 : 0;
    if (aPending !== bPending) {
      return bPending - aPending;
    }
    return b.avg_confidence - a.avg_confidence;
  });

  const existingStandardNames = Object.keys(groups).sort();

  let unassignedHtml = "";
  if (unassignedRecords.length > 0) {
    unassignedRecords.sort((a, b) => a.raw_company_name.localeCompare(b.raw_company_name));
    const isExpanded = expandedCompanyGroups.has("UNASSIGNED_CARD");
    const bodyClass = isExpanded ? "" : "hidden";
    const iconClass = isExpanded ? "expanded" : "";
    
    unassignedHtml = `
    <div class="company-group-card" id="company-group-card-unassigned" style="border-color: var(--md-sys-color-error); background: rgba(211, 47, 47, 0.01);">
      <div class="company-group-header" onclick="toggleGroupExpand('unassigned', 'UNASSIGNED_CARD')" style="background: rgba(211, 47, 47, 0.03);">
        <div class="header-left">
          <span class="material-symbols-outlined expand-icon ${iconClass}" id="expand-icon-unassigned" style="color:var(--md-sys-color-error);">keyboard_arrow_right</span>
          <strong style="color:var(--md-sys-color-error); font-weight: 600;">⚠️ Unallocated / Rejected Variations</strong>
          <span class="pill error" style="background: var(--md-sys-color-error); color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 4px;">${unassignedRecords.length} variations</span>
        </div>
        <div class="header-right" onclick="event.stopPropagation();">
          <span class="badge rejected">Needs Action</span>
        </div>
      </div>
      <div class="company-group-body ${bodyClass}" id="company-group-body-unassigned">
        <div class="raw-variations-list">
          ${unassignedRecords.map((rec) => {
            const targetId = `unassigned-target-${rec.id}`;
            const dropdownId = `unassigned-options-${rec.id}`;
            return `
            <div class="raw-variation-item" style="padding: 12px 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
              <div class="raw-name-text" style="flex: 1; min-width: 200px;">
                <span class="material-symbols-outlined muted" style="font-size:16px;">help_outline</span>
                <strong>${esc(rec.raw_company_name)}</strong>
                <span class="pill confidence-pill ${confidenceClass(rec.confidence_score)}">${percent(rec.confidence_score)}</span>
                <span class="muted" style="font-size:11px;">(${esc(rec.source_roles || "")})</span>
              </div>
              <div class="raw-action" style="display: flex; gap: 8px; align-items: center; flex: 2; min-width: 300px; max-width: 600px;">
                
                <div class="custom-select-wrapper" style="position: relative; width: 100%; max-width: 450px;">
                  <input type="text" class="inline-edit custom-select-input" id="${targetId}" 
                         placeholder="Select existing or type new name..." 
                         onclick="event.stopPropagation(); toggleSelectDropdown(${rec.id})" 
                         oninput="filterSelectOptions(${rec.id})" 
                         style="width: 100%; padding: 8px; border: 1px solid var(--md-sys-color-outline); border-radius: 4px; box-sizing: border-box; background: #fff; font-weight: 500;">
                  <span class="material-symbols-outlined" style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); pointer-events: none; color: var(--md-sys-color-on-surface-variant);">arrow_drop_down</span>
                  
                  <div class="custom-select-options hidden" id="${dropdownId}" 
                       style="position: absolute; top: 100%; left: 0; right: 0; max-height: 200px; overflow-y: auto; background: #fff; border: 1px solid var(--md-sys-color-outline); border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); z-index: 1000; margin-top: 4px;">
                    <div class="custom-select-option" onclick="selectDropdownOption(${rec.id}, '${esc(rec.raw_company_name).replace(/'/g, "\\'")}')" 
                         style="padding: 8px 12px; cursor: pointer; font-size: 13px; text-align: left; transition: background 0.15s ease; border-bottom: 1px dashed var(--md-sys-color-outline); font-weight: 600; color: var(--md-sys-color-primary);">
                      ✨ + Create New Group ("${esc(rec.raw_company_name)}")
                    </div>
                    <div class="custom-select-option" onclick="selectDropdownOptionAndFocus(${rec.id})" 
                         style="padding: 8px 12px; cursor: pointer; font-size: 13px; text-align: left; transition: background 0.15s ease; border-bottom: 1px solid var(--md-sys-color-outline); font-weight: 600; color: var(--md-sys-color-secondary);">
                      ✍️ + Create New Group (type custom...)
                    </div>
                    ${existingStandardNames.map((name) => `
                      <div class="custom-select-option" onclick="selectDropdownOption(${rec.id}, '${esc(name).replace(/'/g, "\\'")}')" 
                           style="padding: 8px 12px; cursor: pointer; font-size: 13px; text-align: left; transition: background 0.15s ease;">
                        ${esc(name)}
                      </div>
                    `).join("")}
                  </div>
                </div>

                <button class="small" onclick="event.stopPropagation(); assignUnassignedVariation(this, ${rec.id})">
                  <span class="material-symbols-outlined" style="font-size:16px; vertical-align:middle;">check</span> Assign
                </button>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>
    </div>`;
  }

  container.innerHTML = `<div class="company-accordion-list">
    ${groupList.map((g, index) => {
      const inputId = `company-group-input-${index}`;
      const idsJson = JSON.stringify(g.ids);
      const isExpanded = expandedCompanyGroups.has(g.name);
      const bodyClass = isExpanded ? "" : "hidden";
      const iconClass = isExpanded ? "expanded" : "";
      
      return `
      <div class="company-group-card" id="company-group-card-${index}">
        <div class="company-group-header" onclick="toggleGroupExpand(${index}, '${esc(g.name).replace(/'/g, "\\'")}')">
          <div class="header-left">
            <span class="material-symbols-outlined expand-icon ${iconClass}" id="expand-icon-${index}">keyboard_arrow_right</span>
            <input class="inline-edit group-name-input" id="${inputId}" value="${esc(g.name)}" onclick="event.stopPropagation();" title="Edit standard company name">
            <span class="pill secondary" style="font-size: 11px; padding: 2px 8px;">${g.records.length} variations</span>
          </div>
          <div class="header-right" onclick="event.stopPropagation();">
            ${statusText(g.status)}
            <div class="mapping-actions">
              <button class="small" onclick='mappingGroupAction(this, "company", ${idsJson}, "approve", "${inputId}")'>Approve Group</button>
              <button class="small ghost" onclick='mappingGroupAction(this, "company", ${idsJson}, "reject", "${inputId}")'>Reject</button>
            </div>
          </div>
        </div>
        <div class="company-group-body ${bodyClass}" id="company-group-body-${index}">
          <div class="raw-variations-list">
            ${g.records.map((rec) => `
              <div class="raw-variation-item">
                <div class="raw-name-text">
                  <span class="material-symbols-outlined muted" style="font-size:16px;">subdirectory_arrow_right</span>
                  <strong>${esc(rec.raw_company_name)}</strong>
                  <span class="pill confidence-pill ${confidenceClass(rec.confidence_score)}">${percent(rec.confidence_score)}</span>
                  <span class="muted" style="font-size:11px;">(${esc(rec.source_roles || "")})</span>
                </div>
                <div class="raw-action">
                  <button class="small ghost danger-btn" onclick="event.stopPropagation(); removeRawMapping(this, ${rec.id})" title="Remove from this group">
                    <span class="material-symbols-outlined" style="font-size:16px; vertical-align:middle;">close</span> Remove
                  </button>
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      </div>`;
    }).join("")}
    ${unassignedHtml}
  </div>`;

  // Update companyMiniTable in dashboard or quality summary as well
  const miniHtml = rows.length ? `<table>
    <thead><tr><th>Raw Company Name</th><th>Approved Standard Company</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_company_name)}</strong></td>
      <td>${esc(row.approved_standard_company_name || row.suggested_standard_company_name)}</td>
      <td>${statusText(row.status)}</td>
    </tr>`).join("")}</tbody>
  </table>` : `<div class="empty">Import data to create company mapping rows.</div>`;
  const miniTable = document.getElementById("companyMiniTable");
  if (miniTable) miniTable.innerHTML = miniHtml;

  // Re-apply filter if user is searching
  filterCompanyRegistry();
}

function clearFilters() {
  ["opProduct", "opImporterCountry", "opExporterCountry", "opImporter", "opExporter", "opYear", "opMonth", "opStatus"].forEach((id) => {
    document.getElementById(id).value = "";
  });
  loadOpportunities();
}

async function withBusy(button, label, task) {
  const original = button ? button.textContent : "";
  try {
    if (button) {
      button.disabled = true;
      button.textContent = label;
    }
    return await task();
  } catch (error) {
    setStatus(error.message || String(error), true);
    throw error;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

function setStatus(message, isError) {
  const el = document.getElementById("statusLine");
  el.textContent = message;
  el.classList.toggle("error", !!isError);
}

function setOutput(text) {
  document.getElementById("aiOutput").textContent = text || "";
}

async function copyOutput() {
  try {
    await navigator.clipboard.writeText(document.getElementById("aiOutput").textContent);
    setStatus("Output copied.");
  } catch {
    setStatus("Copy failed.", true);
  }
}

function statusText(value) {
  const text = String(value || "");
  const lower = text.toLowerCase();
  const cls = lower.includes("reject")
    ? "danger-text"
    : lower.includes("pending") || lower.includes("suggest") || lower.includes("needs") || lower.includes("review") || lower.includes("missing")
      ? "warning-text"
      : "approved-text";
  return `<span class="${cls}">${esc(text)}</span>`;
}

function confidenceClass(value) {
  const score = Number(value || 0);
  if (score >= 0.95) return "score";
  if (score >= 0.8) return "score-medium";
  if (score >= 0.6) return "warning-text";
  return "danger-text";
}

function formatValue(value) {
  if (typeof value === "string") return esc(value);
  return num(value);
}

function num(value) {
  const number = Number(value || 0);
  return number.toLocaleString(undefined, {maximumFractionDigits: 2});
}

function money(value) {
  const number = Number(value || 0);
  return `$${number.toLocaleString(undefined, {maximumFractionDigits: 2})}`;
}

function percent(value) {
  const number = Number(value || 0);
  return `${Math.round(number * 100)}%`;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function setTooltipTitles() {
  document.querySelectorAll("[data-tooltip]").forEach((el) => {
    el.setAttribute("title", el.getAttribute("data-tooltip"));
  });
}

setTooltipTitles();
window.addEventListener("popstate", async () => {
  const page = pathToPage(window.location.pathname);
  if (page === "opportunity-detail") await loadOpportunityDetailFromPath();
  if (page === "pitch") await loadPitchFromPath();
  if (page === "advisor") await loadGrowthAdvisor();
  showPage(page, false);
});
refreshAll()
  .then(async () => {
    await loadAutomationSettings();
    const page = pathToPage(window.location.pathname);
    if (page === "opportunity-detail") await loadOpportunityDetailFromPath();
    if (page === "pitch") await loadPitchFromPath();
    if (page === "advisor") await loadGrowthAdvisor();
    showPage(page, false);
  })
  .catch((error) => setStatus(error.message || String(error), true));

function pageToPath(page) {
  return {
    review: "/cleaning-review",
    dashboard: "/dashboard",
    opportunities: "/opportunities",
    "opportunity-detail": window.location.pathname.startsWith("/opportunities/") ? window.location.pathname : "/opportunities",
    pitch: window.location.pathname.startsWith("/pitch/") ? window.location.pathname : "/pitch",
    products: "/products",
    companies: "/companies",
    countries: "/countries",
    advisor: "/advisor",
  }[page] || "/";
}

function pathToPage(path) {
  if (/^\/opportunities\/[^/]+/.test(path)) return "opportunity-detail";
  if (/^\/pitch(\/[^/]+)?/.test(path)) return "pitch";
  if (path === "/advisor") return "advisor";
  return {
    "/cleaning-review": "review",
    "/dashboard": "dashboard",
    "/opportunities": "opportunities",
    "/products": "products",
    "/companies": "companies",
    "/countries": "countries",
  }[path] || "upload";
}


// --- Automated Scheduling Settings ---
async function loadAutomationSettings() {
  try {
    const settings = await getJSON("/api/settings");
    if (settings) {
      document.getElementById("autoSyncEnabled").checked = !!settings.auto_sync_enabled;
      document.getElementById("autoSyncInterval").value = String(settings.auto_sync_interval_hours || 24);
      document.getElementById("autoSyncQuery").value = settings.sync_query || "Duloxetine";
      
      const lblStatus = document.getElementById("lblSyncStatus");
      if (lblStatus) {
        lblStatus.textContent = settings.sync_status || "Idle";
        lblStatus.className = "pill " + (settings.sync_status?.toLowerCase().includes("success") ? "success" : settings.sync_status?.toLowerCase().includes("sync") ? "primary" : "warning");
      }
      
      const lblTime = document.getElementById("lblSyncTime");
      if (lblTime) {
        if (settings.last_sync_timestamp) {
          lblTime.textContent = new Date(settings.last_sync_timestamp * 1000).toLocaleString();
        } else {
          lblTime.textContent = "Never";
        }
      }
    }
  } catch (error) {
    showToast("Error loading automation settings: " + error.message, true);
  }
}

async function saveAutomationSettings(button) {
  await withBusy(button, "Saving...", async () => {
    const auto_sync_enabled = document.getElementById("autoSyncEnabled").checked ? 1 : 0;
    const auto_sync_interval_hours = parseInt(document.getElementById("autoSyncInterval").value) || 24;
    const sync_query = document.getElementById("autoSyncQuery").value.trim() || "Duloxetine";
    const chemdoze_email = document.getElementById("chemdozeEmail").value.trim();
    const chemdoze_password = document.getElementById("chemdozePassword").value;
    const sync_from_date = document.getElementById("chemdozeFromDate").value.trim() || "01/01/2020";
    const sync_to_date = document.getElementById("chemdozeToDate").value.trim() || "28/02/2026";
    
    const settings = await postJSON("/api/settings", {
      auto_sync_enabled,
      auto_sync_interval_hours,
      sync_query,
      chemdoze_email,
      chemdoze_password,
      sync_from_date,
      sync_to_date
    });
    
    showToast("Automation settings saved successfully!");
    await loadAutomationSettings();
  });
}

// --- Import Local Downloads Excel File ---
async function importLocalDownloadsFile(button) {
  await withBusy(button, "Syncing File...", async () => {
    setStatus("Cleaning and importing local downloads file...");
    try {
      const result = await postJSON("/api/import-downloads-file", {});
      renderImportResult(result);
      await refreshAll();
      setStatus(`Direct Downloads import complete: ${result.clean_rows} rows imported. Mappings updated!`);
      showToast("Downloads file imported successfully!");
      showPage("review");
    } catch (err) {
      setStatus(err.message || String(err), true);
      showToast(err.message || "Failed to find downloads Excel file.", true);
    }
  });
}

// --- Client-Side PDF Generation ---
function downloadPitchPDF() {
  const element = document.getElementById("pitchContent");
  if (!element || element.textContent.includes("No pitch loaded yet")) {
    showToast("Load a pitch in the workspace first.", true);
    return;
  }
  
  // Extract company name for the PDF filename
  const heading = element.querySelector("h2") || element.querySelector("h1");
  let customerName = "Customer";
  if (heading) {
    const text = heading.textContent;
    const match = text.match(/customer\s*:\s*([^$\n]+)/i) || text.match(/target\s*customer\s*:\s*([^$\n]+)/i);
    if (match) customerName = match[1].trim();
  }
  
  const opt = {
    margin:       [15, 15],
    filename:     customerName.replace(/[^A-Za-z0-9]+/g, "_") + "_Duloxetine_Pitch_Report.pdf",
    image:        { type: 'jpeg', quality: 0.98 },
    html2canvas:  { scale: 2, useCORS: true },
    jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' }
  };
  
  showToast("Generating PDF report...");
  html2pdf().set(opt).from(element).save()
    .then(() => {
      showToast("PDF downloaded successfully!");
    })
    .catch((err) => {
      showToast("PDF generation failed: " + err.message, true);
    });
}

// --- Outreach Composer Dialog (Modal) ---
function openOutreachComposer() {
  const content = document.getElementById("pitchContent");
  if (!content || content.textContent.includes("No pitch loaded yet")) {
    showToast("Generate a pitch first before opening the composer.", true);
    return;
  }
  
  // Try to locate selected opportunity details
  let customerEmail = "";
  let subject = "Duloxetine API & Pellets Supply Collaboration - Shodhana Labs";
  let body = "";
  
  // Find email from page elements
  const emailDraftArea = document.getElementById("activeEmailDraft");
  if (emailDraftArea) {
    body = emailDraftArea.textContent || emailDraftArea.innerText;
    // Extract subject line if present in body
    const matchSub = body.match(/Subject\s*:\s*([^\n]+)/i);
    if (matchSub) {
      subject = matchSub[1].trim();
      body = body.substring(body.indexOf("\n", body.indexOf(subject)) + 1).trim();
    }
  }
  
  // Pre-fill importer contact details if available in detail
  if (pitchData && pitchData.detail && pitchData.detail.opportunity) {
    const opp = pitchData.detail.opportunity;
    if (opp.importer) {
      // Create a mock email address like purchasing@importername.com
      const domain = opp.importer.toLowerCase().replace(/[^a-z0-9]+/g, "") + ".com";
      customerEmail = "purchasing@" + domain;
    }
  }
  
  document.getElementById("emailRecipient").value = customerEmail;
  document.getElementById("emailSubject").value = subject;
  document.getElementById("emailBody").value = body;
  
  document.getElementById("emailModal").classList.remove("hidden");
}

function closeEmailModal() {
  document.getElementById("emailModal").classList.add("hidden");
}

function openMailtoLink() {
  const to = document.getElementById("emailRecipient").value;
  const sub = document.getElementById("emailSubject").value;
  const body = document.getElementById("emailBody").value;
  
  const link = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(sub)}&body=${encodeURIComponent(body)}`;
  window.open(link, "_blank");
}

async function sendEmailAction(button) {
  const to = document.getElementById("emailRecipient").value.trim();
  const sub = document.getElementById("emailSubject").value.trim();
  const body = document.getElementById("emailBody").value.trim();
  
  if (!to) {
    showToast("Recipient email is required.", true);
    return;
  }
  
  // Use current opportunity ID if available
  const oppId = pitchData?.opportunity_id || pitchData?.detail?.opportunity?.opportunity_id || "general";
  
  await withBusy(button, "Sending...", async () => {
    try {
      await postJSON("/api/send-email", {
        opportunity_id: oppId,
        recipient_email: to,
        subject: sub,
        body: body
      });
      showToast("Email dispatched and logged successfully!");
      closeEmailModal();
      await loadSentEmailsList();
    } catch (err) {
      showToast("Failed to send: " + err.message, true);
    }
  });
}

// --- Display Sent Email Logs ---
async function loadSentEmailsList() {
  const container = document.getElementById("sentEmailsLogs");
  if (!container) return;
  
  const oppId = pitchData?.opportunity_id || pitchData?.detail?.opportunity?.opportunity_id || "general";
  try {
    const res = await getJSON(`/api/sent-emails?opportunity_id=${oppId}`);
    const rows = res.rows || [];
    if (rows.length === 0) {
      container.innerHTML = `<p style="font-size:12px; color:var(--md-sys-color-on-surface-variant); margin-top:8px;">No email history recorded for this lead.</p>`;
      return;
    }
    
    container.innerHTML = rows.map((row) => `
      <div style="border:1px solid var(--md-sys-color-outline); border-radius:8px; padding:12px; margin-top:8px; background:#fff;">
        <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:500; color:var(--md-sys-color-on-surface-variant); margin-bottom:6px;">
          <span>To: <strong>${esc(row.recipient_email)}</strong></span>
          <span>${new Date(row.sent_at * 1000).toLocaleString()}</span>
        </div>
        <div style="font-size:13px; font-weight:600; margin-bottom:4px;">Subject: ${esc(row.subject)}</div>
        <div style="font-size:12px; white-space:pre-wrap; max-height:80px; overflow:auto; color:var(--md-sys-color-on-surface-variant); background:#fcfcfc; padding:8px; border-radius:4px; border:1px solid #f0f0f0;">${esc(row.body)}</div>
      </div>
    `).join("");
  } catch (e) {
    console.error("Error loading sent emails:", e);
  }
}

// --- Toast Notification Helper ---
function showToast(message, isError = false) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  if (isError) {
    toast.style.background = "#fce8e6";
    toast.style.color = "var(--md-sys-color-error)";
  }
  toast.innerHTML = `<span class="material-symbols-outlined" style="font-size: 20px;">${isError ? 'error' : 'check_circle'}</span> ${esc(message)}`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(20px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// --- Group Mapping Actions ---
async function mappingGroupAction(button, kind, ids, action, valueInputId) {
  const valueEl = document.getElementById(valueInputId);
  const value = valueEl ? valueEl.value.trim() : "";
  
  let label = "Approving...";
  if (action === "edit") label = "Applying...";
  if (action === "reject") label = "Rejecting...";
  
  await withBusy(button, label, async () => {
    try {
      // Process sequentially to avoid SQLite database locks
      for (const id of ids) {
        await postJSON("/api/mapping-action", {kind, id, action, value});
      }
      showToast(`Successfully processed group action (${action}) for ${ids.length} mappings.`);
      setStatus(`Group mapping ${action} completed. Click Re-run Cleaning to rebuild golden data.`);
      await loadReview();
      await loadMappings();
    } catch (err) {
      showToast("Failed to process group action: " + err.message, true);
    }
  });
}

// --- AI Growth Advisor Controllers ---
async function loadGrowthAdvisor() {
  try {
    const data = await getJSON("/api/growth-insights");
    renderGrowthAdvisor(data);
  } catch (err) {
    console.error("Failed to load growth insights:", err);
  }
}

function renderGrowthAdvisor(data) {
  // 1. Top Target Sourcing Accounts
  const targetsContainer = document.getElementById("advisorTargetAccounts");
  if (!data.target_accounts || data.target_accounts.length === 0) {
    targetsContainer.innerHTML = '<div class="empty">No high opportunity targets identified. Load more data first.</div>';
  } else {
    targetsContainer.innerHTML = data.target_accounts.map(ta => `
      <div class="advisor-card">
        <div class="advisor-card-title">${esc(ta.importer)}</div>
        <div class="advisor-card-meta">${esc(ta.country)} • ${esc(ta.product)}</div>
        <div style="font-size: 13px; line-height: 1.4; margin-bottom: 8px;">
          <strong>Competitor Supplier:</strong> ${esc(ta.competitor)}<br>
          <strong>Sourced Volume:</strong> ${num(ta.volume_kg)} KG<br>
          <strong>Average Price:</strong> $${num(ta.avg_price)}/KG
        </div>
        <div class="advisor-card-tags">
          <span class="advisor-tag high">Score ${ta.score}</span>
          ${ta.reasons.slice(0, 2).map(r => `<span class="advisor-tag">${esc(r)}</span>`).join("")}
        </div>
        <button class="primary small" style="margin-top:12px; width:100%;" onclick="quickPitchFromAdvisor('${esc(ta.opportunity_id)}')">
          <span class="material-symbols-outlined" style="font-size:14px; vertical-align:middle; margin-right:4px;">campaign</span> Draft Sourcing Pitch
        </button>
      </div>
    `).join("");
  }

  // 2. Competitor Vulnerabilities
  const competitorsContainer = document.getElementById("advisorCompetitors");
  if (!data.vulnerable_competitors || data.vulnerable_competitors.length === 0) {
    competitorsContainer.innerHTML = '<div class="empty">No competitor vulnerabilities detected.</div>';
  } else {
    competitorsContainer.innerHTML = data.vulnerable_competitors.map(vc => `
      <div class="vulnerability-item">
        <div class="vulnerability-title">${esc(vc.competitor)}</div>
        <div class="vulnerability-desc">
          <strong>Supplied Volume:</strong> ${num(vc.volume_kg)} KG across ${vc.clients_count} client(s)<br>
          <strong>Average Pricing:</strong> $${num(vc.avg_price)}/KG<br>
          <span style="color:var(--md-sys-color-error); font-weight:500;">Weaknesses:</span> ${vc.vulnerability_reasons.join(", ")}
        </div>
      </div>
    `).join("");
  }

  // 3. Regional Entry Strategies
  const regionsContainer = document.getElementById("advisorRegions");
  if (!data.regional_strategies || data.regional_strategies.length === 0) {
    regionsContainer.innerHTML = '<div class="empty">No market entry recommendations available.</div>';
  } else {
    regionsContainer.innerHTML = data.regional_strategies.map(rs => `
      <div class="region-item">
        <div class="region-title">${esc(rs.country)}</div>
        <div class="region-desc">
          <strong>Market Size:</strong> ${num(rs.total_volume_kg)} KG<br>
          <strong>Shodhana Share:</strong> ${rs.shodhana_share_pct}% (${rs.competitors_count} active competitors)<br>
          <span style="color:var(--md-sys-color-secondary); font-weight:500;">Signals:</span> ${rs.recommendation_reasons.join(", ")}
        </div>
      </div>
    `).join("");
  }

  // 4. Dynamic Pricing Matrix
  const matrixBody = document.getElementById("advisorPricingBody");
  const categories = Object.keys(data.pricing_matrix || {});
  if (categories.length === 0) {
    matrixBody.innerHTML = '<tr><td colspan="5" class="empty">No pricing observations found.</td></tr>';
  } else {
    matrixBody.innerHTML = categories.map(cat => {
      const pm = data.pricing_matrix[cat];
      return `
        <tr>
          <td><strong>${esc(cat)}</strong></td>
          <td>$${num(pm.observed_min)}</td>
          <td>$${num(pm.observed_avg)}</td>
          <td>$${num(pm.observed_max)}</td>
          <td><span class="pill success">${esc(pm.suggested_pitch_range)}</span></td>
        </tr>
      `;
    }).join("");
  }
}

async function quickPitchFromAdvisor(oppId) {
  showPage("pitch");
  await openPitch(oppId);
}

function downloadPptxDeck() {
  const id = pitchData?.opportunity_id || pitchData?.detail?.opportunity?.opportunity_id;
  if (!id) {
    setStatus("Select an opportunity to download PowerPoint presentation.", true);
    return;
  }
  window.location.href = `/api/export/pitch-deck?opportunity_id=${encodeURIComponent(id)}`;
}

async function runAiAutoMapper(button) {
  await withBusy(button, "Auto-Mapping", async () => {
    setStatus("Running AI Auto-Mapper agent...");
    try {
      const result = await postJSON("/api/mappings/auto-map", {});
      await refreshAll();
      setStatus(`AI Auto-Mapper finished: Standardized ${result.updated_products} products, ${result.updated_companies} companies, and ${result.updated_countries} countries.`);
      showToast("AI Auto-Mapping complete!");
    } catch (err) {
      showToast("AI Auto-Mapping failed: " + err.message, true);
    }
  });
}
