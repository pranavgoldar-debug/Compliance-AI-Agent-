"use strict";

/* ============================================================
 *  Mode switcher
 * ============================================================ */
const viewCalendar = document.getElementById("view-calendar");
const viewExtractor = document.getElementById("view-extractor");
const tabs = document.querySelectorAll(".tab");

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((t) => t.classList.toggle("active", t === tab));
    const view = tab.dataset.view;
    setVisibility(viewCalendar, view === "calendar");
    setVisibility(viewExtractor, view === "extractor");
  });
});

function setVisibility(el, visible) { el.hidden = !visible; }

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

/* ============================================================
 *  Compliance Calendar view
 * ============================================================ */
const calendarCountry = document.getElementById("calendar-country");
const categoryFilter = document.getElementById("category-filter");
const categoryFilterLabel = document.getElementById("category-filter-label");
const searchInput = document.getElementById("search-input");
const searchLabel = document.getElementById("search-label");
const calendarEmpty = document.getElementById("calendar-empty");
const calendarLoading = document.getElementById("calendar-loading");
const calendarError = document.getElementById("calendar-error");
const calendarResult = document.getElementById("calendar-result");
const calendarTitle = document.getElementById("calendar-title");
const calendarSummary = document.getElementById("calendar-summary");
const calendarCounts = document.getElementById("calendar-counts");
const filingsBody = document.getElementById("filings-body");

let currentFilings = null;
let currentCountry = null;

async function loadFintechCountries() {
  try {
    const r = await fetch("/api/fintech/countries");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    for (const c of data) {
      const opt = document.createElement("option");
      opt.value = c.code;
      opt.textContent = `${c.flag}  ${c.name}  (${c.filing_count})`;
      calendarCountry.appendChild(opt);
    }
  } catch (err) {
    calendarError.textContent = `Could not load countries: ${err.message}`;
    setVisibility(calendarError, true);
  }
}

