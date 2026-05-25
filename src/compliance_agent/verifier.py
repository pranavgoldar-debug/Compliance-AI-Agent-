from __future__ import annotations

import re
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from compliance_agent.models import (
    ExtractionResult,
    FindingStatus,
    VerificationFinding,
    VerificationResult,
)

VERIFIER_SYSTEM_PROMPT = """You are an auditor grading a compliance extraction.

You will receive:
1. The full source document.
2. A list of extracted requirements (id, summary, source_quote, category, severity, etc.).

For each requirement, decide if it is faithful to the source:
- `pass` — the requirement is supported by the source, the summary accurately reflects the obligation, and category/severity are reasonable.
- `warning` — minor issues: summary is imprecise, severity is debatable, category is suboptimal, evidence artifacts are weak. The obligation itself is real.
- `fail` — the obligation is hallucinated or unsupported, the summary contradicts the source, or material details are wrong.

The `quote_verbatim` field will be set by the calling code — do not set it. Focus on semantic faithfulness.

Also list `missed_requirements`: distinct obligations in the source that were not extracted. Each entry should describe the missing obligation and quote the source sentence."""


_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text).strip().lower()


def check_quote_verbatim(source: str, quote: str) -> bool:
    """Whitespace-tolerant substring check."""
    if not quote:
        return False
    return _normalize(quote) in _normalize(source)


class _ModelFinding(BaseModel):
    requirement_id: str
    status: FindingStatus
    issues: list[str] = Field(default_factory=list)
    suggested_fix: Optional[str] = None


class _ModelVerificationResult(BaseModel):
    findings: list[_ModelFinding]
    overall_summary: str
    missed_requirements: list[str] = Field(default_factory=list)


class ComplianceVerifier:
    def __init__(
        self,
        client: Optional[anthropic.Anthropic] = None,
        model: str = "claude-opus-4-7",
    ):
        self.client = client or anthropic.Anthropic()
        self.model = model

    def verify(self, source_text: str, extraction: ExtractionResult) -> VerificationResult:
        quote_verbatim = {
            req.requirement_id: check_quote_verbatim(source_text, req.source_quote)
            for req in extraction.requirements
        }

        extraction_payload = extraction.model_dump_json(indent=2)
        user_content = (
            "SOURCE DOCUMENT:\n"
            f"{source_text}\n\n"
            "---\n\n"
            "EXTRACTED REQUIREMENTS:\n"
            f"{extraction_payload}"
        )

        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=[
                {
                    "type": "text",
                    "text": VERIFIER_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
            output_format=_ModelVerificationResult,
        )

        if response.parsed_output is None:
            raise RuntimeError(
                f"Verification failed — stop_reason={response.stop_reason}."
            )

        model_result = response.parsed_output
        findings_by_id = {f.requirement_id: f for f in model_result.findings}

        merged_findings: list[VerificationFinding] = []
        for req in extraction.requirements:
            model_finding = findings_by_id.get(req.requirement_id)
            verbatim = quote_verbatim[req.requirement_id]
            if model_finding is None:
                merged_findings.append(
                    VerificationFinding(
                        requirement_id=req.requirement_id,
                        status=FindingStatus.warning,
                        quote_verbatim=verbatim,
                        issues=["Verifier did not return a finding for this requirement."],
                    )
                )
                continue

            issues = list(model_finding.issues)
            status = model_finding.status
            if not verbatim:
                issues.append("`source_quote` is not a verbatim substring of the source document.")
                if status == FindingStatus.pass_:
                    status = FindingStatus.warning

            merged_findings.append(
                VerificationFinding(
                    requirement_id=req.requirement_id,
                    status=status,
                    quote_verbatim=verbatim,
                    issues=issues,
                    suggested_fix=model_finding.suggested_fix,
                )
            )

        return VerificationResult(
            findings=merged_findings,
            overall_summary=model_result.overall_summary,
            missed_requirements=model_result.missed_requirements,
        )
