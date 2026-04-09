#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "jupytext>=1.19.1",
#   "PyYAML>=6.0",
# ]
# ///

"""Convert a Jupytext-readable notebook or .ipynb file to Org format.

The script is intentionally narrow:
- Input can be a Jupyter notebook (``.ipynb``) or a text notebook that Jupytext can read.
- Non-markdown inputs are normalized to temporary ``md:pandoc`` with Jupytext.
- Markdown inputs are converted directly with Pandoc.
- Kernel metadata is extracted from Jupyter YAML front matter when present and written back
  into the Org file as ``#+PROPERTY: header-args:jupyter-<lang> ...``.
- By default, Python code blocks are rewritten from ``python`` to ``jupyter-python``
  (and similarly for other kernel languages when known).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

import yaml
from jupytext.pandoc import PandocError, raise_if_pandoc_is_not_available

MARKDOWN_SUFFIXES: Final[set[str]] = {".md", ".markdown", ".qmd", ".rmd"}
FRONT_MATTER_RE: Final[re.Pattern[str]] = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
LEADING_HTML_ANCHOR_RE: Final[re.Pattern[str]] = re.compile(
    r'(?m)^`<span id="[^"]+"></span>`\{=html\}[ \t]*\n(?:[ \t]*\n)?'
)
ORG_HEADER_ARGS_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^#\+PROPERTY:\s*header-args:(jupyter-[^\s]+)\b.*$"
)
ORG_BEGIN_SRC_RE_TEMPLATE: Final[str] = r"(?im)^(#\+begin_src\s+){}(?=\s|$)"


class ConversionError(RuntimeError):
    """Raised when conversion fails in a user-facing way."""


class NotebookMetadata(dict):
    """Notebook metadata extracted from a markdown YAML header."""

    @property
    def kernel_name(self) -> str | None:
        return self.get("kernel_name")

    @property
    def kernel_display_name(self) -> str | None:
        return self.get("kernel_display_name")

    @property
    def kernel_language(self) -> str | None:
        return self.get("kernel_language")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a Jupyter notebook or Jupytext-readable text notebook to Org format via md:pandoc."
        )
    )
    parser.add_argument("input_path", type=Path, help="Input notebook path.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output Org path. Defaults to the input stem plus .org.",
    )
    parser.add_argument(
        "--kernel-name",
        help="Override the kernel name extracted from YAML metadata.",
    )
    parser.add_argument(
        "--kernel-display-name",
        help="Override the kernel display name extracted from YAML metadata.",
    )
    parser.add_argument(
        "--kernel-language",
        help="Override the kernel language extracted from YAML metadata, e.g. python.",
    )
    parser.add_argument(
        "--session",
        help="Org-babel session name. Defaults to the kernel name when available.",
    )
    parser.add_argument(
        "--no-async",
        action="store_true",
        help="Do not include :async yes in the Org header-args property.",
    )
    parser.add_argument(
        "--exports",
        choices=["both", "code", "results", "none"],
        help="Optional :exports value to add to the Org header-args property.",
    )
    parser.add_argument(
        "--keep-html-anchors",
        action="store_true",
        help=(
            "Do not strip leading raw HTML anchor lines like `<span id=...></span>` from markdown inputs."
        ),
    )
    parser.add_argument(
        "--keep-source-language",
        action="store_true",
        help=(
            "Do not rewrite fenced-code languages like 'python' to Org src languages like 'jupyter-python'."
        ),
    )
    return parser.parse_args()


def infer_output_path(input_path: Path) -> Path:
    return input_path.with_suffix(".org")


def run_checked(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        details = stderr or stdout or f"Command exited with status {proc.returncode}."
        raise ConversionError(f"Command failed: {' '.join(cmd)}\n{details}")
    return proc


def is_markdown_like(path: Path) -> bool:
    return path.suffix.lower() in MARKDOWN_SUFFIXES


def strip_leading_html_anchors(text: str) -> str:
    return LEADING_HTML_ANCHOR_RE.sub("", text)


def extract_notebook_metadata_from_markdown(text: str) -> NotebookMetadata:
    metadata = NotebookMetadata()
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return metadata

    front_matter = yaml.safe_load(match.group(1)) or {}
    jupyter_meta = front_matter.get("jupyter", {}) or {}
    kernelspec = jupyter_meta.get("kernelspec", {}) or {}
    language_info = jupyter_meta.get("language_info", {}) or {}

    kernel_name = kernelspec.get("name")
    kernel_display_name = kernelspec.get("display_name")
    kernel_language = kernelspec.get("language") or language_info.get("name")

    if kernel_name:
        metadata["kernel_name"] = str(kernel_name)
    if kernel_display_name:
        metadata["kernel_display_name"] = str(kernel_display_name)
    if kernel_language:
        metadata["kernel_language"] = str(kernel_language)

    return metadata


def prepare_markdown_input(input_path: Path, keep_html_anchors: bool) -> tuple[str, NotebookMetadata]:
    text = input_path.read_text(encoding="utf-8")
    metadata = extract_notebook_metadata_from_markdown(text)
    if not keep_html_anchors:
        text = strip_leading_html_anchors(text)
    return text, metadata


def convert_with_jupytext_to_markdown(input_path: Path, temp_md: Path) -> str:
    run_checked(
        [
            sys.executable,
            "-m",
            "jupytext",
            "--to",
            "md:pandoc",
            str(input_path),
            "-o",
            str(temp_md),
        ]
    )
    return temp_md.read_text(encoding="utf-8")


def convert_markdown_text_to_org(markdown_text: str, output_path: Path) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as temp_md:
        temp_md.write(markdown_text)
        temp_md_path = Path(temp_md.name)

    try:
        run_checked(
            [
                "pandoc",
                str(temp_md_path),
                "-f",
                "markdown+yaml_metadata_block",
                "-t",
                "org",
                "-o",
                str(output_path),
            ]
        )
    finally:
        temp_md_path.unlink(missing_ok=True)


def normalize_kernel_language(language: str | None) -> str:
    if not language:
        return "python"
    return language.strip().lower()


def make_jupyter_block_language(language: str | None) -> str:
    return f"jupyter-{normalize_kernel_language(language)}"


def build_org_header_args_property(
    block_language: str,
    kernel_name: str | None,
    session: str | None,
    use_async: bool,
    exports: str | None,
) -> str:
    parts = [f"#+PROPERTY: header-args:{block_language}"]
    if kernel_name:
        parts.extend([":kernel", kernel_name])
    if session:
        parts.extend([":session", session])
    if use_async:
        parts.extend([":async", "yes"])
    if exports:
        parts.extend([":exports", exports])
    return " ".join(parts)


def insert_org_header_property(org_text: str, property_line: str | None) -> str:
    if not property_line:
        return org_text

    if ORG_HEADER_ARGS_RE.search(org_text):
        return org_text

    lines = org_text.splitlines(keepends=True)
    insert_at = 0
    while insert_at < len(lines):
        stripped = lines[insert_at].strip()
        if stripped.startswith("#+") and not stripped.lower().startswith("#+begin_"):
            insert_at += 1
            continue
        if stripped == "":
            insert_at += 1
            continue
        break

    prefix = "".join(lines[:insert_at])
    suffix = "".join(lines[insert_at:])
    separator = "" if prefix.endswith("\n") or not prefix else "\n"
    return f"{prefix}{separator}{property_line}\n{suffix}"


def rewrite_org_block_language(org_text: str, source_language: str, target_language: str) -> str:
    pattern = re.compile(ORG_BEGIN_SRC_RE_TEMPLATE.format(re.escape(source_language)))
    return pattern.sub(rf"\1{target_language}", org_text)


def postprocess_org_output(
    output_path: Path,
    kernel_name: str | None,
    kernel_language: str | None,
    session: str | None,
    use_async: bool,
    exports: str | None,
    keep_source_language: bool,
) -> None:
    org_text = output_path.read_text(encoding="utf-8")
    normalized_language = normalize_kernel_language(kernel_language)
    jupyter_block_language = make_jupyter_block_language(kernel_language)

    property_line = build_org_header_args_property(
        block_language=jupyter_block_language,
        kernel_name=kernel_name,
        session=session,
        use_async=use_async,
        exports=exports,
    )
    org_text = insert_org_header_property(org_text, property_line)

    if not keep_source_language:
        org_text = rewrite_org_block_language(
            org_text,
            source_language=normalized_language,
            target_language=jupyter_block_language,
        )

    output_path.write_text(org_text, encoding="utf-8")


def main() -> int:
    args = parse_args()

    input_path = args.input_path.expanduser().resolve()
    if not input_path.exists():
        raise ConversionError(f"Input file does not exist: {input_path}")

    try:
        raise_if_pandoc_is_not_available(min_version="2.7.2")
    except PandocError as exc:
        raise ConversionError(str(exc)) from exc

    output_path = (args.output or infer_output_path(input_path)).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if is_markdown_like(input_path):
        markdown_text, metadata = prepare_markdown_input(
            input_path=input_path,
            keep_html_anchors=args.keep_html_anchors,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="jpy-org-") as temp_dir:
            temp_md = Path(temp_dir) / f"{input_path.stem}.md"
            markdown_text = convert_with_jupytext_to_markdown(input_path, temp_md)
            metadata = extract_notebook_metadata_from_markdown(markdown_text)
            if not args.keep_html_anchors:
                markdown_text = strip_leading_html_anchors(markdown_text)

    kernel_name = args.kernel_name or metadata.kernel_name
    kernel_display_name = args.kernel_display_name or metadata.kernel_display_name
    kernel_language = args.kernel_language or metadata.kernel_language or "python"
    session = args.session or kernel_name

    convert_markdown_text_to_org(markdown_text, output_path)
    postprocess_org_output(
        output_path=output_path,
        kernel_name=kernel_name,
        kernel_language=kernel_language,
        session=session,
        use_async=not args.no_async,
        exports=args.exports,
        keep_source_language=args.keep_source_language,
    )

    print(f"Wrote {output_path}")
    if kernel_name:
        print(f"Kernel name: {kernel_name}")
    if kernel_display_name:
        print(f"Kernel display name: {kernel_display_name}")
    print(f"Kernel language: {kernel_language}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConversionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
