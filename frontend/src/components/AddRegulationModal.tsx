// Add-regulation modal — manual entry (with a structured due-date rule + live
// "Next due" preview) and bulk Import from Excel/CSV. Emitted records are mapped
// to backend rules by the caller (see EntityDetailPage) and land as DRAFTS on
// the entity's discovered list. Adapted from the product prototype; keeps its
// self-contained inline-styled UI.
import { useState, useMemo, useRef } from "react";
import * as XLSX from "xlsx";

/* eslint-disable @typescript-eslint/no-explicit-any */

/* ---------------- register schema ---------------- */
const COLUMNS = [
  { key: "oblId", label: "Obl. ID", aliases: ["oblid", "obligationid", "id"] },
  { key: "entity", label: "Entity", aliases: ["entity", "legalentity", "company"] },
  { key: "country", label: "Country", aliases: ["country", "jurisdiction"] },
  { key: "regulator", label: "Regulator", aliases: ["regulator", "authority", "agency"] },
  { key: "submissionPortal", label: "Submission portal", aliases: ["submissionportal", "portal"] },
  { key: "type", label: "Type", aliases: ["type", "category"] },
  { key: "subtype", label: "Subtype", aliases: ["subtype", "subcategory"] },
  { key: "filingName", label: "Filing / form", aliases: ["filingform", "filing", "form", "filingname", "formcode"], required: true },
  { key: "description", label: "Description", aliases: ["description", "whatissubmitted", "descriptionwhatissubmitted"] },
  { key: "frequency", label: "Frequency", aliases: ["frequency", "freq", "cadence"] },
  { key: "deadlineRuleText", label: "Deadline rule", aliases: ["deadlinerule", "duedaterule", "duerule", "deadline"] },
  { key: "anchorDate", label: "Anchor date", aliases: ["anchordate", "fyend", "anchor"] },
  { key: "effort", label: "Effort", aliases: ["effort"] },
  { key: "ownerTeam", label: "Owner team", aliases: ["ownerteam", "owner", "team", "function"] },
  { key: "triggeringActivity", label: "Triggering activity", aliases: ["triggeringactivity", "trigger"] },
  { key: "applicability", label: "Applicability / condition", aliases: ["applicabilitycondition", "applicability", "condition"] },
  { key: "sourceAuthority", label: "Source authority", aliases: ["sourceauthority", "sourceauthoritydocsection", "source"] },
  { key: "sourceUrl", label: "Source URL", aliases: ["sourceurl", "url", "link"] },
  { key: "dateAccessed", label: "Date accessed", aliases: ["dateaccessed", "accessed"] },
  { key: "confidence", label: "Confidence", aliases: ["confidence"] },
  { key: "verifiedBy", label: "Verified by", aliases: ["verifiedby"] },
  { key: "verifiedDate", label: "Verified date", aliases: ["verifieddate"] },
  { key: "comment", label: "Comment", aliases: ["comment", "comments", "notes"] },
];

const FREQUENCIES = [
  { id: "ANNUAL", label: "Annual" },
  { id: "SEMI_ANNUAL", label: "Semi-annual" },
  { id: "QUARTERLY", label: "Quarterly" },
  { id: "MONTHLY", label: "Monthly" },
  { id: "ONE_TIME", label: "One-time" },
];
const STEP_MONTHS: Record<string, number> = { ANNUAL: 12, SEMI_ANNUAL: 6, QUARTERLY: 3, MONTHLY: 1 };
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const MONTH_RX = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec";

/* ---------------- parsing helpers ---------------- */
const norm = (s: any) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

function parseFrequency(text: any): string | null {
  const t = norm(text);
  if (!t) return null;
  if (t.includes("semi") || t.includes("halfyear") || t.includes("biannual")) return "SEMI_ANNUAL";
  if (t.includes("quarter")) return "QUARTERLY";
  if (t.includes("month")) return "MONTHLY";
  if (t.includes("annual") || t.includes("year")) return "ANNUAL";
  if (t.includes("once") || t.includes("onetime") || t.includes("adhoc") || t.includes("event")) return "ONE_TIME";
  return null;
}

