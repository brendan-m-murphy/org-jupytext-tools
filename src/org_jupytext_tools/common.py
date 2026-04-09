from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import re
import subprocess
import tempfile
from pathlib import Path
from collections.abc import Iterator

import yaml
from jupytext.pandoc import PandocError, raise_if_pandoc_is_not_available

DEFAULT_OUTPUT_FORMAT = "md:pandoc"
DEFAULT_KERNEL_LANGUAGE = "python"
MARKDOWN_SUFFIXES = {".md", ".markdown", ".qmd", ".rmd"}
FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
ORG_KERNEL_NAME_RE = re.compile(r"(?im)^#\+JUPYTER_KERNEL_NAME:\s*(.+?)\s*$")
ORG_KERNEL_DISPLAY_NAME_RE = re.compile(
    r"(?im)^#\+JUPYTER_KERNEL_DISPLAY_NAME:\s*(.+?)\s*$"
)
ORG_HEADER_ARGS_RE = re.compile(
    r"(?im)^#\+PROPERTY:\s*header-args:(jupyter-[^\s]+)\b(.*)$"
)
ORG_TARGET_LINE_RE = re.compile(r"(?m)^<<[^>\n]+>>[ \t]*\n?")
LEADING_HTML_ANCHOR_RE = re.compile(
    r'(?m)^`<span id="[^"]+"></span>`\{=html\}[ \t]*\n(?:[ \t]*\n)?'
)
ORG_BEGIN_SRC_RE_TEMPLATE = r"(?im)^(#\+begin_src\s+){}(?=\s|$)"


class ConversionError(RuntimeError):
    """Raised when conversion fails in a user-facing way."""


@dataclass(slots=True)
class NotebookMetadata:
    """Hold notebook kernel metadata extracted from Org or markdown text."""

    kernel_name: str | None = None
    kernel_display_name: str | None = None
    kernel_language: str | None = None


def ensure_pandoc_available() -> None:
    """Raise a user-facing error when Pandoc is unavailable.

    Raises:
        ConversionError: Pandoc is not installed or is too old.
    """
    try:
        raise_if_pandoc_is_not_available(min_version="2.7.2")
    except PandocError as exc:
        raise ConversionError(str(exc)) from exc


def run_checked(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command and raise a readable conversion error on failure.

    Args:
        cmd: Command and arguments to execute.

    Returns:
        The completed subprocess result.

    Raises:
        ConversionError: The command exits with a non-zero status.
    """
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        details = stderr or stdout or f"Command exited with status {proc.returncode}."
        raise ConversionError(f"Command failed: {' '.join(cmd)}\n{details}")
    return proc


@contextmanager
def temporary_text_file(text: str, suffix: str) -> Iterator[Path]:
    """Write text to a temporary file and clean it up afterwards.

    Args:
        text: File contents to write.
        suffix: Filename suffix for the temporary file.

    Yields:
        The path to the temporary file.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=suffix,
        delete=False,
        encoding="utf-8",
    ) as handle:
        handle.write(text)
        path = Path(handle.name)

    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


@contextmanager
def temporary_directory(prefix: str) -> Iterator[Path]:
    """Yield a temporary directory path for short-lived conversion work.

    Args:
        prefix: Prefix used for the temporary directory name.

    Yields:
        The path to the temporary directory.
    """
    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        yield Path(directory)


def infer_output_suffix(output_format: str) -> str:
    """Infer a file suffix from a Jupytext output format string.

    Args:
        output_format: Jupytext format such as ``md:pandoc`` or ``py:percent``.

    Returns:
        A file suffix suitable for the converted output.
    """
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
    return suffix_map.get(fmt_base, f".{fmt_base}")


def infer_jupytext_output_path(input_path: Path, output_format: str) -> Path:
    """Build the default Jupytext output path for an input file.

    Args:
        input_path: Source file path.
        output_format: Requested Jupytext output format.

    Returns:
        The inferred output path with an appropriate suffix.
    """
    return input_path.with_suffix(infer_output_suffix(output_format))


def is_markdown_like(path: Path) -> bool:
    """Return whether a path has a markdown-like suffix."""
    return path.suffix.lower() in MARKDOWN_SUFFIXES


def is_markdown_output(path: Path, output_format: str) -> bool:
    """Return whether a Jupytext conversion target should be treated as markdown.

    Args:
        path: Output path.
        output_format: Requested Jupytext output format.

    Returns:
        ``True`` when markdown post-processing should be applied.
    """
    if is_markdown_like(path):
        return True
    return output_format.startswith("md:") or output_format in {
        "md",
        "qmd",
        "Rmd",
        "rmd",
    }


def normalize_kernel_language(language: str | None) -> str:
    """Normalize a kernel language value for downstream use."""
    if not language:
        return DEFAULT_KERNEL_LANGUAGE
    return language.strip().lower()


def make_jupyter_block_language(language: str | None) -> str:
    """Build an Org source block language name for emacs-jupyter."""
    return f"jupyter-{normalize_kernel_language(language)}"


