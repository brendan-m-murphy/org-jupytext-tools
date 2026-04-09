from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .common import (
    ConversionError,
    DEFAULT_OUTPUT_FORMAT,
    ensure_pandoc_available,
    extract_kernel_metadata_from_org,
    infer_jupytext_output_path,
    is_markdown_output,
    patch_markdown_yaml_header,
    run_checked,
    strip_html_anchor_lines,
    strip_org_targets,
    temporary_directory,
    temporary_text_file,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the Org to Jupytext converter.

    Args:
        argv: Optional argument list. When omitted, arguments are read from
            ``sys.argv``.

    Returns:
        The parsed argument namespace.
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
    return parser.parse_args(argv)


def convert_org_to_ipynb(input_org_text: str, temp_ipynb: Path) -> None:
    """Convert Org text to a temporary notebook with Pandoc.

    Args:
        input_org_text: Org document text to convert.
        temp_ipynb: Destination path for the temporary notebook.
    """
    with temporary_text_file(input_org_text, suffix=".org") as temp_org_path:
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


def convert_ipynb_with_jupytext(
    temp_ipynb: Path, output_path: Path, output_format: str
) -> None:
    """Convert a notebook file into the requested Jupytext output format.

    Args:
        temp_ipynb: Source notebook path.
        output_path: Destination path for the converted output.
        output_format: Jupytext output format such as ``md:pandoc``.
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


def postprocess_output(
    output_path: Path,
    output_format: str,
    kernel_name: str | None,
    kernel_display_name: str | None,
    keep_html_anchors: bool,
) -> None:
    """Patch markdown kernelspec metadata and strip generated anchors.

    Args:
        output_path: Final output file to update in place.
        output_format: Requested Jupytext output format.
        kernel_name: Kernel name to inject into markdown YAML.
        kernel_display_name: Kernel display name to inject into markdown YAML.
        keep_html_anchors: Whether to preserve raw HTML anchor lines.
    """
    if not is_markdown_output(output_path, output_format):
        return

    text = output_path.read_text(encoding="utf-8")
    text = patch_markdown_yaml_header(text, kernel_name, kernel_display_name)
    if not keep_html_anchors:
        text = strip_html_anchor_lines(text)
    output_path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the Org to Jupytext conversion command.

    Args:
        argv: Optional argument list. When omitted, arguments are read from
            ``sys.argv``.

    Returns:
        Exit status code ``0`` on success.

    Raises:
        ConversionError: Input validation fails or an external tool command fails.
    """
    args = parse_args(argv)

    input_org = args.input_org.expanduser().resolve()
    if not input_org.exists():
        raise ConversionError(f"Input file does not exist: {input_org}")
    if input_org.suffix.lower() != ".org":
        raise ConversionError(f"Input file is not an .org file: {input_org}")

    ensure_pandoc_available()

    org_text = input_org.read_text(encoding="utf-8")
    metadata = extract_kernel_metadata_from_org(org_text)
    kernel_name = args.kernel_name or metadata.kernel_name
    kernel_display_name = (
        args.kernel_display_name or metadata.kernel_display_name or kernel_name
    )

    temp_org_text = org_text if args.keep_org_targets else strip_org_targets(org_text)

    output_path = (
        args.output or infer_jupytext_output_path(input_org, args.output_format)
    ).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    write_ipynb = args.write_ipynb or args.ipynb_output is not None
    ipynb_output = (
        args.ipynb_output.expanduser()
        if args.ipynb_output is not None
        else output_path.with_suffix(".ipynb")
    )

    with temporary_directory(prefix="org-jupytext-") as temp_dir:
        temp_ipynb = temp_dir / f"{input_org.stem}.ipynb"
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