function parseDeadlineRule(text: any): any {
  const t = String(text || "").toLowerCase().trim();
  if (!t) return null;
  const unitOf = (u: string) => (u.startsWith("day") ? "DAYS" : u.startsWith("week") ? "WEEKS" : "MONTHS");

  let m = t.match(/fye?\s*\+\s*(\d+)\s*(day|week|month)/);
  if (m) return { type: "OFFSET_FROM_FY_END", offset_value: +m[1], offset_unit: unitOf(m[2]), day_anchor: "SAME_DAY" };

  m = t.match(/(\d+)\s*(day|week|month)s?\s*(?:after|from|following|of)\s*(?:the\s*)?(?:fye|fy\s*end|financial\s*year(?:\s*end)?|tax\s*year(?:\s*end)?|year\s*end)/);
  if (m) return { type: "OFFSET_FROM_FY_END", offset_value: +m[1], offset_unit: unitOf(m[2]), day_anchor: "SAME_DAY" };

  m = t.match(/(\d+)\s*(day|week|month)s?\s*(?:after|from|following)\s*(?:each\s*|the\s*)?(?:period|quarter|month|reporting\s*period)\s*end/);
  if (m) return { type: "OFFSET_FROM_PERIOD_END", offset_value: +m[1], offset_unit: unitOf(m[2]), day_anchor: "SAME_DAY" };

  m = t.match(/within\s*(\d+)\s*(day|week|month)s?\s*(?:of|after|from)/);
  if (m) return { type: "OFFSET_FROM_PERIOD_END", offset_value: +m[1], offset_unit: unitOf(m[2]), day_anchor: "SAME_DAY" };

  if (/last\s*day\s*of\s*(each|every|the)\s*(following\s*)?month/.test(t)) {
    const following = /following/.test(t);
    return { type: "OFFSET_FROM_PERIOD_END", offset_value: following ? 1 : 0, offset_unit: "MONTHS", day_anchor: "LAST_DAY_OF_MONTH" };
  }

  m = t.match(new RegExp(`(?:by\\s*)?(\\d{1,2})(?:st|nd|rd|th)?\\s*(${MONTH_RX})`));
  if (m) return { type: "FIXED_DATE", day: +m[1], month: MONTH_RX.split("|").indexOf(m[2]) + 1 };

  m = t.match(new RegExp(`(${MONTH_RX})\\w*\\s*(\\d{1,2})(?:st|nd|rd|th)?`));
  if (m) return { type: "FIXED_DATE", day: +m[2], month: MONTH_RX.split("|").indexOf(m[1]) + 1 };

  return null;
}

/* ---------------- date math ---------------- */
const lastDayOf = (y: number, m0: number) => new Date(y, m0 + 1, 0).getDate();

function addMonths(date: Date, n: number, anchor?: string) {
  const total = date.getMonth() + n;
  const y = date.getFullYear() + Math.floor(total / 12);
  const m0 = ((total % 12) + 12) % 12;
  const ld = lastDayOf(y, m0);
  const day = anchor === "LAST_DAY_OF_MONTH" ? ld : Math.min(date.getDate(), ld);
  return new Date(y, m0, day);
}
const addDays = (d: Date, n: number) => { const r = new Date(d); r.setDate(r.getDate() + n); return r; };
const fmt = (d: Date) => d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

