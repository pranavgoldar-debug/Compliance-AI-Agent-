"""Global Compliance Tracker filings — intentionally empty.

The previously hardcoded, AI-generated tracker rows were removed: they were an
unverified source of truth that skewed results. Kept as an empty `TRACKER`
mapping so the catalog assembly in fintech/__init__ still works.
"""
from __future__ import annotations

TRACKER: dict = {}
