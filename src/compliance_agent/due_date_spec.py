"""Structured due-date specifications and their computed deadlines.

A filing's schedule is captured as a small JSON ``spec`` (set by the Due-Date
Builder in the UI) and the calendar computes real dates from it — so what a
reviewer sees in the builder's preview is exactly what lands on the calendar.

Spec shape (all keys optional unless noted)::

    {
      "frequency": "annual"|"semiannual"|"quarterly"|"monthly"|"onetime"
                   |"event"|"continuous",      # event/continuous: no dates
      "basis":     "fixed"|"after_period",     # ignored for onetime/event/continuous
      "day":   1..31,                           # fixed basis
      "month": 1..12,                           # fixed basis (anchor month)
      "offset": int, "unit": "months"|"days",   # after_period basis
      "snap_last": bool,                        # after_period: snap to month-end
      "date": "YYYY-MM-DD",                     # onetime
    }

"after_period" deadlines anchor on the entity's fiscal year-end (periods step
back from it), falling back to a 31-Dec year-end. This module is intentionally
dependency-free so it imports and unit-tests without the web stack.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional


FREQUENCIES = (
    "annual", "semiannual", "quarterly", "monthly", "onetime",
    # Unscheduled cadences — no computable due dates: event-based filings
    # happen when the trigger occurs; continuous obligations are maintained
    # at all times. next_due_dates() returns [] for both.
    "event", "continuous",
)
# Months between occurrences / period-ends for each recurring frequency.
_INTERVAL_MONTHS = {"annual": 12, "semiannual": 6, "quarterly": 3, "monthly": 1}
_FREQ_LABEL = {
    "annual": "Annual",
    "semiannual": "Semi-annual",
    "quarterly": "Quarterly",
    "monthly": "Monthly",
    "onetime": "One-time",
    "event": "Event-based",
    "continuous": "Continuous",
}
_MONTH_NAME = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _clamp_day(year: int, month: int, day: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(int(day or 1), 1), last))


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    return _clamp_day(y, m + 1, d.day)


def _first_of(year: int, month: int) -> date:
    return date(year, month, 1)


def freq_label(spec: Optional[dict]) -> str:
    """Human frequency label for the rule's ``frequency`` column."""
    f = str((spec or {}).get("frequency", "")).strip().lower()
    return _FREQ_LABEL.get(f, "")


def _parse_iso(text) -> Optional[date]:
    try:
        return date.fromisoformat(str(text)[:10])
    except (ValueError, TypeError):
        return None


def next_due_dates(
    spec: Optional[dict],
    base: date,
    fy_end: Optional[tuple[int, int]] = None,
    count: int = 3,
    ard_end: Optional[tuple[int, int]] = None,
) -> list[date]:
    """The next ``count`` due dates on/after ``base`` implied by ``spec``.

    Returns [] when the spec can't produce a date (incomplete / one-time in the
    past is still returned as a single date so the preview can show it)."""
    if not spec:
        return []
    freq = str(spec.get("frequency", "")).strip().lower()
    if freq not in FREQUENCIES:
        return []

    if freq == "onetime":
        d = _parse_iso(spec.get("date"))
        return [d] if d else []
    if freq in ("event", "continuous"):
        return []

    interval = _INTERVAL_MONTHS[freq]
    basis = str(spec.get("basis", "")).strip().lower()
    out: list[date] = []
    # Scan a generous window of occurrences (a few years either side of base)
    # and keep the first `count` that fall on/after base.
    steps = (48 // interval) + count + 4

    if basis == "fixed":
        day = int(spec.get("day") or 1)
        # Monthly recurs on the same day every month, so the anchor month is
        # irrelevant; other cadences anchor on the chosen month.
        anchor_month = 1 if freq == "monthly" else int(spec.get("month") or 1)
        origin = _first_of(base.year - 2, anchor_month)
        for i in range(steps):
            t = _add_months(origin, i * interval)
            occ = _clamp_day(t.year, t.month, day)
            if occ >= base:
                out.append(occ)
                if len(out) >= count:
                    break
        return out

    if basis == "after_period":
        offset = int(spec.get("offset") or 0)
        unit = str(spec.get("unit", "months")).strip().lower()
        snap = bool(spec.get("snap_last"))
        # Anchor on the entity's Annual Return Date when the spec asks for it
        # (anchor == "ard"); otherwise the fiscal year-end. ard_end is None when
        # the entity's ARD equals its FYE, so it correctly falls back to fy_end.
        anchor = str(spec.get("anchor", "")).strip().lower()
        anchor_end = ard_end if (anchor == "ard" and ard_end) else fy_end
        fy_month, _fy_day = anchor_end or (12, 31)
        # Period ends are month-ends stepping back from the anchor (FYE / ARD).
        origin_pe = _last_day(base.year - 2, fy_month)
        for i in range(steps):
            t = _add_months(_first_of(origin_pe.year, origin_pe.month), i * interval)
            pe = _last_day(t.year, t.month)
            if unit == "days":
                due = pe + timedelta(days=offset)
            else:
                due = _add_months(pe, offset)
                if snap:
                    due = _last_day(due.year, due.month)
            if due >= base:
                out.append(due)
                if len(out) >= count:
                    break
        return out

    return []


def period_end_for(spec: Optional[dict], due: date, fy_end: Optional[tuple[int, int]] = None) -> Optional[date]:
    """For an after_period spec, the period-end a given due date belongs to —
    used to label the preview ('Period ending 31 Mar 2026')."""
    if not spec or str(spec.get("basis", "")).lower() != "after_period":
        return None
    offset = int(spec.get("offset") or 0)
    unit = str(spec.get("unit", "months")).strip().lower()
    if unit == "days":
        return due - timedelta(days=offset)
    # months: the period end is `offset` months before the (pre-snap) due month.
    t = _add_months(_first_of(due.year, due.month), -offset)
    return _last_day(t.year, t.month)


def summarize(spec: Optional[dict]) -> str:
    """One-line human description for the rule's ``due_date_rule`` text column."""
    if not spec:
        return ""
    freq = str(spec.get("frequency", "")).strip().lower()
    if freq == "onetime":
        d = _parse_iso(spec.get("date"))
        return f"Due once on {d.isoformat()}" if d else "One-time (date not set)"
    if freq == "event":
        return "Event-based — due when the triggering event occurs"
    if freq == "continuous":
        return "Continuous — maintained at all times; no fixed due date"
    basis = str(spec.get("basis", "")).strip().lower()
    cadence = {
        "annual": "every year",
        "semiannual": "every 6 months",
        "quarterly": "every quarter",
        "monthly": "every month",
    }.get(freq, "")
    if basis == "fixed":
        day = int(spec.get("day") or 1)
        if freq == "monthly":
            return f"Due on the {_ordinal(day)} of every month"
        month = _MONTH_NAME[(int(spec.get("month") or 1) - 1) % 12]
        if freq == "annual":
            return f"Due every year on {day} {month}"
        return f"Due {cadence}, anchored on {day} {month}"
    if basis == "after_period":
        offset = int(spec.get("offset") or 0)
        unit = str(spec.get("unit", "months")).strip().lower()
        anchor = "financial year end" if freq == "annual" else "each period end"
        tail = ", on the last day of that month" if (unit == "months" and spec.get("snap_last")) else ""
        return f"Due {offset} {unit} after {anchor}{tail}"
    return ""


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= (n % 100) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


__all__ = ["next_due_dates", "period_end_for", "summarize", "freq_label", "FREQUENCIES"]