function nextDue(dueRule: any, frequency: string, anchorDate: any): Date | null {
  if (!dueRule) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  if (dueRule.type === "SPECIFIC_DATE") return dueRule.date ? new Date(dueRule.date) : null;
  if (dueRule.type === "FIXED_DATE") {
    for (let y = today.getFullYear(); y < today.getFullYear() + 3; y++) {
      const d = new Date(y, dueRule.month - 1, Math.min(dueRule.day, lastDayOf(y, dueRule.month - 1)));
      if (d >= today) return d;
    }
    return null;
  }
  const step = STEP_MONTHS[frequency] || 12;
  const fy = anchorDate || { month: 3, day: 31 };
  const baseY = today.getFullYear() - 2;
  const fyIsMonthEnd = fy.day >= lastDayOf(baseY, fy.month - 1);
  const anchor = new Date(baseY, fy.month - 1, Math.min(fy.day, lastDayOf(baseY, fy.month - 1)));
  for (let k = 0; k < 72; k++) {
    const pe = addMonths(anchor, k * step, fyIsMonthEnd ? "LAST_DAY_OF_MONTH" : "SAME_DAY");
    const due = dueRule.offset_unit === "MONTHS"
      ? addMonths(pe, dueRule.offset_value, dueRule.day_anchor)
      : addDays(pe, dueRule.offset_value * (dueRule.offset_unit === "WEEKS" ? 7 : 1));
    if (due >= today) return due;
  }
  return null;
}

function describeRule(dueRule: any): string {
  if (!dueRule) return "Free text only — needs review";
  const plural = (n: number, w: string) => `${n} ${w.toLowerCase().replace(/s$/, "")}${n === 1 ? "" : "s"}`;
  if (dueRule.type === "FIXED_DATE") return `Every year on ${dueRule.day} ${MONTHS[dueRule.month - 1]}`;
  if (dueRule.type === "SPECIFIC_DATE") return dueRule.date ? `Once, on ${fmt(new Date(dueRule.date))}` : "Pick a date";
  const base = dueRule.type === "OFFSET_FROM_FY_END" ? "FY end" : "each period end";
  let s = `${plural(dueRule.offset_value, dueRule.offset_unit)} after ${base}`;
  if (dueRule.offset_unit === "MONTHS" && dueRule.day_anchor === "LAST_DAY_OF_MONTH") s += ", last day of that month";
  return s;
}

/* ---------------- styles (matches the violet UI) ---------------- */
const C = {
  text: "#1c1530", sub: "#6f6a80", border: "#e6e3ee", soft: "#f7f6fb",
  accent: "#7c3aed", accentSoft: "#f1eafd", accentBtn: "#c4a7f3",
  good: "#0e7a4f", warn: "#b45309", warnBg: "#fef3e2", goodBg: "#e7f5ee",
};
const S: any = {
  overlay: { position: "fixed", inset: 0, background: "rgba(28,21,48,0.45)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto", zIndex: 50 },
  modal: { fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif", background: "#fff", borderRadius: 18, width: "100%", maxWidth: 760, color: C.text, boxShadow: "0 24px 60px rgba(28,21,48,0.25)" },
  head: { padding: "22px 26px 0", display: "flex", justifyContent: "space-between", alignItems: "center" },
  h1: { fontSize: 21, fontWeight: 600, margin: 0 },
  body: { padding: "14px 26px 8px" },
  intro: { fontSize: 13.5, color: C.sub, borderTop: `1px solid ${C.border}`, paddingTop: 14, marginBottom: 16, lineHeight: 1.5 },
  tabs: { display: "flex", gap: 6, marginBottom: 18 },
  tab: (a: boolean) => ({ fontSize: 13.5, padding: "8px 14px", borderRadius: 9, border: `1px solid ${a ? C.accent : C.border}`, background: a ? C.accentSoft : "#fff", color: a ? C.accent : C.text, fontWeight: a ? 500 : 400, cursor: "pointer" }),
  label: { fontSize: 13, fontWeight: 500, display: "block", marginBottom: 6 },
  input: { fontSize: 14, padding: "9px 12px", border: `1px solid ${C.border}`, borderRadius: 9, width: "100%", boxSizing: "border-box", outline: "none", color: C.text, background: "#fff" },
  grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 },
  grid3: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14, marginBottom: 14 },
  field: { minWidth: 0 },
  section: { fontSize: 12, fontWeight: 600, letterSpacing: 0.6, textTransform: "uppercase", color: C.sub, margin: "18px 0 10px" },
  summary: { fontSize: 13.5, fontWeight: 500, color: C.accent, background: C.accentSoft, borderRadius: 9, padding: "9px 12px", marginBottom: 14, display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 6 },
  foot: { display: "flex", justifyContent: "flex-end", gap: 10, padding: "16px 26px 22px", borderTop: `1px solid ${C.border}`, marginTop: 8 },
  btn: { fontSize: 14.5, fontWeight: 500, padding: "10px 18px", borderRadius: 11, border: `1px solid ${C.border}`, background: "#fff", color: C.text, cursor: "pointer" },
  btnPrimary: (enabled: boolean) => ({ fontSize: 14.5, fontWeight: 500, padding: "10px 18px", borderRadius: 11, border: "none", background: enabled ? C.accent : C.accentBtn, color: "#fff", cursor: enabled ? "pointer" : "default" }),
  chipBtn: { fontSize: 12.5, padding: "6px 11px", borderRadius: 999, border: `1px solid ${C.border}`, background: C.soft, color: C.sub, cursor: "pointer" },
  badge: (ok: boolean) => ({ fontSize: 11.5, fontWeight: 500, padding: "3px 8px", borderRadius: 999, background: ok ? C.goodBg : C.warnBg, color: ok ? C.good : C.warn, whiteSpace: "nowrap" }),
  drop: { border: `1.5px dashed ${C.border}`, borderRadius: 12, padding: "34px 20px", textAlign: "center", color: C.sub, fontSize: 14, background: C.soft, cursor: "pointer" },
  th: { textAlign: "left", fontSize: 11.5, fontWeight: 600, color: C.sub, padding: "7px 8px", borderBottom: `1px solid ${C.border}`, textTransform: "uppercase", letterSpacing: 0.4, whiteSpace: "nowrap" },
  td: { fontSize: 12.5, padding: "7px 8px", borderBottom: `1px solid ${C.border}`, verticalAlign: "top", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
};

