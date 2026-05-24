from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from compliance_agent.extractor import ComplianceExtractor


@click.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--framework",
    "framework_hint",
    default=None,
    help="Optional framework hint (e.g. 'SOC 2', 'GDPR', 'HIPAA').",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write JSON to this path instead of stdout.",
)
@click.option(
    "--model",
    default="claude-opus-4-7",
    show_default=True,
    help="Claude model ID.",
)
def main(source: Path, framework_hint: Optional[str], output: Optional[Path], model: str) -> None:
    """Extract structured compliance requirements from a policy or regulation document."""
    extractor = ComplianceExtractor(model=model)
    click.echo(f"Extracting requirements from {source}...", err=True)
    result = extractor.extract_from_file(source, framework_hint=framework_hint)

    payload = result.model_dump_json(indent=2)
    if output:
        output.write_text(payload, encoding="utf-8")
        click.echo(f"Wrote {len(result.requirements)} requirements to {output}", err=True)
    else:
        sys.stdout.write(payload + "\n")


if __name__ == "__main__":
    main()
