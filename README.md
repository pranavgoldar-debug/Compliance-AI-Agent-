# Compliance AI Agent

Extracts structured, auditable compliance requirements from policy and regulation documents using Claude.

## Install

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

## CLI

```bash
compliance-agent examples/sample_policy.txt -o requirements.json
compliance-agent examples/sample_policy.txt --framework "SOC 2"
compliance-agent examples/sample_policy.txt --verify -o results.json
```

Supports `.txt` and `.pdf` input.

## Library

```python
from compliance_agent import extract_requirements

result = extract_requirements("examples/sample_policy.txt")
for req in result.requirements:
    print(f"[{req.severity}] {req.requirement_id}: {req.title}")
```

## Output shape

Each requirement carries: `requirement_id`, `title`, `summary`, verbatim `source_quote`,
`category`, `severity`, `applies_to`, `evidence_artifacts`, and `section_reference`.
See `src/compliance_agent/models.py` for the full schema.

## Verification

Pass `--verify` (CLI) or use `ComplianceVerifier` directly to grade an extraction
against the source. Each requirement gets a finding:

- `quote_verbatim` — Python-side check that `source_quote` appears verbatim in the
  source (whitespace-tolerant). No model call needed.
- `status` (`pass` / `warning` / `fail`) plus `issues` and `suggested_fix` — a second
  Claude call grades semantic faithfulness, catching hallucinated obligations and
  miscalibrated severity. Also surfaces `missed_requirements` the extractor skipped.

```python
from compliance_agent import ComplianceExtractor, ComplianceVerifier
from compliance_agent.extractor import read_document

text = read_document("examples/sample_policy.txt")
extraction = ComplianceExtractor().extract(text)
verification = ComplianceVerifier().verify(text, extraction)
for f in verification.findings:
    if f.status != "pass":
        print(f.requirement_id, f.status, f.issues)
```

## How it works

- `claude-opus-4-7` with adaptive thinking + `effort: high` for careful extraction.
- Structured outputs via `messages.parse()` — the response is validated against the
  Pydantic `ExtractionResult` schema, so callers always get a typed object or an error.
- The system prompt is prompt-cached, so repeated runs against different documents pay
  the system-prompt token cost only on the first call within the cache TTL.