const Input = (p: any) => <input {...p} style={{ ...S.input, ...p.style }} />;
const Select = (p: any) => <select {...p} style={{ ...S.input, ...p.style }} />;

/* ---------------- due-rule mini builder ---------------- */
function DueRuleEditor({ frequency, dueRule, onChange, anchorDate, setAnchorDate }: any) {
  const basisOptions =
    frequency === "ONE_TIME"
      ? [{ id: "SPECIFIC_DATE", label: "Specific date" }]
      : frequency === "ANNUAL"
        ? [{ id: "FIXED_DATE", label: "Fixed date each year" }, { id: "OFFSET_FROM_FY_END", label: "After FY end" }]
        : [{ id: "OFFSET_FROM_PERIOD_END", label: "After each period end" }];

  const setBasis = (id: string) => {
    if (id === dueRule?.type) return;
    if (id === "FIXED_DATE") onChange({ type: id, month: 7, day: 31 });
    else if (id === "SPECIFIC_DATE") onChange({ type: id, date: "" });
    else onChange({ type: id, offset_value: id === "OFFSET_FROM_FY_END" ? 6 : 30, offset_unit: id === "OFFSET_FROM_FY_END" ? "MONTHS" : "DAYS", day_anchor: "SAME_DAY" });
  };

  const due = nextDue(dueRule, frequency, anchorDate);

  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {basisOptions.map((b) => (
          <button key={b.id} type="button" style={S.tab(dueRule?.type === b.id)} onClick={() => setBasis(b.id)}>
            {b.label}
          </button>
        ))}
      </div>

      {dueRule?.type === "FIXED_DATE" && (
        <div style={S.grid3}>
          <div style={S.field}>
            <span style={S.label}>Day</span>
            <Select value={dueRule.day} onChange={(e: any) => onChange({ ...dueRule, day: +e.target.value })}>
              {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => <option key={d}>{d}</option>)}
            </Select>
          </div>
          <div style={S.field}>
            <span style={S.label}>Month</span>
            <Select value={dueRule.month} onChange={(e: any) => onChange({ ...dueRule, month: +e.target.value })}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </Select>
          </div>
        </div>
      )}

      {(dueRule?.type === "OFFSET_FROM_FY_END" || dueRule?.type === "OFFSET_FROM_PERIOD_END") && (
        <>
          <div style={S.grid3}>
            <div style={S.field}>
              <span style={S.label}>Offset</span>
              <Input type="number" min={0} max={365} value={dueRule.offset_value}
                onChange={(e: any) => onChange({ ...dueRule, offset_value: Math.max(0, +e.target.value || 0) })} />
            </div>
            <div style={S.field}>
              <span style={S.label}>Unit</span>
              <Select value={dueRule.offset_unit} onChange={(e: any) => onChange({ ...dueRule, offset_unit: e.target.value })}>
                <option value="DAYS">days</option><option value="WEEKS">weeks</option><option value="MONTHS">months</option>
              </Select>
            </div>
            <div style={S.field}>
              <span style={S.label}>Anchor (FY end)</span>
              <div style={{ display: "flex", gap: 6 }}>
                <Select value={anchorDate.day} style={{ width: "44%" }}
                  onChange={(e: any) => setAnchorDate({ ...anchorDate, day: +e.target.value })}>
                  {Array.from({ length: lastDayOf(2025, anchorDate.month - 1) }, (_, i) => i + 1).map((d) => <option key={d}>{d}</option>)}
                </Select>
                <Select value={anchorDate.month} style={{ width: "56%" }}
                  onChange={(e: any) => setAnchorDate({ month: +e.target.value, day: Math.min(anchorDate.day, lastDayOf(2025, +e.target.value - 1)) })}>
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m.slice(0, 3)}</option>)}
                </Select>
              </div>
            </div>
          </div>
          {dueRule.offset_unit === "MONTHS" && (
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, marginBottom: 12 }}>
              <input type="checkbox" checked={dueRule.day_anchor === "LAST_DAY_OF_MONTH"}
                onChange={(e: any) => onChange({ ...dueRule, day_anchor: e.target.checked ? "LAST_DAY_OF_MONTH" : "SAME_DAY" })} />
              Snap to last day of the resulting month
            </label>
          )}
        </>
      )}

      {dueRule?.type === "SPECIFIC_DATE" && (
        <div style={{ marginBottom: 12, maxWidth: 220 }}>
          <span style={S.label}>Due date</span>
          <Input type="date" value={dueRule.date} onChange={(e: any) => onChange({ ...dueRule, date: e.target.value })} />
        </div>
      )}

      <div style={S.summary}>
        <span>{describeRule(dueRule)}</span>
        {due && <span style={{ color: C.good }}>Next due: {fmt(due)}</span>}
      </div>
    </div>
  );
}

