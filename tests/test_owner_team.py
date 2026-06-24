"""Owner-team engine regression — the 8 worked cases from the routing spec.

These are the cases most often tagged wrong; they ship as a unit so the
deterministic classifier never silently regresses. Run: `pytest`.
"""
from compliance_agent.classification import owner_team_engine as ot

# (filing name, authority/recipient, category, area, triggering_activity) -> team
SPEC_CASES = [
    ("DFSA Annual AML Return", "DFSA", "AML / CFT", "", None, "Compliance"),               # Rule 1
    ("TDS on salary (24Q)", "Income Tax Department", "Withholding", "", None, "Finance"),  # Rule 2 (tax mechanic)
    ("Form 16 to employees", "Employees / Income Tax Dept", "Payroll", "", None, "HR"),    # Rule 3
    ("Audited Financial Statements to the Registrar", "Registrar of Companies",
     "Corporate & Statutory", "", None, "Finance"),                                        # Tie-breaker A
    ("Client Money Auditor's Report to DFSA", "DFSA", "Regulatory", "", None, "Compliance"),  # Tie-breaker B
    ("BEN-2 beneficial owners to the registry", "Registry", "Corporate & Statutory", "", None, "Legal"),  # Rule 4
    ("Change-in-control approval to the DFSA", "DFSA", "Regulatory", "", None, "Compliance"),  # Rule 1 beats Rule 4
    ("Data protection notification", "Privacy Commissioner",
     "Data Protection & Privacy", "", None, "Legal"),                                      # Tie-breaker C
]


def test_spec_worked_cases():
    for name, auth, cat, area, ta, expected in SPEC_CASES:
        assert ot(name, auth, cat, area, ta) == expected, f"{name!r} should route to {expected}"


def test_always_one_of_four():
    teams = {"Finance", "Compliance", "Legal", "HR"}
    samples = [
        ("Some unknown filing", "", "", "", None),
        ("Mystery return", "Random Authority", "Misc", "stuff", None),
        ("Activity-gated thing", "", "", "", "employs_staff"),
        ("", "", "", "", "registered_company"),
        ("", "", "", "", "vat_gst_registered"),
        ("", "", "", "", "holds_customer_funds"),
        ("", "", "", "", None),
    ]
    for args in samples:
        assert ot(*args) in teams


def test_activity_fallback():
    assert ot("x", "", "", "", "employs_staff") == "HR"
    assert ot("x", "", "", "", "registered_company") == "Legal"
    assert ot("x", "", "", "", "vat_gst_registered") == "Finance"
    assert ot("x", "", "", "", "holds_customer_funds") == "Compliance"


def test_regulator_recipient_wins():
    # A regulator-facing filing is Compliance even for an ownership subject.
    assert ot("Change in control notification", "FINTRAC", "Regulatory", "", None) == "Compliance"
    # FINTRAC AML reports route to Compliance.
    assert ot("Suspicious Transaction Report (STR)", "FINTRAC", "AML / CFT", "", None) == "Compliance"
