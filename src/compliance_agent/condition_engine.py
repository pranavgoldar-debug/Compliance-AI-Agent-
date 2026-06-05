"""Machine-condition evaluator (spec §4 / §7).

Every discovered obligation can carry a `condition`: a boolean tree over the
entity's attributes. An obligation APPLIES iff its condition evaluates TRUE.

Grammar:
  - Leaf:        {"attr": "<name>", "<op>": <value>}
                 ops: eq, neq, gte, lte, gt, lt, in
                 ("in" = scalar in list, or for a list-valued attr the set is a
                  subset of the list)
  - Combinators: all_of (AND), any_of (OR), none_of (NOR), always
  - Unknown:     if an attribute is null/absent (TBC / unanswered), the clause
                 is treated as TRUE (safe-include) and the row is flagged
                 "verify". Under-inclusion is the dangerous failure, so the bias
                 is to keep.

`classify` turns the evaluation into a verdict:
  - not applicable → condition is FALSE
  - conditional    → TRUE but relied on an unknown (needs verify)
  - mandatory      → TRUE on known data only

This is a faithful Python port of the reference JS evaluator in the spec — the
unknown→safe-include rule is preserved exactly.
"""
from __future__ import annotations

from typing import Any, Optional

# Verdict vocabulary (matches the rest of the app).
MANDATORY = "mandatory"
CONDITIONAL = "conditional"
NOT_APPLICABLE = "not_applicable"

_LEAF_OPS = {"eq", "neq", "gte", "lte", "gt", "lt", "in"}


def eval_condition(c: Optional[dict], attrs: dict[str, Any]) -> tuple[bool, bool]:
    """Return (applies, used_unknown). Mirrors the spec §7 evaluator exactly."""
    if not c or c.get("always"):
        return True, False

    if "all_of" in c:
        used = False
        for sub in c["all_of"]:
            applies, uu = eval_condition(sub, attrs)
            used = used or uu
            if not applies:
                return False, used
        return True, used

    if "any_of" in c:
        any_clean_true = False
        any_unknown_true = False
        for sub in c["any_of"]:
            applies, uu = eval_condition(sub, attrs)
            if applies:
                if uu:
                    any_unknown_true = True
                else:
                    any_clean_true = True
        if any_clean_true:  # a clean-true branch wins; ignore unknowns elsewhere
            return True, False
        if any_unknown_true:
            return True, True
        return False, False

    if "none_of" in c:
        used = False
        for sub in c["none_of"]:
            applies, uu = eval_condition(sub, attrs)
            used = used or uu
            if applies:
                return False, used
        return True, used

    # Leaf.
    attr = c.get("attr")
    v = attrs.get(attr) if attr is not None else None
    if v is None:
        return True, True  # safe-include unknown
    for op, operand in c.items():
        if op == "attr" or op not in _LEAF_OPS:
            continue
        if op == "eq" and not (v == operand):
            return False, False
        if op == "neq" and not (v != operand):
            return False, False
        if op == "gte" and not (v >= operand):
            return False, False
        if op == "lte" and not (v <= operand):
            return False, False
        if op == "gt" and not (v > operand):
            return False, False
        if op == "lt" and not (v < operand):
            return False, False
        if op == "in":
            ok = all(x in operand for x in v) if isinstance(v, list) else (v in operand)
            if not ok:
                return False, False
    return True, False


def classify(condition: Optional[dict], attrs: dict[str, Any]) -> str:
    """mandatory / conditional / not_applicable for a condition + attributes."""
    applies, used_unknown = eval_condition(condition, attrs)
    if not applies:
        return NOT_APPLICABLE
    return CONDITIONAL if used_unknown else MANDATORY
