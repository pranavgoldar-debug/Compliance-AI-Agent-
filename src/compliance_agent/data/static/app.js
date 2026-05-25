"use strict";

const countrySelect = document.getElementById("country-select");
const regulationSelect = document.getElementById("regulation-select");
const regulationLabel = document.getElementById("regulation-label");
const emptyState = document.getElementById("empty-state");
const loading = document.getElementById("loading");
const errorBox = document.getElementById("error");
const result = document.getElementById("result");
const regulationName = document.getElementById("regulation-name");
const regulationScope = document.getElementById("regulation-scope");
const counts = document.getElementById("counts");
const verificationBox = document.getElementById("verification");
const categoriesBox = document.getElementById("categories");
const modeBadge = document.getElementById("mode-badge");

let catalog = [];

const SEVERITY_RANK = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  informational: 4,
};

const SEVERITY_LABEL = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  informational: "Info",
};

function setVisibility(elem, visible) {
  elem.hidden = !visible;
}

function showError(message) {
  errorBox.textContent = message;
  setVisibility(errorBox, true);
  setVisibility(loading, false);
  setVisibility(result, false);
}

async function loadCountries() {
  try {
    const response = await fetch("/api/countries");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    catalog = await response.json();
    for (const country of catalog) {
      const opt = document.createElement("option");
      opt.value = country.code;
      opt.textContent = `${country.flag}  ${country.name}`;
      countrySelect.appendChild(opt);
    }
  } catch (err) {
    showError(`Could not load countries: ${err.message}`);
  }
}

countrySelect.addEventListener("change", () => {
  const code = countrySelect.value;
  regulationSelect.innerHTML = '<option value="">— select a regulation —</option>';
  setVisibility(result, false);
  setVisibility(errorBox, false);
  if (!code) {
    setVisibility(regulationSelect, false);
    setVisibility(regulationLabel, false);
    setVisibility(emptyState, true);
    return;
  }
  const country = catalog.find((c) => c.code === code);
  if (!country) return;
  for (const reg of country.regulations) {
    const opt = document.createElement("option");
    opt.value = reg.id;
    opt.textContent = reg.short_name;
    regulationSelect.appendChild(opt);
  }
  setVisibility(regulationSelect, true);
  setVisibility(regulationLabel, true);
  setVisibility(emptyState, true);
});

regulationSelect.addEventListener("change", async () => {
  const regId = regulationSelect.value;
  if (!regId) {
    setVisibility(result, false);
    setVisibility(emptyState, true);
    return;
  }
  setVisibility(emptyState, false);
  setVisibility(errorBox, false);
  setVisibility(result, false);
  setVisibility(loading, true);

  try {
    const response = await fetch(`/api/regulations/${encodeURIComponent(regId)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderResult(data);
    setVisibility(loading, false);
    setVisibility(result, true);
  } catch (err) {
    showError(`Could not load regulation: ${err.message}`);
  }
});

function renderResult(data) {
  const { regulation, extraction, verification, flag, country } = data;
  regulationName.textContent = `${flag} ${regulation.name}`;
  regulationScope.textContent = regulation.scope;

  // Counts
  const sevCounts = { critical: 0, high: 0, medium: 0, low: 0, informational: 0 };
  for (const req of extraction.requirements) {
    sevCounts[req.severity] = (sevCounts[req.severity] || 0) + 1;
  }
  counts.innerHTML = "";
  for (const sev of ["critical", "high", "medium", "low", "informational"]) {
    if (!sevCounts[sev]) continue;
    const pill = document.createElement("div");
    pill.className = "count-pill";
    pill.innerHTML = `<strong>${sevCounts[sev]}</strong>${SEVERITY_LABEL[sev]}`;
    counts.appendChild(pill);
  }
  const total = document.createElement("div");
  total.className = "count-pill";
  total.innerHTML = `<strong>${extraction.requirements.length}</strong>Total`;
  counts.appendChild(total);

  // Verification block
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

  // Group by category
  const findingsById = {};
  if (verification) for (const f of verification.findings) findingsById[f.requirement_id] = f;

  const byCategory = {};
  for (const req of extraction.requirements) {
    (byCategory[req.category] ??= []).push(req);
  }

  categoriesBox.innerHTML = "";
  for (const category of Object.keys(byCategory).sort()) {
    const reqs = byCategory[category].sort(
      (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity],
    );
    const section = document.createElement("section");
    section.className = "cat-section";
    const title = document.createElement("h3");
    title.className = "cat-title";
    title.textContent = humanize(category);
    section.appendChild(title);
    for (const req of reqs) section.appendChild(renderCard(req, findingsById[req.requirement_id]));
    categoriesBox.appendChild(section);
  }
}

function renderCard(req, finding) {
  const card = document.createElement("article");
  card.className = "card";

  const head = document.createElement("div");
  head.className = "card-head";
  head.innerHTML = `
    <div>
      <h4 class="card-title">${escapeHtml(req.title)}</h4>
      <span class="card-id">${escapeHtml(req.requirement_id)}${req.section_reference ? " · " + escapeHtml(req.section_reference) : ""}</span>
    </div>
    <span class="severity-badge severity-${req.severity}">${SEVERITY_LABEL[req.severity]}</span>
  `;
  card.appendChild(head);

  const summary = document.createElement("p");
  summary.className = "card-summary";
  summary.textContent = req.summary;
  card.appendChild(summary);

  const kv = document.createElement("dl");
  kv.className = "kv-row";
  kv.innerHTML = `
    <dt>Applies to</dt><dd>${renderTags(req.applies_to)}</dd>
    <dt>Evidence</dt><dd>${renderTags(req.evidence_artifacts)}</dd>
  `;
  card.appendChild(kv);

  if (req.source_quote) {
    const bq = document.createElement("blockquote");
    bq.className = "source";
    bq.textContent = req.source_quote;
    card.appendChild(bq);
  }

  if (finding) {
    const fbox = document.createElement("div");
    fbox.style.marginTop = "10px";
    const badge = `<span class="verify-badge verify-${finding.status}">${finding.status}</span>`;
    const verbatim = finding.quote_verbatim ? "✓ verbatim quote" : "✗ quote not verbatim";
    const issues = (finding.issues || []).map((i) => `<li>${escapeHtml(i)}</li>`).join("");
    fbox.innerHTML = `${badge} <span style="color:var(--muted);font-size:12px;margin-left:8px;">${verbatim}</span>${issues ? `<ul style="margin:6px 0 0 18px;color:var(--muted);font-size:13px;">${issues}</ul>` : ""}`;
    card.appendChild(fbox);
  }

  return card;
}

function renderTags(items) {
  if (!items || items.length === 0) return '<span style="color:var(--muted)">—</span>';
  return items.map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("");
}

function humanize(category) {
  return category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

if (window.__COMPLIANCE_LIVE__) {
  modeBadge.textContent = "Live (Claude)";
  modeBadge.classList.add("live");
}

loadCountries();
