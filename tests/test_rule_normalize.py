"""Contract for canonical_code — the form-code identity that makes the existing
name+cadence dedupe (api.entities) collapse phrasing variants of the same coded
filing, while never merging genuinely different forms.

The cardinal sin is a FALSE MERGE (it hides an obligation), so these tests pin
both directions: coded phrasings share a key, distinct forms do not.
"""
from compliance_agent.rule_normalize import canonical_code


def test_t1134_phrasings_share_a_key():
    a = canonical_code("Foreign Affiliate Information Return", "T1134", "canada")
    b = canonical_code("T1134 return", "T1134 — Foreign Affiliate Information Return", "canada")
    assert a == b == "CANADA::T1134"


def test_t4_variants_share_a_key():
    keys = {
        canonical_code("Statement of Remuneration Paid", "T4", "canada"),
        canonical_code("T4 slips", "T4", "canada"),
        canonical_code("T4 Information Return", "T4", "canada"),
    }
    assert keys == {"CANADA::T4"}


def test_cit_balance_phrasings_share_a_key():
    a = canonical_code("Corporate Tax Balance Payment", "Corporate Tax Balance Payment", "canada")
    b = canonical_code("Corporate Income Tax Balance Payment", "x", "canada")
    assert a == b == "CANADA::CIT-BALANCE"


def test_t4_and_t4a_are_distinct():
    assert canonical_code("T4 slip", "T4", "canada") == "CANADA::T4"
    assert canonical_code("T4A", "T4A", "canada") == "CANADA::T4A"


def test_balance_payment_distinct_from_instalment():
    assert canonical_code("Corporate Income Tax Balance Payment", "x", "canada") == "CANADA::CIT-BALANCE"
    assert canonical_code("Corporate Income Tax Instalments", "monthly instalment", "canada") == "CANADA::CIT-INSTALMENT"


def test_whole_word_code_does_not_match_inside_longer_code():
    # T2 (catalog) must not swallow T2125; T2125 gets its own leading-code key.
    assert canonical_code("T2 corporation return", "T2", "canada") == "CANADA::T2"
    assert canonical_code("T2125 business income", "T2125", "canada") == "CANADA::T2125"


def test_uncoded_filing_returns_none():
    # Falls back to the existing name-based dedupe in api.entities.
    assert canonical_code("Annual Financial Statements", "Annual Financial Statements", "canada") is None
    assert canonical_code("Some Novel Filing", "Some Novel Filing", "canada") is None


def test_jurisdiction_prefixes_the_key():
    assert canonical_code("CT600 return", "CT600", "uk") == "UK::CT600"
    # different jurisdiction -> different key, so codes never collide across borders
    assert canonical_code("CT600 return", "CT600", "uk") != canonical_code("CT600 return", "CT600", "canada")


def test_leading_code_only_no_passing_mention_merge():
    # A code merely mentioned mid-name must not become the identity.
    assert canonical_code("PAYE RTI return plus P11D", "PAYE RTI return plus P11D", "uk") is None
