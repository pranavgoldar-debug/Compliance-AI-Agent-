from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from compliance_agent.models import ExtractionResult

SYSTEM_PROMPT = """You are a compliance analyst that extracts structured, auditable obligations from policy and regulation documents.

When you receive a document:
- Identify every distinct, testable obligation. Split compound sentences into separate requirements when they impose independent duties.
- Preserve the source's exact wording in `source_quote` — do not paraphrase that field. Paraphrase only in `summary`.
- Prefer the source's own identifiers (article numbers, control IDs, section numbers). Synthesize one only when none exist.
- Assign severity by operational risk if the requirement is unmet, not by how prominently the source phrases it.
- For `evidence_artifacts`, name documents or system outputs an auditor would actually request — not abstract concepts.
- If the document is ambiguous, contradictory, or appears truncated, note it in `extraction_notes` rather than guessing.
- Do not invent requirements that are not supported by the source text."""


def read_document(source: Union[str, Path]) -> str:
    path = Path(source)
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


class ComplianceExtractor:
    def __init__(
        self,
        client: Optional[Any] = None,
        model: str = "claude-opus-4-8",
    ):
        from compliance_agent.ai.llm_client import make_client

        self.client = client or make_client()
        self.model = model

    def extract(self, document_text: str, *, framework_hint: Optional[str] = None) -> ExtractionResult:
        user_content = document_text
        if framework_hint:
            user_content = f"Framework hint: {framework_hint}\n\n---\n\n{document_text}"

        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
            output_format=ExtractionResult,
        )

        if response.parsed_output is None:
            raise RuntimeError(
                f"Extraction failed — stop_reason={response.stop_reason}. "
                "The model did not return a parseable ExtractionResult."
            )
        return response.parsed_output

    def extract_from_file(
        self, source: Union[str, Path], *, framework_hint: Optional[str] = None
    ) -> ExtractionResult:
        return self.extract(read_document(source), framework_hint=framework_hint)


def extract_requirements(
    source: Union[str, Path],
    *,
    framework_hint: Optional[str] = None,
    model: str = "claude-opus-4-8",
) -> ExtractionResult:
    return ComplianceExtractor(model=model).extract_from_file(source, framework_hint=framework_hint)
