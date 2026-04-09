from __future__ import annotations

from org_jupytext_tools.common import (
    extract_kernel_metadata_from_markdown,
    extract_kernel_metadata_from_org,
    patch_markdown_yaml_header,
    rewrite_source_block_language,
    strip_html_anchor_lines,
    strip_org_targets,
)


def test_strip_org_targets_removes_only_standalone_targets() -> None:
    """Remove standalone Org targets without touching inline target text."""
    text = "<<drop-me>>\nParagraph with <<keep-inline>> target.\n\n<<drop-too>>\n"

    result = strip_org_targets(text)

    assert "<<drop-me>>" not in result
    assert "<<drop-too>>" not in result
    assert "Paragraph with <<keep-inline>> target." in result


def test_strip_html_anchor_lines_removes_raw_anchor_blocks() -> None:
    """Drop raw HTML anchor lines and the following blank line."""
    text = '`<span id="abc"></span>`{=html}\n\n# Heading\n'

    result = strip_html_anchor_lines(text)

    assert result == "# Heading\n"


def test_extract_kernel_metadata_from_markdown_reads_jupyter_yaml() -> None:
    """Read kernelspec metadata from markdown front matter."""
    text = """---
jupyter:
  kernelspec:
    display_name: Python 3
    language: python
    name: python3
  language_info:
    name: python
---

# Title
"""

    metadata = extract_kernel_metadata_from_markdown(text)

    assert metadata.kernel_name == "python3"
    assert metadata.kernel_display_name == "Python 3"
    assert metadata.kernel_language == "python"


def test_extract_kernel_metadata_from_org_reads_directives_and_header_args() -> None:
    """Read Org kernel directives and jupyter header args."""
    text = """#+TITLE: Demo
#+JUPYTER_KERNEL_DISPLAY_NAME: Python 3
#+PROPERTY: header-args:jupyter-python :kernel python3 :session python3
"""

    metadata = extract_kernel_metadata_from_org(text)

    assert metadata.kernel_name == "python3"
    assert metadata.kernel_display_name == "Python 3"
    assert metadata.kernel_language == "python"


def test_patch_markdown_yaml_header_replaces_kernelspec() -> None:
    """Patch the markdown YAML header with a kernelspec block."""
    text = """---
jupyter:
  jupytext:
    formats: md:pandoc
---

# Title
"""

    result = patch_markdown_yaml_header(text, "python3", "Python 3")

    assert "name: python3" in result
    assert "display_name: Python 3" in result
    assert "language: python" in result


def test_rewrite_source_block_language_rewrites_matching_blocks_only() -> None:
    """Rewrite only the requested Org source block language."""
    text = """#+begin_src python
print("hello")
#+end_src

#+begin_src bash
echo hello
#+end_src
"""

    result = rewrite_source_block_language(text, "python", "jupyter-python")

    assert "#+begin_src jupyter-python" in result
    assert "#+begin_src bash" in result
