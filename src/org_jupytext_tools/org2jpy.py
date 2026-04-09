#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "jupytext>=1.19.1",
#   "PyYAML>=6.0",
# ]
# ///

"""Export an Org notebook to a Jupytext text format via a temporary notebook.

The script is intentionally narrow:
- Input is an Org file.
- Pandoc converts the Org file to a temporary ``.ipynb``.
- Jupytext converts that temporary notebook to the requested text format.
- By default, no final ``.ipynb`` is written.

This is designed for workflows where the Org file is canonical and a text notebook
representation is generated on demand for sharing or committing.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

import yaml
from jupytext.pandoc import PandocError, raise_if_pandoc_is_not_available

DEFAULT_OUTPUT_FORMAT: Final[str] = "md:pandoc"
MARKDOWN_SUFFIXES: Final[set[str]] = {".md", ".markdown", ".qmd", ".rmd"}
FRONT_MATTER_RE: Final[re.Pattern[str]] = re.compile(
    r"\A---\n(.*?)\n---\n", re.DOTALL
)
ORG_KERNEL_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^#\+JUPYTER_KERNEL_NAME:\s*(.+?)\s*$"
)
ORG_KERNEL_DISPLAY_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^#\+JUPYTER_KERNEL_DISPLAY_NAME:\s*(.+?)\s*$"
)
ORG_HEADER_ARGS_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^#\+PROPERTY:\s*header-args:jupyter-python\b(.*)$"
)
ORG_TARGET_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?m)^<<[^>\n]+>>[ \t]*\n?"
)
LEADING_HTML_ANCHOR_RE: Final[re.Pattern[str]] = re.compile(
    r'(?m)^`<span id="[^"]+"></span>`\{=html\}[ \t]*\n(?:[ \t]*\n)?'
)


class ConversionError(RuntimeError):
    """Raised when conversion fails in a user-facing way."""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Convert an Org file to a Jupytext text notebook format via Pandoc and a temporary ipynb."
        )
    )
    parser.add_argument("input_org", type=Path, help="Path to the input .org file.")
    parser.add_argument(
        "-f",
        "--output-format",
        default=DEFAULT_OUTPUT_FORMAT,
        help=(
            "Final Jupytext output format, e.g. 'md:pandoc' (default), 'md:myst', 'py:percent'."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path to the final Jupytext output. Defaults to the input stem plus a suffix based on the format.",
    )
    parser.add_argument(
        "--kernel-name",
        help=(
            "Override the kernel name. If omitted, the script looks for #+JUPYTER_KERNEL_NAME or "
            ":kernel in #+PROPERTY: header-args:jupyter-python."
        ),
    )
    parser.add_argument(
        "--kernel-display-name",
        help="Override the kernel display name. Defaults to the kernel name when available.",
    )
    parser.add_argument(
        "--write-ipynb",
        action="store_true",
        help="Also write a sibling .ipynb file next to the final output.",
    )
    parser.add_argument(
        "--ipynb-output",
        type=Path,
        help="Path for the optional final .ipynb output. Implies --write-ipynb.",
    )
    parser.add_argument(
        "--keep-org-targets",
        action="store_true",
        help=(
            "Do not strip standalone Org targets like <<id>> from the temporary Org source before Pandoc conversion."
        ),
    )
    parser.add_argument(
        "--keep-html-anchors",
        action="store_true",
        help=(
            "Do not strip leading raw HTML anchor lines like `<span id=...></span>` from markdown outputs."
        ),
    )
    return parser.parse_args()


def infer_output_path(input_org: Path, output_format: str) -> Path:
    """Infer the final output path from the input file and Jupytext format.

    Args:
        input_org: Input Org file.
        output_format: Requested Jupytext format.

    Returns:
        Path for the final output file.
    """
    base = input_org.with_suffix("")
    fmt_base = output_format.split(":", 1)[0]
    suffix_map = {
        "md": ".md",
        "py": ".py",
        "qmd": ".qmd",
        "rmd": ".Rmd",
        "Rmd": ".Rmd",
        "jl": ".jl",
        "r": ".R",
        "ipynb": ".ipynb",
    }
    suffix = suffix_map.get(fmt_base, f".{fmt_base}")
    return base.with_suffix(suffix)


def run_checked(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command and raise a readable error on failure.

    Args:
        cmd: Command and arguments.

    Returns:
        Completed process object.

    Raises:
        ConversionError: If the command exits non-zero.
    """
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        details = stderr or stdout or f"Command exited with status {proc.returncode}."
        raise ConversionError(f"Command failed: {' '.join(cmd)}\n{details}")
    return proc


