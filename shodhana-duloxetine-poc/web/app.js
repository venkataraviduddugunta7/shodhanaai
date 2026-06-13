let dashboardData = null;
let opportunityRows = [];
let opportunityDetailData = null;
let pitchData = null;
let activeEmailTone = "formal";
let reviewData = {summary: {}, products: [], companies: [], issue_rows: []};
let mappingGroupData = {products: [], companies: [], countries: []};
let reviewFilter = "pending";
const STANDARD_PRODUCTS = [
  "Duloxetine API",
  "Duloxetine Pellets 17%",
  "Duloxetine Pellets 22.5%",
  "Duloxetine Pellets 25%",
  "Duloxetine Pellets",
  "Duloxetine Placebo Pellets",
  "Duloxetine Reference Standard / Impurity",
  "Other / Review Required",
];
const GROUP_KINDS = {
  products: {kind: "product", label: "Product Groups"},
  companies: {kind: "company", label: "Company Groups"},
  countries: {kind: "country", label: "Country Groups"},
};

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
  if (updateUrl) {
    const path = pageToPath(page);
    if (window.location.pathname !== path) window.history.pushState({page}, "", path);
  }
}

async function refreshAll() {
  await Promise.all([loadDashboard(), loadOpportunities(), loadMappings(), loadReview()]);
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

function renderProductOptionDatalist() {
  const datalist = document.getElementById("standardProductOptions");
  if (!datalist) return;
  datalist.innerHTML = STANDARD_PRODUCTS.map((option) => `<option value="${esc(option)}"></option>`).join("");
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
  const [review, groups] = await Promise.all([
    getJSON("/api/cleaning-review"),
    getJSON("/api/mapping-groups"),
  ]);
  reviewData = review;
  mappingGroupData = groups;
  renderReviewSummary(reviewData.summary || {});
  renderSmartConfirm(mappingGroupData);
  renderProductReview(reviewData.products || []);
  renderCompanyReview(reviewData.companies || []);
  renderCountryReview(reviewData.countries || []);
  renderIssueRows(reviewData.issue_rows || []);
}

function renderReviewSummary(summary) {
  const cards = [
    ["Total Raw Records", summary.total_raw_records],
    ["Cleaned Records", summary.cleaned_records],
    ["Product Mappings Applied", summary.product_mappings_applied],
    ["Company Mappings Applied", summary.company_mappings_applied],
    ["Country Mappings Applied", summary.country_mappings_applied],
    ["Review Required", summary.review_required_records],
    ["Valid KG Quantity", summary.valid_kg_records],
    ["Invalid Units", summary.invalid_qty_records],
    ["Price/KG Calculated", summary.price_records],
    ["Missing Value/Qty", summary.records_missing_value_or_quantity],
    ["Pending Product Maps", summary.pending_product_mappings],
    ["Pending Company Maps", summary.pending_company_mappings],
    ["Pending Country Maps", summary.pending_country_mappings],
    ["Duplicates Removed", summary.duplicates_removed],
  ];
  document.getElementById("reviewSummaryCards").innerHTML = cards.map(statCard).join("");
}

function renderSmartConfirm(groups) {
  const container = document.getElementById("smartConfirmCards");
  if (!container) return;
  container.innerHTML = Object.entries(GROUP_KINDS).map(([key, meta]) => {
    const rows = groups[key] || [];
    const needsConfirm = rows.reduce((sum, group) => sum + groupNeedsConfirm(group), 0);
    const approved = rows.reduce((sum, group) => sum + Number(group.approved_count || 0), 0);
    const aliases = rows.reduce((sum, group) => sum + Number(group.alias_count || 0), 0);
    return `<div class="smart-card">
      <div>
        <span>${esc(meta.label)}</span>
        <strong>${num(rows.length)} master groups</strong>
      </div>
      <div class="smart-metrics">
        <span>${num(aliases)} aliases</span>
        <span>${num(needsConfirm)} need confirm</span>
        <span>${num(approved)} approved</span>
      </div>
      <button class="small secondary" onclick="openSmartConfirmModal('${key}')">Review Groups</button>
    </div>`;
  }).join("");
}

function openSmartConfirmModal(activeKey = "") {
  const modal = document.getElementById("smartConfirmModal");
  const body = document.getElementById("smartConfirmModalBody");
  const keys = activeKey ? [activeKey] : Object.keys(GROUP_KINDS);
  body.innerHTML = keys.map((key) => smartConfirmSection(key, mappingGroupData[key] || [])).join("");
  modal.classList.remove("hidden");
}

function closeSmartConfirmModal() {
  document.getElementById("smartConfirmModal").classList.add("hidden");
}

function smartConfirmSection(key, groups) {
  const meta = GROUP_KINDS[key];
  if (!groups.length) {
    return `<section class="smart-section"><h3>${esc(meta.label)}</h3><div class="empty">No mapping groups yet.</div></section>`;
  }
  const ranked = groups
    .map((group, index) => ({group, index}))
    .sort((left, right) => {
      const leftReview = String(left.group.standard_value || "").toLowerCase().includes("review required") ? 1 : 0;
      const rightReview = String(right.group.standard_value || "").toLowerCase().includes("review required") ? 1 : 0;
      const leftGeneric = isGenericMappingGroup(left.group) ? 1 : 0;
      const rightGeneric = isGenericMappingGroup(right.group) ? 1 : 0;
      return (
        leftGeneric - rightGeneric
        || leftReview - rightReview
        || groupNeedsConfirm(right.group) - groupNeedsConfirm(left.group)
        || Number(right.group.max_confidence || 0) - Number(left.group.max_confidence || 0)
        || Number(right.group.alias_count || 0) - Number(left.group.alias_count || 0)
      );
    });
  const visible = ranked.filter((entry) => groupNeedsConfirm(entry.group) > 0).slice(0, 25);
  const display = visible;
  return `<section class="smart-section">
    <div class="smart-section-head">
      <h3>${esc(meta.label)}</h3>
      <span class="pill">Showing ${num(display.length)} of ${num(groups.length)} groups</span>
    </div>
    <div class="smart-group-list">
      ${display.length
        ? display.map((entry) => smartConfirmGroup(key, entry.group, entry.index)).join("")
        : `<div class="empty">No pending mapping groups for this section.</div>`}
    </div>
  </section>`;
}

function smartConfirmGroup(key, group, index) {
  const inputId = `smart-${key}-${index}`;
  const needsConfirm = groupNeedsConfirm(group);
  const confidence = `${percent(group.min_confidence)}-${percent(group.max_confidence)}`;
  const isRemaining = isRemainingMappingGroup(group);
  const actions = isRemaining
    ? `<button class="small" onclick="mappingGroupAction('${key}', ${index}, 'edit')">Save New Mapping</button>
       <button class="small ghost" onclick="mappingGroupAction('${key}', ${index}, 'reject')">Reject</button>`
    : `<button class="small" onclick="mappingGroupAction('${key}', ${index}, 'approve')">Confirm Group</button>
       <button class="small secondary" onclick="mappingGroupAction('${key}', ${index}, 'edit')">Save Edited</button>
       <button class="small ghost" onclick="mappingGroupAction('${key}', ${index}, 'reject')">Reject</button>`;
  return `<div class="smart-group">
    <div class="smart-group-main">
      <span class="eyebrow">${isRemaining ? "Create new mapping" : needsConfirm ? `${num(needsConfirm)} need confirm` : "Confirmed"}</span>
      ${smartGroupValueControl(key, inputId, group.standard_value)}
      <div class="smart-metrics">
        <span>${num(group.alias_count)} aliases</span>
        <span>${num(group.master_count || 0)} masters</span>
        <span>${confidence}</span>
        ${group.source_roles ? `<span>${esc(group.source_roles)}</span>` : ""}
      </div>
      ${aliasChecklist(key, group, index)}
    </div>
    <div class="smart-group-actions">
      ${actions}
    </div>
  </div>`;
}

function aliasChecklist(key, group, index) {
  const items = Array.isArray(group.items) && group.items.length
    ? group.items
    : (group.samples || []).map((sample, sampleIndex) => ({
        id: group.ids?.[sampleIndex] || 0,
        raw: sample,
        suggested: group.standard_value,
        status: "Pending",
        confidence: group.max_confidence || 0,
        is_master: 0,
      }));
  if (!items.length) return "";
  const controlKey = groupControlKey(key, index);
  const checkedCount = confirmableGroupIds(group).length;
  const isRemaining = isRemainingMappingGroup(group);
  const rows = items.map((item) => {
    const itemId = Number(item.id || 0);
    const isMaster = Number(item.is_master || 0) === 1;
    const isRejected = item.status === "Rejected";
    const checked = !isRejected ? "checked" : "";
    const disabled = !itemId ? "disabled" : "";
    const rowClass = [
      "alias-check-row",
      isMaster ? "alias-master" : "",
      isRejected ? "alias-rejected" : "",
    ].filter(Boolean).join(" ");
    const statusText = isMaster ? "Master" : isRejected ? "Rejected" : item.status || "Pending";
    const suggested = item.approved || item.suggested || group.standard_value || "";
    return `<label class="${rowClass}">
      <input type="checkbox" data-group="${esc(controlKey)}" value="${itemId}" ${checked} ${disabled}>
      <span>
        <strong>${esc(item.raw || "Unknown")}</strong>
        ${suggested ? `<em>${esc(suggested)}</em>` : ""}
      </span>
      <span class="alias-status">${esc(statusText)} · ${percent(item.confidence || 0)}</span>
    </label>`;
  }).join("");
  return `<div class="alias-review">
    <div class="alias-review-head">
      <span>${num(checkedCount)} selected for confirmation</span>
      <span>${isRemaining ? "Select aliases, type the new master name, then Save Edited." : "Uncheck aliases to move them into Remaining / Create New Mapping."}</span>
    </div>
    <div class="alias-check-list">${rows}</div>
  </div>`;
}

function smartGroupValueControl(key, inputId, value) {
  if (key === "products") {
    return `<input class="smart-value" list="standardProductOptions" id="${inputId}" value="${esc(value)}">`;
  }
  return `<input class="smart-value" id="${inputId}" value="${esc(value)}">`;
}

function groupNeedsConfirm(group) {
  if (group.needs_review_count !== undefined) {
    return Math.max(0, Number(group.needs_review_count || 0));
  }
  return Math.max(
    0,
    Number(group.pending_count || 0)
      + Number(group.approved_count || 0)
      - Number(group.master_count || 0)
  );
}

function groupControlKey(key, index) {
  return `group-${key}-${index}`;
}

function confirmableGroupIds(group) {
  const ids = (group.items || [])
    .filter((item) => item.status !== "Rejected")
    .map((item) => Number(item.id || 0))
    .filter(Boolean);
  return ids.length ? ids : (group.ids || []);
}

function selectedGroupIds(key, index, group) {
  const controls = Array.from(document.querySelectorAll(`input[data-group="${groupControlKey(key, index)}"]`));
  if (!controls.length) return confirmableGroupIds(group);
  return controls
    .filter((control) => control.checked)
    .map((control) => Number(control.value || 0))
    .filter(Boolean);
}

function excludedGroupIds(key, index, group) {
  const controls = Array.from(document.querySelectorAll(`input[data-group="${groupControlKey(key, index)}"]`));
  if (!controls.length) return [];
  const selected = new Set(selectedGroupIds(key, index, group));
  return (group.ids || [])
    .map((id) => Number(id || 0))
    .filter((id) => {
      const control = controls.find((item) => Number(item.value || 0) === id);
      return id && control && !control.disabled && !selected.has(id);
    });
}

function isGenericMappingGroup(group) {
  const value = String(group.standard_value || "").toLowerCase();
  return value.includes("to the order") || value === "unknown" || value === "n/a";
}

function isRemainingMappingGroup(group) {
  return String(group.standard_value || "").toLowerCase() === "remaining / create new mapping";
}

async function mappingGroupAction(key, index, action, silent = false) {
  const group = (mappingGroupData[key] || [])[index];
  if (!group) return;
  const input = document.getElementById(`smart-${key}-${index}`);
  const value = input ? input.value.trim() : group.standard_value;
  const ids = selectedGroupIds(key, index, group);
  if (!ids.length) {
    setStatus("Select at least one alias before saving this group.", true);
    return;
  }
  try {
    const wasOpen = !document.getElementById("smartConfirmModal").classList.contains("hidden");
    const result = await postJSON("/api/mapping-group-action", {
      kind: GROUP_KINDS[key].kind,
      ids,
      excluded_ids: action === "reject" ? [] : excludedGroupIds(key, index, group),
      action,
      value,
    });
    const rerun = await postJSON("/api/rerun-cleaning", {});
    await refreshAll();
    if (wasOpen) openSmartConfirmModal(key);
    if (!silent) {
      const removed = result.excluded ? `, ${result.excluded} removed from the group` : "";
      setStatus(`${result.updated} ${GROUP_KINDS[key].kind} mappings ${result.status.toLowerCase()} as ${result.approved || "rejected"}${removed}. Opportunities regenerated from ${rerun.clean_rows} cleaned rows.`);
    }
  } catch (error) {
    setStatus(error.message || String(error), true);
  }
}

async function approveConfidentGroups(button) {
  await withBusy(button, "Approving", async () => {
    let updated = 0;
    for (const key of Object.keys(GROUP_KINDS)) {
        const groups = mappingGroupData[key] || [];
      for (let index = 0; index < groups.length; index += 1) {
        const group = groups[index];
        const needsConfirm = groupNeedsConfirm(group);
        const minConfidence = Number(group.min_confidence || 0);
        const reviewRequired = String(group.standard_value || "").toLowerCase().includes("review required");
        if (needsConfirm && minConfidence >= 0.9 && !reviewRequired && !isGenericMappingGroup(group)) {
          const ids = confirmableGroupIds(group);
          await postJSON("/api/mapping-group-action", {
            kind: GROUP_KINDS[key].kind,
            ids,
            action: "approve",
            value: group.standard_value,
          });
          updated += ids.length;
        }
      }
    }
    if (updated) {
      const rerun = await postJSON("/api/rerun-cleaning", {});
      await refreshAll();
      setStatus(`Approved ${updated} confident aliases and regenerated ${rerun.clean_rows} clean rows.`);
    } else {
      await loadReview();
      await loadMappings();
      setStatus("No confident pending groups found.");
    }
  });
}

async function syncMasterMappings(button) {
  await withBusy(button, "Saving", async () => {
    const result = await postJSON("/api/sync-master-mappings", {});
    const parts = [
      `Products ${num(result.products?.rows || 0)}`,
      `Companies ${num(result.companies?.rows || 0)}`,
      `Countries ${num(result.countries?.rows || 0)}`,
    ];
    setStatus(`Saved confirmed mappings as defaults: ${parts.join(", ")}.`);
    await loadMappings();
    await loadReview();
  });
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
  const readiness = data.mapping_readiness || {};
  if (readiness.requires_review) {
    opportunityRows = [];
    document.getElementById("opportunityCount").textContent = "Mapping review required";
    renderOpportunityReviewGate(readiness);
    return;
  }
  opportunityRows = data.rows || [];
  document.getElementById("opportunityCount").textContent = `${opportunityRows.length} rows`;
  renderOpportunities(opportunityRows);
}

function renderOpportunityReviewGate(readiness) {
  const container = document.getElementById("opportunityTable");
  const samples = readiness.samples || [];
  const counts = readiness.by_kind || {};
  container.innerHTML = `<div class="review-gate">
    <div>
      <span class="eyebrow">Mapping Review Required</span>
      <h3>Confirm master mappings before using opportunities</h3>
      <p>There are ${num(readiness.total_groups || 0)} grouped mapping suggestions with ${num(readiness.total_aliases || 0)} aliases waiting for confirmation. Opportunities are hidden until the mapping layer is clean, so EVA PHARMA-style variants do not appear as separate customers.</p>
    </div>
    <div class="smart-metrics">
      <span>Products ${num(counts.products?.groups || 0)}</span>
      <span>Companies ${num(counts.companies?.groups || 0)}</span>
      <span>Countries ${num(counts.countries?.groups || 0)}</span>
    </div>
    <div class="review-gate-list">
      ${samples.slice(0, 6).map((group) => `<div>
        <strong>${esc(group.standard_value)}</strong>
        <span>${esc(group.kind)} · ${num(group.needs_review)} aliases need confirmation</span>
        <em>${esc((group.examples || []).join(" · "))}</em>
      </div>`).join("")}
    </div>
    <div class="button-row">
      <button onclick="showPage('review'); setTimeout(() => openSmartConfirmModal(), 0)">Open Mapping Review</button>
      <button class="secondary" onclick="showPage('review')">Go to Cleaning Review</button>
    </div>
  </div>`;
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
        <th>Status</th>
        <th>Score</th>
        <th>Category</th>
        <th>Recommended Action</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      ${rows.map((row, index) => `<tr>
        <td class="score">#${row.rank}</td>
        <td>
          <strong>${esc(row.importer)}</strong>
          ${mappingAliasNote(row.importer_aliases, "raw company names clubbed")}
          <br><span class="muted">${esc((row.reasons || []).join(', '))}</span>
        </td>
        <td>${esc(row.country)}<br><span class="muted">${esc(row.market_category)}</span></td>
        <td>${esc(row.product)}</td>
        <td>${esc(row.current_supplier)}${mappingAliasNote(row.supplier_aliases, "raw supplier names represented")}</td>
        <td>${num(row.total_quantity_kg)}</td>
        <td class="score">${money(row.avg_price_per_kg)}</td>
        <td>${money(row.market_avg_price_per_kg)}</td>
        <td class="${Number(row.price_difference || 0) > 0 ? 'score' : 'muted'}">${money(row.price_difference)}</td>
        <td>${num(row.shipment_count)}</td>
        <td>${esc(row.last_shipment_date)}</td>
        <td>${esc(row.shodhana_status)}<br><span class="muted">${esc(row.tier)}</span></td>
        <td class="score">${row.score}</td>
        <td>${esc(row.opportunity_category)}</td>
        <td class="reason-cell">${esc(row.recommended_action)}</td>
        <td class="action-cell">
          <div class="action-grid two-actions">
            <button class="small tip" data-tooltip="Open customer, shipment, supplier, and price detail." onclick="viewOpportunity('${esc(row.opportunity_id)}')">Details</button>
            <button class="small tip" data-tooltip="Generate a customer-specific pitch package for this opportunity." onclick="openPitch('${esc(row.opportunity_id)}')">Generate Pitch</button>
          </div>
        </td>
      </tr>`).join("")}
    </tbody>
  </table>`;
  setTooltipTitles();
}

function mappingAliasNote(aliases, label) {
  const values = Array.isArray(aliases) ? aliases.filter(Boolean) : [];
  if (values.length <= 1) return "";
  return `<br><span class="mapping-alias-note tip" data-tooltip="${esc(values.join(" · "))}">${num(values.length)} ${esc(label)}</span>`;
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
  `;
  setTooltipTitles();
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
          <tr><th>Status</th><td>${esc(opp.shodhana_status)}</td></tr>
          <tr><th>Raw Names Clubbed</th><td>${mappingAliasList(data.customer_summary?.importer_aliases)}</td></tr>
          <tr><th>Supplier Aliases</th><td>${mappingAliasList(data.customer_summary?.supplier_aliases)}</td></tr>
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
  setTooltipTitles();
}

function supplierHistoryTable(rows) {
  return rows.length ? `<div class="table-wrap"><table>
    <thead><tr><th>Supplier</th><th>Country</th><th>Qty KG</th><th>Value</th><th>Avg $/KG</th><th>Shipments</th><th>Last Shipment</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.supplier)}</strong>${mappingAliasNote(row.supplier_aliases, "raw supplier names clubbed")}</td><td>${esc(row.exporter_country)}</td><td>${num(row.total_quantity_kg)}</td><td>${money(row.total_value_usd)}</td><td class="score">${money(row.avg_price_per_kg)}</td><td>${num(row.shipment_count)}</td><td>${esc(row.last_shipment_date)}</td><td>${esc(row.shodhana_status)}</td>
    </tr>`).join("")}</tbody>
  </table></div>` : `<div class="empty">No supplier history.</div>`;
}

function mappingAliasList(aliases) {
  const values = Array.isArray(aliases) ? aliases.filter(Boolean) : [];
  if (!values.length) return `<span class="muted">No aliases</span>`;
  return `<div class="mapping-alias-list">${values.map((value) => `<span>${esc(value)}</span>`).join("")}</div>`;
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
  await openPitch(opportunityDetailData.opportunity.opportunity_id);
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
        <th>Suggested Standard Company Name</th>
        <th>Confidence</th>
        <th>Role</th>
        <th>Reason</th>
        <th>Status</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_company_name)}</strong></td>
      <td><input class="inline-edit" id="company-map-${row.id}" value="${esc(row.approved_standard_company_name || row.suggested_standard_company_name)}"></td>
      <td class="${confidenceClass(row.confidence_score)}">${percent(row.confidence_score)}</td>
      <td>${esc(row.source_roles || "")}</td>
      <td class="reason-cell">${esc(row.reason_for_suggestion || "")}</td>
      <td>${statusText(row.status)}</td>
      <td class="action-cell"><div class="mapping-actions">
        <button class="small" onclick="mappingAction('company', ${row.id}, 'approve')">Approve</button>
        <button class="small secondary" onclick="mappingAction('company', ${row.id}, 'edit')">Edit</button>
        <button class="small ghost" onclick="mappingAction('company', ${row.id}, 'reject')">Reject</button>
      </div></td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function renderCountryReview(rows) {
  const container = document.getElementById("countryReviewTable");
  document.getElementById("countryReviewCount").textContent = `${rows.length} rows`;
  if (!rows.length) {
    container.innerHTML = `<div class="empty">Upload trade data to create country mapping suggestions.</div>`;
    return;
  }
  container.innerHTML = `<table>
    <thead>
      <tr>
        <th>Raw Country Name</th>
        <th>Suggested Standard Country Name</th>
        <th>Confidence</th>
        <th>Role</th>
        <th>Reason</th>
        <th>Status</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_country_name)}</strong></td>
      <td><input class="inline-edit" id="country-map-${row.id}" value="${esc(row.approved_standard_country_name || row.suggested_standard_country_name)}"></td>
      <td class="${confidenceClass(row.confidence_score)}">${percent(row.confidence_score)}</td>
      <td>${esc(row.source_roles || "")}</td>
      <td class="reason-cell">${esc(row.reason_for_suggestion || "")}</td>
      <td>${statusText(row.status)}</td>
      <td class="action-cell"><div class="mapping-actions">
        <button class="small" onclick="mappingAction('country', ${row.id}, 'approve')">Approve</button>
        <button class="small secondary" onclick="mappingAction('country', ${row.id}, 'edit')">Edit</button>
        <button class="small ghost" onclick="mappingAction('country', ${row.id}, 'reject')">Reject</button>
      </div></td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function productSelect(id, value) {
  return `<input class="inline-edit" list="standardProductOptions" id="product-map-${id}" value="${esc(value)}">`;
}

