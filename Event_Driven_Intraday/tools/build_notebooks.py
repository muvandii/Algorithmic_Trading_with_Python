"""Build (and optionally execute) the lesson notebooks from ``tools/lessons``.

Usage, from ``Event_Driven_Intraday/``:

    python tools/build_notebooks.py            # build + execute + save outputs
    python tools/build_notebooks.py --no-exec  # build only (fast, no outputs)

Why generate notebooks from Python files? Diff-ability and reproducibility:
markdown/code live as plain text, the generated .ipynb is a build artifact you
can always recreate. Same spirit as the rest of the module.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from lessons import MODULES  # noqa: E402


def to_nbformat(nb) -> nbformat.NotebookNode:
    """Convert our Notebook dataclass into a valid nbformat v4 document."""
    out = nbformat.v4.new_notebook()
    out.metadata.update(
        {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.9+"},
            "title": nb.title,
        }
    )
    for kind, text in nb.cells:
        out.cells.append(nbformat.v4.new_markdown_cell(text) if kind == "markdown" else nbformat.v4.new_code_cell(text))
    return out


def execute(nb, timeout: int = 600):
    """Run the notebook in-place so saved outputs are real, not aspirational."""
    client = NotebookClient(nb, timeout=timeout, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
    client.execute()
    return nb


def main() -> None:
    """Build every lesson module into ``notebooks/``."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-exec", action="store_true", help="build without executing")
    parser.add_argument("--only", default=None, help="build a single module, e.g. lesson1")
    args = parser.parse_args()

    out_dir = ROOT / "notebooks"
    out_dir.mkdir(exist_ok=True)

    for module in MODULES:
        if args.only and module.__name__.split(".")[-1] != args.only:
            continue
        nb = module.build()
        doc = to_nbformat(nb)
        path = out_dir / module.FILENAME
        if not args.no_exec:
            print(f"executing {path.name} ...", flush=True)
            doc = execute(doc)
        nbformat.write(doc, path)
        print(f"wrote {path}  ({len(doc.cells)} cells)")


if __name__ == "__main__":
    main()
