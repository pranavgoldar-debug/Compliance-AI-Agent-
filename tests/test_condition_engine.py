"""Condition-engine invariants — the Round 2/3 filter.

Locks the critical rule: an UNKNOWN attribute (TBC / unanswered) is treated as
TRUE (safe-include) and the row lands Conditional, never dropped. Run: `pytest`.
"""
from compliance_agent.condition_engine import classify

MANDATORY, CONDITIONAL, NOT_APPLICABLE = "mandatory", "conditional", "not_applicable"


def test_yes_answer_is_mandatory():
    cond = {"all_of": [{"attr": "employs_staff", "eq": True}]}
    assert classify(cond, {"employs_staff": True}) == MANDATORY


def test_no_answer_is_not_applicable():
    cond = {"all_of": [{"attr": "employs_staff", "eq": True}]}
    assert classify(cond, {"employs_staff": False}) == NOT_APPLICABLE


def test_unknown_attr_is_conditional_not_dropped():
    # employs_staff unanswered (absent) -> safe-include + verify -> conditional
    cond = {"all_of": [{"attr": "employs_staff", "eq": True}]}
    assert classify(cond, {}) == CONDITIONAL


def test_always_is_mandatory():
    assert classify({"always": True}, {}) == MANDATORY


def test_any_of_one_true():
    cond = {"any_of": [
        {"attr": "company_size_band", "in": ["medium", "large"]},
        {"attr": "audit_exemption_ineligible", "eq": True},
    ]}
    assert classify(cond, {"company_size_band": "large", "audit_exemption_ineligible": False}) == MANDATORY


def test_none_of_blocks():
    cond = {"none_of": [{"attr": "vat_gst_registered", "eq": True}]}
    assert classify(cond, {"vat_gst_registered": True}) == NOT_APPLICABLE
    assert classify(cond, {"vat_gst_registered": False}) == MANDATORY


def test_threshold_gate_unconfirmed_is_conditional():
    # intra-group on, TP threshold unanswered -> conditional (verify), not dropped
    cond = {"all_of": [
        {"attr": "intra_group_transactions", "eq": True},
        {"attr": "group_consolidated_revenue_threshold_met", "eq": True},
    ]}
    assert classify(cond, {"intra_group_transactions": True}) == CONDITIONAL