async function mappingAction(kind, id, action) {
  const valueEl = document.getElementById(`${kind}-map-${id}`);
  const value = valueEl ? valueEl.value.trim() : "";
  try {
    const result = await postJSON("/api/mapping-action", {kind, id, action, value});
    const rerun = await postJSON("/api/rerun-cleaning", {});
    setStatus(`${result.kind} mapping ${result.status.toLowerCase()} and opportunities regenerated from ${rerun.clean_rows} cleaned rows.`);
    await refreshAll();
  } catch (error) {
    setStatus(error.message || String(error), true);
  }
}

async function rerunCleaning(button) {
  await withBusy(button, "Re-running", async () => {
    const result = await postJSON("/api/rerun-cleaning", {});
    setStatus(`Cleaning re-run complete: ${result.clean_rows} rows regenerated, ${result.duplicates_removed} duplicates removed.`);
    await refreshAll();
    showPage("dashboard");
  });
}

function renderProductMappings(rows) {
  const html = rows.length ? `<table>
    <thead><tr><th>Raw Product Description</th><th>Suggested Standard Product</th><th>Confidence</th><th>Reason</th><th>Approved</th><th>Master</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_product_description)}</strong></td>
      <td>${esc(row.suggested_standard_product)}</td>
      <td class="${confidenceClass(row.confidence_score)}">${percent(row.confidence_score)}</td>
      <td>${esc(row.reason_for_suggestion || "")}</td>
      <td>${esc(row.approved_standard_product)}</td>
      <td>${masterText(row.is_master)}</td>
      <td>${statusText(row.status)}</td>
    </tr>`).join("")}</tbody>
  </table>` : `<div class="empty">Import data to create product mapping rows.</div>`;
  document.getElementById("productMappings").innerHTML = html;
  document.getElementById("productMiniTable").innerHTML = html;
}

function renderCompanyMappings(rows) {
  const html = rows.length ? `<table>
    <thead><tr><th>Raw Company Name</th><th>Suggested Standard Company</th><th>Confidence</th><th>Role</th><th>Approved</th><th>Master</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_company_name)}</strong></td>
      <td>${esc(row.suggested_standard_company_name)}</td>
      <td class="${confidenceClass(row.confidence_score)}">${percent(row.confidence_score)}</td>
      <td>${esc(row.source_roles || "")}</td>
      <td>${esc(row.approved_standard_company_name)}</td>
      <td>${masterText(row.is_master)}</td>
      <td>${statusText(row.status)}</td>
    </tr>`).join("")}</tbody>
  </table>` : `<div class="empty">Import data to create company mapping rows.</div>`;
  document.getElementById("companyMappings").innerHTML = html;
  document.getElementById("companyMiniTable").innerHTML = html;
}

