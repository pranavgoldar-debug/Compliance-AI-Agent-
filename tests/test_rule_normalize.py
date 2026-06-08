"""Deterministic-dedupe contract for rule_normalize.

These tests pin the behaviour that fixes the duplicate storm: coded duplicates
collapse, genuinely different forms never merge (the false-merge is the cardinal
sin), and non-filings get routed off the filings register. The LLM adjudication
pass is disabled here (`adjudicate=False`) so the tests are deterministic and
offline.
"""
from compliance_agent.rule_normalize import (
    CONTROLS_REGISTER,
    FILINGS_REGISTER,
    classify_obligation_type,
    normalize_and_dedupe,
)


def _c(name, form_name=None, frequency="Annual", area=""):
    return {
        "name": name,
        "form_name": form_name if form_name is not None else name,
        "frequency": frequency,
        "area": area,
    }


def test_coded_phrasings_collapse():
    cands = [
        _c("Foreign Affiliate Information Return", "T1134"),
        _c("T1134 return", "T1134 — Foreign Affiliate Information Return"),
        _c("Statement of Remuneration Paid", "T4"),
        _c("T4 slips", "T4"),
        _c("T4 Information Return", "T4"),
    ]
    out, rep = normalize_and_dedupe(cands, jurisdiction="canada", adjudicate=False)
    keys = {c["canonical_key"] for c in out}
    assert keys == {"CANADA::T1134", "CANADA::T4"}
    assert rep.output_count == 2
    # provenance preserved, nothing silently lost
    t4 = next(c for c in out if c["canonical_key"] == "CANADA::T4")
    assert set(t4["merged_from"]) == {"T4 slips", "T4 Information Return"}


def test_t4_and_t4a_never_merge():
    out, rep = normalize_and_dedupe(
        [_c("T4 slip", "T4"), _c("T4A", "T4A")],
        jurisdiction="canada",
        adjudicate=False,
    )
    assert rep.output_count == 2
    assert {c["canonical_key"] for c in out} == {"CANADA::T4", "CANADA::T4A"}


def test_balance_payment_distinct_from_instalment():
    cands = [
        _c("Corporate Tax Balance Payment"),
        _c("Corporate Income Tax Balance Payment"),
        _c("Corporate Income Tax Instalments", "monthly instalment", frequency="Monthly"),
    ]
    out, rep = normalize_and_dedupe(cands, jurisdiction="canada", adjudicate=False)
    keys = {c["canonical_key"] for c in out}
    # the two balance phrasings merge; the instalment stays its own obligation
    assert keys == {"CANADA::CIT-BALANCE", "CANADA::CIT-INSTALMENT"}
    assert rep.output_count == 2
    for c in out:
        assert c["obligation_type"] == "payment"


def test_leading_form_code_fallback_for_uncatalogued_code():
    # T2125 isn't in the catalog but is a real leading form code -> coded.
    out, _ = normalize_and_dedupe(
        [_c("T2125 business income", "T2125")], jurisdiction="canada", adjudicate=False
    )
    assert out[0]["canonical_key"] == "CANADA::T2125"
    # ...and must not collapse into the catalog's T2 entry.
    out2, rep = normalize_and_dedupe(
        [_c("T2 corporation return", "T2"), _c("T2125 business income", "T2125")],
        jurisdiction="canada",
        adjudicate=False,
    )
    assert rep.output_count == 2


def test_continuous_controls_routed_off_filings_register():
    cands = [
        _c("AML Training Program", frequency="Continuous", area="AML"),
        _c("Ongoing Monitoring of Transactions", frequency="Continuous", area="AML"),
        _c("GST/HST Return", frequency="Quarterly", area="VAT"),
    ]
    out, _ = normalize_and_dedupe(cands, jurisdiction="canada", adjudicate=False)
    by_name = {c["name"]: c for c in out}
    assert by_name["AML Training Program"]["obligation_type"] == "ongoing_control"
    assert by_name["AML Training Program"]["register"] == CONTROLS_REGISTER
    assert by_name["GST/HST Return"]["register"] == FILINGS_REGISTER


def test_obligation_type_classifier():
    assert classify_obligation_type(_c("AML Training", frequency="Continuous")) == "ongoing_control"
    assert classify_obligation_type(_c("Record Retention Policy")) == "recordkeeping"
    assert classify_obligation_type(_c("Tax Balance Payment")) == "payment"
    assert classify_obligation_type(_c("Licence Renewal")) == "registration_or_licence"
    assert classify_obligation_type(_c("Breach Notification", frequency="Event-based")) == "event_triggered"
    assert classify_obligation_type(_c("Annual Corporate Tax Return")) == "periodic_filing"


def test_empty_and_singleton_are_noops():
    assert normalize_and_dedupe([], jurisdiction="canada", adjudicate=False)[1].output_count == 0
    out, rep = normalize_and_dedupe(
        [_c("Some Filing")], jurisdiction="zz", adjudicate=False
    )
    assert rep.output_count == 1
