"""Lithuania filing catalog — intentionally empty.

The previously hardcoded, AI-generated seed filings were removed: they were an
unverified source of truth that skewed results. Obligations now come from live
discovery ("Find Regulations") + human review, not from this list. Kept as an
empty `FILINGS` so the catalog assembly in fintech/__init__ still works.
"""
from __future__ import annotations

FILINGS: list = []
