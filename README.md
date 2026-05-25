# Compliance AI Agent

Extracts structured, auditable compliance requirements from policy and regulation documents,
verifies them against the source, and diffs policy versions. Powered by Claude (live mode)
or curated stubs (mock mode, default).

## Install

```bash
pip install -e .
```

Mock mode runs without an API key. Pass `--live` (and set `ANTHROPIC_API_KEY`) to call Claude.

## Web UI

```bash
compliance-agent serve
```

Open `http://127.0.0.1:8000`. Pick a country → pick a regulation → see requirements grouped by category, with severity badges and verification findings.

Bundled regulations: **India** (DPDP Act 2023), **European Union** (GDPR), **United States** (HIPAA). All run on curated mock extractions by default — pass `--live` (with `ANTHROPIC_API_KEY`) to re-extract with Claude.

## CLI

Four subcommands: `extract`, `diff`, `render`, `serve`.

```bash
# Extract requirements
compliance-agent extract examples/sample_policy.txt --verify -o out.json
compliance-agent extract examples/sample_policy.txt --verify --format markdown -o out.md

# Diff two policy versions
compliance-agent diff examples/sample_policy.txt examples/sample_policy_v4.txt -o diff.md
compliance-agent diff examples/sample_policy.txt examples/sample_policy_v4.txt --format json -o diff.json

# Re-render a previously-saved JSON as Markdown
compliance-agent render out.json -o out.md

# Live mode (when you have an API key)
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # PowerShell
compliance-agent extract examples/sample_policy.txt --live --verify -o out.json
```

Each subcommand takes `--help` for full options.

## Library

```python
from compliance_agent import extract_requirements, compute_diff, render_extraction_markdown

result = extract_requirements("examples/sample_policy.txt")
print(render_extraction_markdown(result))
```

## Output shape

Each requirement carries: `requirement_id`, `title`, `summary`, verbatim `source_quote`,
`category`, `severity`, `applies_to`, `evidence_artifacts`, and `section_reference`.
See `src/compliance_agent/models.py` for the full schema.

## Verification

Pass `--verify` to grade each extracted requirement against the source. Two layers:

- **Python-side** — `quote_verbatim` substring check, plus sanity checks (non-empty
  evidence artifacts, applies-to, summary). Runs in both mock and live mode.
- **LLM-side** — second Claude call assigns `pass`/`warning`/`fail`, lists `issues`
  and `suggested_fix`, and surfaces `missed_requirements`. Live mode only.

## Diff mode

`compliance-agent diff old.txt new.txt` matches requirements by `requirement_id` and
emits `added`, `removed`, and `changed` sets. For changes, it lists which fields
differ and flags severity shifts (e.g. `medium ↑ high`).

The bundled samples (`sample_policy.txt` v3.2 vs `sample_policy_v4.txt` v4.0) demo
1 added requirement (JIT privileged access), 4 changed (tighter rotation, longer
retention, expanded MFA scope, faster incident SLA).

## How it works

- `claude-opus-4-7` with adaptive thinking + `effort: high` for careful extraction.
- Structured outputs via `messages.parse()` — responses are validated against the
  Pydantic `ExtractionResult` schema, so callers always get a typed object or an error.
- The system prompt is prompt-cached, so repeated runs against different documents pay
  the system-prompt token cost only on the first call within the cache TTL.