def read_org_text(path: Path) -> str:
    """Read an Org file as UTF-8 text.

    Args:
        path: Input Org path.

    Returns:
        File contents.
    """
    return path.read_text(encoding="utf-8")


def extract_kernel_name(org_text: str) -> str | None:
    """Extract the kernel name from Org metadata.

    The search order is:
    1. ``#+JUPYTER_KERNEL_NAME``
    2. ``:kernel`` inside ``#+PROPERTY: header-args:jupyter-python``

    Args:
        org_text: Org file contents.

    Returns:
        Kernel name if found, otherwise ``None``.
    """
    match = ORG_KERNEL_NAME_RE.search(org_text)
    if match:
        return match.group(1).strip()

    header_match = ORG_HEADER_ARGS_RE.search(org_text)
    if not header_match:
        return None

    header_args = header_match.group(1)
    kernel_match = re.search(r":kernel\s+(\S+)", header_args)
    if kernel_match:
        return kernel_match.group(1).strip()
    return None


def extract_kernel_display_name(org_text: str) -> str | None:
    """Extract the kernel display name from Org metadata.

    Args:
        org_text: Org file contents.

    Returns:
        Display name if found, otherwise ``None``.
    """
    match = ORG_KERNEL_DISPLAY_NAME_RE.search(org_text)
    if match:
        return match.group(1).strip()
    return None


def strip_standalone_org_targets(org_text: str) -> str:
    """Strip standalone Org targets like ``<<id>>``.

    This is intended to avoid raw HTML anchor lines appearing in the generated
    markdown after Pandoc/Jupytext conversion.

    Args:
        org_text: Org file contents.

    Returns:
        Org text with standalone targets removed.
    """
    return ORG_TARGET_LINE_RE.sub("", org_text)


def patch_markdown_front_matter(
    text: str,
    kernel_name: str | None,
    kernel_display_name: str | None,
) -> str:
    """Patch Jupyter YAML front matter in a markdown-like output.

    Args:
        text: Output text, expected to begin with YAML front matter.
        kernel_name: Kernel name, if known.
        kernel_display_name: Kernel display name, if known.

    Returns:
        Patched text.
    """
    if not kernel_name:
        return text

    match = FRONT_MATTER_RE.match(text)
    if not match:
        return text

    metadata = yaml.safe_load(match.group(1)) or {}
    jupyter_meta = metadata.setdefault("jupyter", {})
    jupyter_meta["kernelspec"] = {
        "display_name": kernel_display_name or kernel_name,
        "language": "python",
        "name": kernel_name,
    }

    new_front_matter = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{new_front_matter}\n---\n{text[match.end():]}"


def strip_leading_html_anchors(text: str) -> str:
    """Strip raw HTML anchor lines from markdown outputs.

    Args:
        text: Output text.

    Returns:
        Cleaned text.
    """
    return LEADING_HTML_ANCHOR_RE.sub("", text)


