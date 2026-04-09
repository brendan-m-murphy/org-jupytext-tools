from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import (
    ConversionError,
    NotebookMetadata,
    build_org_header_args_property,
    ensure_pandoc_available,
    extract_kernel_metadata_from_markdown,
    infer_output_suffix,
    insert_org_header_args_property,
    is_markdown_like,
    make_jupyter_block_language,
    normalize_kernel_language,
    rewrite_source_block_language,
    run_checked,
    strip_html_anchor_lines,
    temporary_directory,
    temporary_text_file,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the Jupytext to Org converter.

    Args:
        argv: Optional argument list. When omitted, arguments are read from
            ``sys.argv``.

    Returns:
        The parsed argument namespace.
    """
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
    return parser.parse_args(argv)


def infer_output_path(input_path: Path) -> Path:
    """Infer the default Org output path for an input file."""
    return input_path.with_suffix(".org")


def prepare_markdown_input(
    input_path: Path,
    keep_html_anchors: bool,
) -> tuple[str, NotebookMetadata]:
    """Load markdown notebook text and extract any embedded kernel metadata.

    Args:
        input_path: Markdown-like notebook path.
        keep_html_anchors: Whether to preserve raw HTML anchor lines.

    Returns:
        The cleaned markdown text and extracted notebook metadata.
    """
    text = input_path.read_text(encoding="utf-8")
    metadata = extract_kernel_metadata_from_markdown(text)
    if not keep_html_anchors:
        text = strip_html_anchor_lines(text)
    return text, metadata


def convert_with_jupytext_to_markdown(input_path: Path, temp_md: Path) -> str:
    """Normalize a notebook source into temporary ``md:pandoc`` text.

    Args:
        input_path: Notebook source path readable by Jupytext.
        temp_md: Destination path for the temporary markdown notebook.

    Returns:
        The generated markdown text.
    """
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
    """Convert markdown notebook text into Org using Pandoc.

    Args:
        markdown_text: Markdown notebook text to convert.
        output_path: Destination path for the Org output.
    """
    with temporary_text_file(markdown_text, suffix=".md") as temp_md_path:
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


def postprocess_org_output(
    output_path: Path,
    kernel_name: str | None,
    kernel_language: str | None,
    session: str | None,
    use_async: bool,
    exports: str | None,
    keep_source_language: bool,
) -> None:
    """Insert Org header args and optionally rewrite source block languages.

    Args:
        output_path: Org output path to update in place.
        kernel_name: Kernel name for the header args property.
        kernel_language: Kernel language used for block rewriting.
        session: Optional Org-babel session name.
        use_async: Whether to add ``:async yes`` to the property.
        exports: Optional ``:exports`` value for the property.
        keep_source_language: Whether to keep the original source block language.
    """
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
    org_text = insert_org_header_args_property(org_text, property_line)

    if not keep_source_language:
        org_text = rewrite_source_block_language(
            org_text,
            source_language=normalized_language,
            target_language=jupyter_block_language,
        )

    output_path.write_text(org_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the Jupytext to Org conversion command.

    Args:
        argv: Optional argument list. When omitted, arguments are read from
            ``sys.argv``.

    Returns:
        Exit status code ``0`` on success.

    Raises:
        ConversionError: Input validation fails or an external tool command fails.
    """
    args = parse_args(argv)

    input_path = args.input_path.expanduser().resolve()
    if not input_path.exists():
        raise ConversionError(f"Input file does not exist: {input_path}")

    ensure_pandoc_available()

    output_path = (args.output or infer_output_path(input_path)).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if is_markdown_like(input_path):
        markdown_text, metadata = prepare_markdown_input(
            input_path=input_path,
            keep_html_anchors=args.keep_html_anchors,
        )
    else:
        with temporary_directory(prefix="jpy-org-") as temp_dir:
            temp_md = temp_dir / f"{input_path.stem}{infer_output_suffix('md:pandoc')}"
            markdown_text = convert_with_jupytext_to_markdown(input_path, temp_md)
            metadata = extract_kernel_metadata_from_markdown(markdown_text)
            if not args.keep_html_anchors:
                markdown_text = strip_html_anchor_lines(markdown_text)

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