/* ---------------- manual entry tab ---------------- */
const EMPTY: any = Object.fromEntries(COLUMNS.map((c) => [c.key, ""]));

function ManualTab({ onSubmit, onClose }: any) {
  const [rec, setRec] = useState<any>({ ...EMPTY });
  const [frequency, setFrequency] = useState("ANNUAL");
  const [dueRule, setDueRule] = useState<any>({ type: "OFFSET_FROM_FY_END", offset_value: 6, offset_unit: "MONTHS", day_anchor: "SAME_DAY" });
  const [anchorDate, setAnchorDate] = useState<any>({ month: 3, day: 31 });
  const [moreOpen, setMoreOpen] = useState(false);

  const set = (k: string) => (e: any) => setRec({ ...rec, [k]: e.target.value });
  const canSubmit = rec.filingName.trim().length > 0;

  const submit = () => {
    if (!canSubmit) return;
    onSubmit({
      ...rec, frequency, dueRule,
      deadlineRuleText: describeRule(dueRule),
      anchorDate: `${anchorDate.day} ${MONTHS[anchorDate.month - 1].slice(0, 3)}`,
      status: "draft",
    });
    onClose();
  };

  return (
    <>
      <div style={{ marginBottom: 14 }}>
        <span style={S.label}>Filing name *</span>
        <Input autoFocus value={rec.filingName} onChange={set("filingName")}
          style={{ border: `2px solid ${C.accent}` }} placeholder="e.g. T2 Corporation Income Tax Return" />
      </div>

      <div style={S.grid3}>
        <div style={S.field}><span style={S.label}>Entity</span><Input value={rec.entity} onChange={set("entity")} placeholder="e.g. Aspora UK Ltd" /></div>
        <div style={S.field}><span style={S.label}>Country</span><Input value={rec.country} onChange={set("country")} placeholder="e.g. Canada" /></div>
        <div style={S.field}><span style={S.label}>Regulator</span><Input value={rec.regulator} onChange={set("regulator")} placeholder="e.g. CRA" /></div>
      </div>

      <div style={S.grid3}>
        <div style={S.field}><span style={S.label}>Type</span><Input value={rec.type} onChange={set("type")} placeholder="e.g. Tax" /></div>
        <div style={S.field}><span style={S.label}>Subtype</span><Input value={rec.subtype} onChange={set("subtype")} placeholder="e.g. CIT" /></div>
        <div style={S.field}><span style={S.label}>Owner team</span>
          <Select value={rec.ownerTeam} onChange={set("ownerTeam")}>
            <option value="">Select…</option>
            {["Finance", "Compliance", "Legal", "Ops", "HR / Payroll"].map((t) => <option key={t}>{t}</option>)}
          </Select>
        </div>
      </div>

      <div style={S.section}>Schedule</div>
      <div style={{ marginBottom: 12, maxWidth: 260 }}>
        <span style={S.label}>Frequency</span>
        <Select value={frequency} onChange={(e: any) => {
          const f = e.target.value; setFrequency(f);
          if (f === "ONE_TIME") setDueRule({ type: "SPECIFIC_DATE", date: "" });
          else if (f === "ANNUAL") setDueRule({ type: "OFFSET_FROM_FY_END", offset_value: 6, offset_unit: "MONTHS", day_anchor: "SAME_DAY" });
          else setDueRule({ type: "OFFSET_FROM_PERIOD_END", offset_value: 30, offset_unit: "DAYS", day_anchor: "SAME_DAY" });
        }}>
          {FREQUENCIES.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
        </Select>
      </div>
      <DueRuleEditor frequency={frequency} dueRule={dueRule} onChange={setDueRule}
        anchorDate={anchorDate} setAnchorDate={setAnchorDate} />

      <button type="button" style={{ ...S.chipBtn, marginBottom: 12 }} onClick={() => setMoreOpen(!moreOpen)}>
        {moreOpen ? "Hide" : "Show"} context & source fields
      </button>

      {moreOpen && (
        <>
          <div style={{ marginBottom: 14 }}>
            <span style={S.label}>Description (what is submitted)</span>
            <Input value={rec.description} onChange={set("description")} placeholder="e.g. Annual corporate income tax return with schedules" />
          </div>
          <div style={S.grid2}>
            <div style={S.field}><span style={S.label}>Triggering activity</span><Input value={rec.triggeringActivity} onChange={set("triggeringActivity")} /></div>
            <div style={S.field}><span style={S.label}>Applicability / condition</span><Input value={rec.applicability} onChange={set("applicability")} placeholder="e.g. Tax payable over $3,000" /></div>
          </div>
          <div style={S.grid2}>
            <div style={S.field}><span style={S.label}>Submission portal</span><Input value={rec.submissionPortal} onChange={set("submissionPortal")} /></div>
            <div style={S.field}><span style={S.label}>Effort</span>
              <Select value={rec.effort} onChange={set("effort")}>
                <option value="">Select…</option><option>Low</option><option>Medium</option><option>High</option>
              </Select>
            </div>
          </div>
          <div style={S.grid2}>
            <div style={S.field}><span style={S.label}>Source authority (doc + section)</span><Input value={rec.sourceAuthority} onChange={set("sourceAuthority")} /></div>
            <div style={S.field}><span style={S.label}>Source URL</span><Input value={rec.sourceUrl} onChange={set("sourceUrl")} placeholder="https://…" /></div>
          </div>
        </>
      )}

      <div style={S.foot}>
        <button type="button" style={S.btn} onClick={onClose}>Cancel</button>
        <button type="button" style={S.btnPrimary(canSubmit)} disabled={!canSubmit} onClick={submit}>
          Add regulation
        </button>
      </div>
    </>
  );
}

/* ---------------- import tab ---------------- */
function autoMap(headers: any[]) {
  const map: any = {};
  headers.forEach((h, i) => {
    const n = norm(h);
    const col = COLUMNS.find((c) => c.aliases.includes(n)) ||
      COLUMNS.find((c) => n && (n.includes(c.aliases[0]) || c.aliases[0].includes(n)));
    if (col && !Object.values(map).includes(col.key)) map[i] = col.key;
  });
  return map;
}

function buildRecords(rows: any[], map: any) {
  return rows
    .filter((r) => r.some((c: any) => String(c || "").trim() !== ""))
    .map((r) => {
      const rec: any = { ...EMPTY };
      Object.entries(map).forEach(([i, key]) => { if (key) rec[key as string] = String(r[+i] ?? "").trim(); });
      const freq = parseFrequency(rec.frequency);
      const rule = parseDeadlineRule(rec.deadlineRuleText);
      const issues: string[] = [];
      if (!rec.filingName) issues.push("Missing filing name");
      if (!freq) issues.push("Frequency not recognised");
      if (rec.deadlineRuleText && !rule) issues.push("Deadline rule needs structuring");
      return { ...rec, frequency: freq || rec.frequency, dueRule: rule, status: "draft", _issues: issues };
    });
}

function ImportTab({ onImport, onClose }: any) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [map, setMap] = useState<any>({});
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file?: File) => {
    if (!file) return;
    try {
      const wb = XLSX.read(await file.arrayBuffer());
      const ws = wb.Sheets[wb.SheetNames[0]];
      const data: any[] = XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" });
      if (!data.length) { setError("The file appears to be empty."); return; }
      setFileName(file.name);
      setHeaders(data[0].map(String));
      setRows(data.slice(1));
      setMap(autoMap(data[0]));
      setError(null);
    } catch {
      setError("Could not read that file. Use .xlsx, .xls or .csv.");
    }
  };

  const records = useMemo(() => buildRecords(rows, map), [rows, map]);
  const ready = records.filter((r) => r._issues.length === 0).length;
  const review = records.length - ready;
  const mappedCount = Object.values(map).filter(Boolean).length;

  const downloadTemplate = () => {
    const ws = XLSX.utils.aoa_to_sheet([COLUMNS.map((c) => c.label)]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Obligations");
    XLSX.writeFile(wb, "obligations_register_template.xlsx");
  };

  return (
    <>
      {!fileName && (
        <>
          <div style={S.drop} onClick={() => fileRef.current?.click()}>
            <div style={{ fontWeight: 500, color: C.text, marginBottom: 4 }}>Upload your obligations register</div>
            .xlsx, .xls or .csv — first row should be column headers
            <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: "none" }}
              onChange={(e) => handleFile(e.target.files?.[0])} />
          </div>
          <div style={{ marginTop: 12 }}>
            <button type="button" style={S.chipBtn} onClick={downloadTemplate}>Download blank template (.xlsx)</button>
          </div>
          {error && <div style={{ ...S.badge(false), display: "inline-block", marginTop: 12 }}>{error}</div>}
        </>
      )}

      {fileName && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
            <div style={{ fontSize: 13.5 }}>
              <span style={{ fontWeight: 500 }}>{fileName}</span>
              <span style={{ color: C.sub }}> — {records.length} rows, {mappedCount} of {COLUMNS.length} columns mapped</span>
            </div>
            <button type="button" style={S.chipBtn} onClick={() => { setFileName(null); setRows([]); setHeaders([]); }}>
              Choose another file
            </button>
          </div>

          <div style={S.section}>Column mapping</div>
          <div style={{ maxHeight: 170, overflowY: "auto", border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 16 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr><th style={S.th}>Your column</th><th style={S.th}>Maps to</th></tr></thead>
              <tbody>
                {headers.map((h, i) => (
                  <tr key={i}>
                    <td style={S.td}>{h || <em style={{ color: C.sub }}>blank</em>}</td>
                    <td style={S.td}>
                      <Select value={map[i] || ""} style={{ padding: "5px 8px", fontSize: 12.5 }}
                        onChange={(e: any) => setMap({ ...map, [i]: e.target.value })}>
                        <option value="">— ignore —</option>
                        {COLUMNS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                      </Select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={S.section}>Preview</div>
          <div style={{ overflowX: "auto", border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 8 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={S.th}>Status</th><th style={S.th}>Filing / form</th><th style={S.th}>Entity</th>
                  <th style={S.th}>Frequency</th><th style={S.th}>Due-date rule</th>
                </tr>
              </thead>
              <tbody>
                {records.slice(0, 6).map((r, i) => (
                  <tr key={i}>
                    <td style={S.td}>
                      <span style={S.badge(r._issues.length === 0)}>
                        {r._issues.length === 0 ? "Ready" : r._issues[0]}
                      </span>
                    </td>
                    <td style={{ ...S.td, fontWeight: 500 }}>{r.filingName || "—"}</td>
                    <td style={S.td}>{r.entity || "—"}</td>
                    <td style={S.td}>{r.frequency || "—"}</td>
                    <td style={S.td} title={r.deadlineRuleText}>
                      {r.dueRule ? describeRule(r.dueRule) : (r.deadlineRuleText || "—")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {records.length > 6 && (
            <div style={{ fontSize: 12.5, color: C.sub }}>…and {records.length - 6} more rows</div>
          )}

          <div style={S.foot}>
            <button type="button" style={S.btn} onClick={onClose}>Cancel</button>
            <button type="button" style={S.btnPrimary(records.length > 0)} disabled={!records.length}
              onClick={() => { onImport(records.map(({ _issues, ...r }: any) => ({ ...r, needsReview: _issues.length > 0 }))); onClose(); }}>
              Add {records.length} as drafts{review > 0 ? ` (${review} need review)` : ""}
            </button>
          </div>
        </>
      )}
    </>
  );
}

/* ---------------- modal shell ---------------- */
export interface AddRegulationModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (record: any) => void;
  onImport: (records: any[]) => void;
}

export function AddRegulationModal({ open, onClose, onSubmit, onImport }: AddRegulationModalProps) {
  const [tab, setTab] = useState("manual");
  if (!open) return null;
  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.modal} onClick={(e) => e.stopPropagation()}>
        <div style={S.head}>
          <h1 style={S.h1}>Add regulation</h1>
          <button type="button" onClick={onClose}
            style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: C.sub }}>✕</button>
        </div>
        <div style={S.body}>
          <div style={S.intro}>
            Add a filing the AI missed. It joins this entity's discovered list as a draft — send it to Review &amp;
            Assign with the rest.
          </div>
          <div style={S.tabs}>
            <button type="button" style={S.tab(tab === "manual")} onClick={() => setTab("manual")}>Manual entry</button>
            <button type="button" style={S.tab(tab === "import")} onClick={() => setTab("import")}>Import from Excel</button>
          </div>
          {tab === "manual"
            ? <ManualTab onSubmit={onSubmit} onClose={onClose} />
            : <ImportTab onImport={onImport} onClose={onClose} />}
        </div>
      </div>
    </div>
  );
}