calendarCountry.addEventListener("change", async () => {
  const code = calendarCountry.value;
  setVisibility(calendarError, false);
  if (!code) {
    setVisibility(calendarResult, false);
    setVisibility(calendarEmpty, true);
    setVisibility(categoryFilter, false);
    setVisibility(categoryFilterLabel, false);
    setVisibility(searchInput, false);
    setVisibility(searchLabel, false);
    return;
  }
  setVisibility(calendarEmpty, false);
  setVisibility(calendarResult, false);
  setVisibility(calendarLoading, true);
  try {
    const r = await fetch(`/api/fintech/${encodeURIComponent(code)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    currentCountry = await r.json();
    currentFilings = currentCountry.filings;
    populateCategoryFilter();
    setVisibility(categoryFilter, true);
    setVisibility(categoryFilterLabel, true);
    setVisibility(searchInput, true);
    setVisibility(searchLabel, true);
    renderCalendar();
    setVisibility(calendarLoading, false);
    setVisibility(calendarResult, true);
  } catch (err) {
    calendarError.textContent = `Could not load filings: ${err.message}`;
    setVisibility(calendarError, true);
    setVisibility(calendarLoading, false);
  }
});

categoryFilter.addEventListener("change", renderCalendar);
searchInput.addEventListener("input", renderCalendar);

function populateCategoryFilter() {
  const cats = Array.from(new Set(currentFilings.map((f) => f.category))).sort();
  categoryFilter.innerHTML = '<option value="">All categories</option>';
  for (const c of cats) {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    categoryFilter.appendChild(opt);
  }
}

function renderCalendar() {
  if (!currentCountry) return;

  const catVal = categoryFilter.value;
  const q = (searchInput.value || "").trim().toLowerCase();

  const filtered = currentFilings.filter((f) => {
    if (catVal && f.category !== catVal) return false;
    if (!q) return true;
    return [f.form_name, f.authority, f.area, f.frequency, f.due_date_rule, f.applicability_note]
      .some((v) => (v || "").toLowerCase().includes(q));
  });

  calendarTitle.textContent = `${currentCountry.flag}  ${currentCountry.country_name} — Compliance Calendar`;
  calendarSummary.textContent =
    `${filtered.length} of ${currentFilings.length} filings shown. ` +
    `Status / Filing reference / Comments are blank for you to fill in.`;

  // Severity-like counts by applicability
  const counts = { Mandatory: 0, Conditional: 0, "Sector-specific": 0, Other: 0 };
  for (const f of currentFilings) {
    const a = f.applicability || "Other";
    counts[a] !== undefined ? counts[a]++ : counts.Other++;
  }
  calendarCounts.innerHTML = "";
  const total = mkPill(currentFilings.length, "Total");
  calendarCounts.appendChild(total);
  for (const key of ["Mandatory", "Conditional", "Sector-specific"]) {
    if (counts[key]) calendarCounts.appendChild(mkPill(counts[key], key));
  }

  filingsBody.innerHTML = "";
  for (const f of filtered) filingsBody.appendChild(renderRow(f));
}

function mkPill(value, label) {
  const div = document.createElement("div");
  div.className = "count-pill";
  div.innerHTML = `<strong>${value}</strong>${label}`;
  return div;
}

function catClass(category) {
  const slug = (category || "")
    .toLowerCase()
    .replace(/[^\w]+/g, "-")
    .replace(/^-|-$/g, "");
  return `cat-${slug}`;
}
function appClass(app) {
  return `app-${(app || "").split(/[\s-]/)[0]}`;
}
function freqClass(freq) {
  return `freq-${(freq || "").split(/[\s/]/)[0]}`;
}

function renderRow(f) {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td class="col-sno">${f.s_no}</td>
    <td class="col-geo">${currentCountry.flag}</td>
    <td class="col-cat"><span class="cat-pill ${catClass(f.category)}">${escapeHtml(f.category)}</span></td>
    <td class="col-area">${escapeHtml(f.area)}</td>
    <td class="col-form"><strong>${escapeHtml(f.form_name)}</strong></td>
    <td class="col-auth">${escapeHtml(f.authority)}</td>
    <td class="col-freq"><span class="freq-text ${freqClass(f.frequency)}">${escapeHtml(f.frequency)}</span></td>
    <td class="col-rule">${escapeHtml(f.due_date_rule)}</td>
    <td class="col-pay">${f.payment_due ? escapeHtml(f.payment_due) : '<span class="blank">—</span>'}</td>
    <td class="col-app"><span class="app-pill ${appClass(f.applicability)}">${escapeHtml(f.applicability)}</span></td>
    <td class="col-reason">${f.applicability_note ? escapeHtml(f.applicability_note) : '<span class="blank">—</span>'}</td>
  `;
  return tr;
}

/* ============================================================
 *  Regulation Extractor view (previous behaviour, kept intact)
 * ============================================================ */
const extractorCountry = document.getElementById("extractor-country");
const regulationSelect = document.getElementById("regulation-select");
const regulationLabel = document.getElementById("regulation-label");
const extractorEmpty = document.getElementById("extractor-empty");
const extractorLoading = document.getElementById("extractor-loading");
const extractorError = document.getElementById("extractor-error");
const extractorResult = document.getElementById("extractor-result");
const regulationName = document.getElementById("regulation-name");
const regulationScope = document.getElementById("regulation-scope");
const counts = document.getElementById("counts");
const verificationBox = document.getElementById("verification");
const categoriesBox = document.getElementById("categories");
const modeBadge = document.getElementById("mode-badge");

let extractorCatalog = [];

const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3, informational: 4 };
const SEVERITY_LABEL = { critical: "Critical", high: "High", medium: "Medium", low: "Low", informational: "Info" };

async function loadExtractorCountries() {
  try {
    const r = await fetch("/api/countries");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    extractorCatalog = await r.json();
    for (const c of extractorCatalog) {
      const opt = document.createElement("option");
      opt.value = c.code;
      opt.textContent = `${c.flag}  ${c.name}`;
      extractorCountry.appendChild(opt);
    }
  } catch (err) {
    extractorError.textContent = `Could not load countries: ${err.message}`;
    setVisibility(extractorError, true);
  }
}

extractorCountry.addEventListener("change", () => {
  const code = extractorCountry.value;
  regulationSelect.innerHTML = '<option value="">— select a regulation —</option>';
  setVisibility(extractorResult, false);
  setVisibility(extractorError, false);
  if (!code) {
    setVisibility(regulationSelect, false);
    setVisibility(regulationLabel, false);
    setVisibility(extractorEmpty, true);
    return;
  }
  const country = extractorCatalog.find((c) => c.code === code);
  if (!country) return;
  for (const reg of country.regulations) {
    const opt = document.createElement("option");
    opt.value = reg.id;
    opt.textContent = reg.short_name;
    regulationSelect.appendChild(opt);
  }
  setVisibility(regulationSelect, true);
  setVisibility(regulationLabel, true);
  setVisibility(extractorEmpty, true);
});

regulationSelect.addEventListener("change", async () => {
  const regId = regulationSelect.value;
  if (!regId) {
    setVisibility(extractorResult, false);
    setVisibility(extractorEmpty, true);
    return;
  }
  setVisibility(extractorEmpty, false);
  setVisibility(extractorError, false);
  setVisibility(extractorResult, false);
  setVisibility(extractorLoading, true);
  try {
    const r = await fetch(`/api/regulations/${encodeURIComponent(regId)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    renderExtractor(data);
    setVisibility(extractorLoading, false);
    setVisibility(extractorResult, true);
  } catch (err) {
    extractorError.textContent = `Could not load regulation: ${err.message}`;
    setVisibility(extractorError, true);
    setVisibility(extractorLoading, false);
  }
});

function renderExtractor(data) {
  const { regulation, extraction, verification, flag } = data;
  regulationName.textContent = `${flag} ${regulation.name}`;
  regulationScope.textContent = regulation.scope;

  const sevCounts = { critical: 0, high: 0, medium: 0, low: 0, informational: 0 };
  for (const req of extraction.requirements) sevCounts[req.severity] = (sevCounts[req.severity] || 0) + 1;
  counts.innerHTML = "";
  for (const sev of ["critical", "high", "medium", "low", "informational"]) {
    if (!sevCounts[sev]) continue;
    counts.appendChild(mkPill(sevCounts[sev], SEVERITY_LABEL[sev]));
  }
  counts.appendChild(mkPill(extraction.requirements.length, "Total"));

  if (verification) {
    const summary = { pass: 0, warning: 0, fail: 0 };
    for (const f of verification.findings) summary[f.status] = (summary[f.status] || 0) + 1;
    verificationBox.innerHTML = `
      <strong>Verification:</strong> ${escapeHtml(verification.overall_summary)}
      <div class="pills">
        <span class="verify-badge verify-pass">✓ pass · ${summary.pass}</span>
        <span class="verify-badge verify-warning">! warning · ${summary.warning}</span>
        <span class="verify-badge verify-fail">✗ fail · ${summary.fail}</span>
      </div>
    `;
    setVisibility(verificationBox, true);
  } else {
    setVisibility(verificationBox, false);
  }

  const findingsById = {};
  if (verification) for (const f of verification.findings) findingsById[f.requirement_id] = f;

  const byCategory = {};
  for (const req of extraction.requirements) (byCategory[req.category] ??= []).push(req);

  categoriesBox.innerHTML = "";
  for (const category of Object.keys(byCategory).sort()) {
    const reqs = byCategory[category].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
    const section = document.createElement("section");
    section.className = "cat-section";
    const title = document.createElement("h3");
    title.className = "cat-title";
    title.textContent = category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    section.appendChild(title);
    for (const req of reqs) section.appendChild(renderCard(req, findingsById[req.requirement_id]));
    categoriesBox.appendChild(section);
  }
}

function renderCard(req, finding) {
  const card = document.createElement("article");
  card.className = "card";
  card.innerHTML = `
    <div class="card-head">
      <div>
        <h4 class="card-title">${escapeHtml(req.title)}</h4>
        <span class="card-id">${escapeHtml(req.requirement_id)}${req.section_reference ? " · " + escapeHtml(req.section_reference) : ""}</span>
      </div>
      <span class="severity-badge severity-${req.severity}">${SEVERITY_LABEL[req.severity]}</span>
    </div>
    <p class="card-summary">${escapeHtml(req.summary)}</p>
    <dl class="kv-row">
      <dt>Applies to</dt><dd>${tagList(req.applies_to)}</dd>
      <dt>Evidence</dt><dd>${tagList(req.evidence_artifacts)}</dd>
    </dl>
    ${req.source_quote ? `<blockquote class="source">${escapeHtml(req.source_quote)}</blockquote>` : ""}
  `;
  if (finding) {
    const badge = `<span class="verify-badge verify-${finding.status}">${finding.status}</span>`;
    const verbatim = finding.quote_verbatim ? "✓ verbatim quote" : "✗ quote not verbatim";
    const issues = (finding.issues || []).map((i) => `<li>${escapeHtml(i)}</li>`).join("");
    const fbox = document.createElement("div");
    fbox.style.marginTop = "10px";
    fbox.innerHTML = `${badge} <span style="color:var(--muted);font-size:12px;margin-left:8px;">${verbatim}</span>${issues ? `<ul style="margin:6px 0 0 18px;color:var(--muted);font-size:13px;">${issues}</ul>` : ""}`;
    card.appendChild(fbox);
  }
  return card;
}

function tagList(items) {
  if (!items || items.length === 0) return '<span style="color:var(--muted)">—</span>';
  return items.map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join(" ");
}

if (window.__COMPLIANCE_LIVE__) {
  modeBadge.textContent = "Live (Claude)";
  modeBadge.classList.add("live");
}

loadFintechCountries();
loadExtractorCountries();