function renderCountryMappings(rows) {
  const html = rows.length ? `<table>
    <thead><tr><th>Raw Country Name</th><th>Suggested Standard Country</th><th>Confidence</th><th>Role</th><th>Approved</th><th>Master</th><th>Status</th></tr></thead>
    <tbody>${rows.map((row) => `<tr>
      <td><strong>${esc(row.raw_country_name)}</strong></td>
      <td>${esc(row.suggested_standard_country_name)}</td>
      <td class="${confidenceClass(row.confidence_score)}">${percent(row.confidence_score)}</td>
      <td>${esc(row.source_roles || "")}</td>
      <td>${esc(row.approved_standard_country_name)}</td>
      <td>${masterText(row.is_master)}</td>
      <td>${statusText(row.status)}</td>
    </tr>`).join("")}</tbody>
  </table>` : `<div class="empty">Import data to create country mapping rows.</div>`;
  document.getElementById("countryMappings").innerHTML = html;
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
  const cls = text === "Pending" || text === "Suggested" ? "warning-text" : text === "Rejected" ? "danger-text" : "approved-text";
  return `<span class="${cls}">${esc(text)}</span>`;
}

function masterText(value) {
  return Number(value || 0) ? `<span class="approved-text">Yes</span>` : `<span class="muted">No</span>`;
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
renderProductOptionDatalist();
window.addEventListener("popstate", async () => {
  const page = pathToPage(window.location.pathname);
  if (page === "opportunity-detail") await loadOpportunityDetailFromPath();
  if (page === "pitch") await loadPitchFromPath();
  showPage(page, false);
});
refreshAll()
  .then(async () => {
    const page = pathToPage(window.location.pathname);
    if (page === "opportunity-detail") await loadOpportunityDetailFromPath();
    if (page === "pitch") await loadPitchFromPath();
    showPage(page, false);
  })
  .catch((error) => setStatus(error.message || String(error), true));

function pageToPath(page) {
  return {
    review: "/cleaning-review",
    dashboard: "/dashboard",
    opportunities: "/opportunities",
    countries: "/countries",
    "opportunity-detail": window.location.pathname.startsWith("/opportunities/") ? window.location.pathname : "/opportunities",
    pitch: window.location.pathname.startsWith("/pitch/") ? window.location.pathname : "/pitch",
  }[page] || "/";
}

function pathToPage(path) {
  if (/^\/opportunities\/[^/]+/.test(path)) return "opportunity-detail";
  if (/^\/pitch(\/[^/]+)?/.test(path)) return "pitch";
  return {
    "/cleaning-review": "review",
    "/dashboard": "dashboard",
    "/opportunities": "opportunities",
    "/countries": "countries",
  }[path] || "upload";
}
