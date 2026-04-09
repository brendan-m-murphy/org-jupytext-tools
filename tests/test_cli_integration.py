from __future__ import annotations

import difflib
import re
from pathlib import Path

import jupytext
import pytest

from org_jupytext_tools.common import ConversionError, ensure_pandoc_available
from org_jupytext_tools.jpy2org import main as jpy2org_main
from org_jupytext_tools.org2jpy import main as org2jpy_main


DATA_DIR = Path(__file__).parent / "data"
CELL_ID_RE = re.compile(r"(?m)^::: \{#([^ ]+) \.cell\b")


def require_external_tools() -> None:
    """Skip integration tests when Pandoc is unavailable."""
    try:
        ensure_pandoc_available()
    except ConversionError as exc:
        pytest.skip(str(exc))


def normalize_markdown_semantics(path: Path) -> str:
    """Normalize markdown notebook content for semantic round-trip comparison."""
    notebook = jupytext.read(path)
    merged_cells: list[tuple[str, str]] = []

    for cell in notebook.cells:
        normalized_source = normalize_cell_source(cell.cell_type, cell.source)
        if (
            cell.cell_type == "markdown"
            and merged_cells
            and merged_cells[-1][0] == "markdown"
        ):
            previous = merged_cells[-1][1]
            merged_cells[-1] = (
                "markdown",
                normalize_cell_source("markdown", f"{previous}\n\n{normalized_source}"),
            )
            continue
        merged_cells.append((cell.cell_type, normalized_source))

    kernelspec = getattr(notebook.metadata, "kernelspec", {}) or {}
    header = [
        f"name={getattr(kernelspec, 'name', '')}",
        f"display={getattr(kernelspec, 'display_name', '')}",
        f"language={getattr(kernelspec, 'language', '')}",
    ]
    body = [f"[{cell_type}]\n{source}" for cell_type, source in merged_cells]
    return "\n".join(header + body).strip()


def normalize_cell_source(cell_type: str, source: str) -> str:
    """Normalize cell source while tolerating markdown line wrapping differences."""
    stripped = "\n".join(line.rstrip() for line in source.strip().splitlines())
    if cell_type != "markdown":
        return stripped
    return re.sub(r"(?<!\n)\n(?!\n)", " ", stripped)


def count_adjacent_markdown_pairs(path: Path) -> int:
    """Count consecutive markdown cell pairs in a notebook file."""
    notebook = jupytext.read(path)
    pairs = 0
    previous_type = None
    for cell in notebook.cells:
        if cell.cell_type == "markdown" and previous_type == "markdown":
            pairs += 1
        previous_type = cell.cell_type
    return pairs


def test_org_to_markdown_pandoc(tmp_path: Path) -> None:
    """Convert a small Org fixture to markdown and preserve key behavior."""
    require_external_tools()
    input_org = DATA_DIR / "minimal_example.org"
    output_md = tmp_path / "minimal_example.md"

    assert org2jpy_main([str(input_org), "-o", str(output_md)]) == 0

    text = output_md.read_text(encoding="utf-8")
    assert "display_name: Python 3" in text
    assert "name: python3" in text
    assert "language: python" in text
    assert "<<example-target>>" not in text
    assert "<span id=" not in text
    assert 'print("hello")' in text


def test_markdown_to_org_from_fixture(tmp_path: Path) -> None:
    """Convert the markdown fixture to Org with emacs-jupyter header args."""
    require_external_tools()
    input_md = DATA_DIR / "cte_hr_data_retrieve.md"
    output_org = tmp_path / "cte_hr_data_retrieve.org"

    assert jpy2org_main([str(input_md), "-o", str(output_org)]) == 0

    text = output_org.read_text(encoding="utf-8")
    assert (
        "#+PROPERTY: header-args:jupyter-python :kernel verification-games-fluxes "
        ":session verification-games-fluxes :async yes"
    ) in text
    assert "#+begin_src jupyter-python" in text
    assert "<span id=" not in text


def test_ipynb_to_org_from_fixture(tmp_path: Path) -> None:
    """Convert the notebook fixture to Org via temporary markdown normalization."""
    require_external_tools()
    input_ipynb = DATA_DIR / "cte_hr_data_retrieve.ipynb"
    output_org = tmp_path / "cte_hr_data_retrieve.org"

    assert jpy2org_main([str(input_ipynb), "-o", str(output_org)]) == 0

    text = output_org.read_text(encoding="utf-8")
    assert (
        "#+PROPERTY: header-args:jupyter-python :kernel verification-games-fluxes "
        ":session verification-games-fluxes :async yes"
    ) in text
    assert "#+begin_src jupyter-python" in text
    assert "Getting CTE-HR fluxes" in text


def test_markdown_roundtrip_diff_is_empty_after_expected_normalization(
    tmp_path: Path,
) -> None:
    """Treat the fixture round trip as equivalent after expected normalizations."""
    require_external_tools()
    input_md = DATA_DIR / "cte_hr_data_retrieve.md"
    roundtrip_org = tmp_path / "roundtrip.org"
    roundtrip_md = tmp_path / "roundtrip.md"

    assert jpy2org_main([str(input_md), "-o", str(roundtrip_org)]) == 0
    assert org2jpy_main([str(roundtrip_org), "-o", str(roundtrip_md)]) == 0

    original_text = input_md.read_text(encoding="utf-8")
    roundtrip_text = roundtrip_md.read_text(encoding="utf-8")
    assert original_text != roundtrip_text

    original_ids = CELL_ID_RE.findall(original_text)
    roundtrip_ids = CELL_ID_RE.findall(roundtrip_text)
    assert original_ids
    assert roundtrip_ids
    assert original_ids != roundtrip_ids

    assert count_adjacent_markdown_pairs(input_md) > count_adjacent_markdown_pairs(
        roundtrip_md
    )

    original_normalized = normalize_markdown_semantics(input_md)
    roundtrip_normalized = normalize_markdown_semantics(roundtrip_md)
    diff = "\n".join(
        difflib.unified_diff(
            original_normalized.splitlines(),
            roundtrip_normalized.splitlines(),
            fromfile="original-normalized",
            tofile="roundtrip-normalized",
            lineterm="",
        )
    )
    assert original_normalized == roundtrip_normalized, diff
