# org-jupytext-tools

Small CLI tools for converting between Org notebooks and Jupytext notebook formats.

## Installation

`pandoc` is required as an external dependency. The Python package depends on `jupytext` and `PyYAML`, but Pandoc must be installed separately and available on `PATH`.

Install from GitHub with `uv`:

```bash
uv tool install git+https://github.com/brendan-m-murphy/org-jupytext-tools
```

## Usage

Convert Org to Jupytext markdown by default:

```bash
org2jpy notebook.org
```

Choose a different final Jupytext format:

```bash
org2jpy notebook.org --output-format py:percent
```

Also keep the intermediate notebook as a final `.ipynb`:

```bash
org2jpy notebook.org --write-ipynb
```

Convert a notebook or Jupytext text file to Org:

```bash
jpy2org notebook.ipynb
jpy2org notebook.md
```

`jpy2org` adds an Org header-args property for `emacs-jupyter` and rewrites source blocks like `python` to `jupyter-python` by default.

## Expected Normalizations

These tools keep the conversion flow simple and explicit, so some formatting changes are expected:

- Jupyter cell IDs are not preserved across round trips.
- Adjacent markdown cells may be merged after Org conversion.
- Markdown line wrapping may differ after a round trip.
- Raw HTML anchor lines generated from Org targets are stripped by default.