def strip_org_targets(text: str) -> str:
    """Remove standalone Org targets that otherwise become raw HTML anchors."""
    return ORG_TARGET_LINE_RE.sub("", text)


def strip_html_anchor_lines(text: str) -> str:
    """Remove raw HTML anchor lines from markdown-like text."""
    return LEADING_HTML_ANCHOR_RE.sub("", text)


def extract_kernel_metadata_from_markdown(text: str) -> NotebookMetadata:
    """Extract notebook kernel metadata from markdown YAML front matter.

    Args:
        text: Markdown notebook text, optionally starting with Jupyter YAML.

    Returns:
        Extracted notebook metadata. Missing fields are returned as ``None``.
    """
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return NotebookMetadata()

    front_matter = yaml.safe_load(match.group(1)) or {}
    jupyter_meta = front_matter.get("jupyter", {}) or {}
    kernelspec = jupyter_meta.get("kernelspec", {}) or {}
    language_info = jupyter_meta.get("language_info", {}) or {}

    return NotebookMetadata(
        kernel_name=_string_or_none(kernelspec.get("name")),
        kernel_display_name=_string_or_none(kernelspec.get("display_name")),
        kernel_language=_string_or_none(
            kernelspec.get("language") or language_info.get("name")
        ),
    )


def extract_kernel_metadata_from_org(text: str) -> NotebookMetadata:
    """Extract kernel metadata from Org directives and header args.

    Args:
        text: Org notebook text.

    Returns:
        Extracted notebook metadata. Missing fields are returned as ``None``.
    """
    kernel_name = None
    kernel_display_name = None
    kernel_language = None

    kernel_name_match = ORG_KERNEL_NAME_RE.search(text)
    if kernel_name_match:
        kernel_name = kernel_name_match.group(1).strip()

    display_name_match = ORG_KERNEL_DISPLAY_NAME_RE.search(text)
    if display_name_match:
        kernel_display_name = display_name_match.group(1).strip()

    header_match = ORG_HEADER_ARGS_RE.search(text)
    if header_match:
        block_language = header_match.group(1).strip()
        header_args = header_match.group(2)
        if not kernel_name:
            kernel_match = re.search(r":kernel\s+(\S+)", header_args)
            if kernel_match:
                kernel_name = kernel_match.group(1).strip()
        if block_language.startswith("jupyter-"):
            kernel_language = block_language.removeprefix("jupyter-").strip() or None

    return NotebookMetadata(
        kernel_name=kernel_name,
        kernel_display_name=kernel_display_name,
        kernel_language=kernel_language,
    )


def patch_markdown_yaml_header(
    text: str,
    kernel_name: str | None,
    kernel_display_name: str | None,
    kernel_language: str | None = DEFAULT_KERNEL_LANGUAGE,
) -> str:
    """Insert or replace markdown YAML kernelspec metadata.

    Args:
        text: Markdown notebook text, expected to begin with YAML front matter.
        kernel_name: Kernel name to write into the header.
        kernel_display_name: Kernel display name to write into the header.
        kernel_language: Kernel language to write into the header.

    Returns:
        The patched markdown text. If no header or kernel name is available, the
        original text is returned unchanged.
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
        "language": normalize_kernel_language(kernel_language),
        "name": kernel_name,
    }

    new_front_matter = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{new_front_matter}\n---\n{text[match.end() :]}"


def build_org_header_args_property(
    block_language: str,
    kernel_name: str | None,
    session: str | None,
    use_async: bool,
    exports: str | None,
) -> str:
    """Build an Org header-args property line for notebook source blocks.

    Args:
        block_language: Org src block language, usually ``jupyter-...``.
        kernel_name: Kernel name to embed in the property.
        session: Optional Org-babel session name.
        use_async: Whether to add ``:async yes``.
        exports: Optional ``:exports`` value.

    Returns:
        A complete ``#+PROPERTY`` line.
    """
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


def insert_org_header_args_property(org_text: str, property_line: str | None) -> str:
    """Insert a header-args property near the top of an Org document.

    Args:
        org_text: Org document text.
        property_line: Property line to insert.

    Returns:
        The updated Org document text. If a matching header-args property already
        exists, the original text is returned unchanged.
    """
    if not property_line or ORG_HEADER_ARGS_RE.search(org_text):
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


def rewrite_source_block_language(
    text: str,
    source_language: str,
    target_language: str,
) -> str:
    """Rewrite Org source block language names in ``#+begin_src`` lines.

    Args:
        text: Org document text.
        source_language: Existing source block language to replace.
        target_language: Replacement source block language.

    Returns:
        Org text with matching block languages rewritten.
    """
    pattern = re.compile(ORG_BEGIN_SRC_RE_TEMPLATE.format(re.escape(source_language)))
    return pattern.sub(rf"\1{target_language}", text)


def _string_or_none(value: object) -> str | None:
    """Return a stripped string value or ``None`` for empty input."""
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value or None