def convert_org_to_ipynb(input_org_text: str, temp_ipynb: Path) -> None:
    """Convert Org text to a temporary notebook using Pandoc.

    Args:
        input_org_text: Org contents to convert.
        temp_ipynb: Destination notebook path.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".org", delete=False, encoding="utf-8"
    ) as temp_org:
        temp_org.write(input_org_text)
        temp_org_path = Path(temp_org.name)

    try:
        run_checked(
            [
                "pandoc",
                str(temp_org_path),
                "--to",
                "ipynb",
                "--output",
                str(temp_ipynb),
            ]
        )
    finally:
        temp_org_path.unlink(missing_ok=True)


def convert_ipynb_with_jupytext(temp_ipynb: Path, output_path: Path, output_format: str) -> None:
    """Convert a notebook to the requested Jupytext format.

    Args:
        temp_ipynb: Temporary notebook path.
        output_path: Final output path.
        output_format: Jupytext output format.
    """
    run_checked(
        [
            sys.executable,
            "-m",
            "jupytext",
            "--to",
            output_format,
            str(temp_ipynb),
            "-o",
            str(output_path),
        ]
    )


def is_markdown_like(path: Path, output_format: str) -> bool:
    """Return whether the final output is markdown-like.

    Args:
        path: Final output path.
        output_format: Jupytext output format.

    Returns:
        ``True`` when markdown-specific post-processing should run.
    """
    if path.suffix.lower() in MARKDOWN_SUFFIXES:
        return True
    return output_format.startswith("md:") or output_format in {"md", "qmd", "Rmd", "rmd"}


def postprocess_output(
    output_path: Path,
    output_format: str,
    kernel_name: str | None,
    kernel_display_name: str | None,
    keep_html_anchors: bool,
) -> None:
    """Patch and clean the final text output when appropriate.

    Args:
        output_path: Final output file.
        output_format: Jupytext output format.
        kernel_name: Kernel name.
        kernel_display_name: Kernel display name.
        keep_html_anchors: Whether to preserve raw HTML anchor lines.
    """
    if not is_markdown_like(output_path, output_format):
        return

    text = output_path.read_text(encoding="utf-8")
    text = patch_markdown_front_matter(text, kernel_name, kernel_display_name)
    if not keep_html_anchors:
        text = strip_leading_html_anchors(text)
    output_path.write_text(text, encoding="utf-8")


def main() -> int:
    """Run the conversion pipeline.

    Returns:
        Process exit code.
    """
    args = parse_args()

    input_org = args.input_org.expanduser().resolve()
    if not input_org.exists():
        raise ConversionError(f"Input file does not exist: {input_org}")
    if input_org.suffix.lower() != ".org":
        raise ConversionError(f"Input file is not an .org file: {input_org}")

    try:
        raise_if_pandoc_is_not_available(min_version="2.7.2")
    except PandocError as exc:
        raise ConversionError(str(exc)) from exc

    org_text = read_org_text(input_org)
    kernel_name = args.kernel_name or extract_kernel_name(org_text)
    kernel_display_name = (
        args.kernel_display_name
        or extract_kernel_display_name(org_text)
        or kernel_name
    )

    temp_org_text = org_text if args.keep_org_targets else strip_standalone_org_targets(org_text)

    output_path = (args.output or infer_output_path(input_org, args.output_format)).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    write_ipynb = args.write_ipynb or args.ipynb_output is not None
    ipynb_output = (
        args.ipynb_output.expanduser()
        if args.ipynb_output is not None
        else output_path.with_suffix(".ipynb")
    )

    with tempfile.TemporaryDirectory(prefix="org-jupytext-") as temp_dir:
        temp_ipynb = Path(temp_dir) / f"{input_org.stem}.ipynb"
        convert_org_to_ipynb(temp_org_text, temp_ipynb)
        convert_ipynb_with_jupytext(temp_ipynb, output_path, args.output_format)
        postprocess_output(
            output_path=output_path,
            output_format=args.output_format,
            kernel_name=kernel_name,
            kernel_display_name=kernel_display_name,
            keep_html_anchors=args.keep_html_anchors,
        )
        if write_ipynb:
            ipynb_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_ipynb, ipynb_output)

    print(f"Wrote {output_path}")
    if write_ipynb:
        print(f"Wrote {ipynb_output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConversionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
