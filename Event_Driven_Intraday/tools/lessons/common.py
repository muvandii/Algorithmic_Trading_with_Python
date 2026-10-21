"""Tiny notebook authoring helper (markdown + code cells, then nbformat)."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import List, Tuple

SETUP = """
# --- environment setup (run me first) -------------------------------------
import sys, os, textwrap, json, tempfile
from pathlib import Path

import numpy as np
import pandas as pd

# The notebooks live in <module>/notebooks; the package lives in <module>/.
BASE = next(p for p in (Path.cwd(), Path.cwd().parent) if (p / "intraday_engine").is_dir())
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

DATA = BASE / "data"
pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 30)
pd.set_option("display.float_format", lambda x: f"{x:,.4f}")

from intraday_engine import *          # noqa: F401,F403
from intraday_engine.core import Fill  # noqa: F401

print("module root :", BASE)
print("pandas      :", pd.__version__, "| numpy:", np.__version__)
print("data files  :", sorted(p.name for p in DATA.glob("*.csv")))
"""


@dataclass
class Notebook:
    """Collect cells, then hand them to nbformat in the build script."""

    title: str
    cells: List[Tuple[str, str]] = field(default_factory=list)

    def md(self, text: str) -> None:
        """Add a markdown cell (dedented, leading/trailing blank lines removed)."""
        self.cells.append(("markdown", textwrap.dedent(text).strip("\n")))

    def code(self, text: str) -> None:
        """Add a code cell (dedented, leading/trailing blank lines removed)."""
        self.cells.append(("code", textwrap.dedent(text).strip("\n")))

    def setup(self) -> None:
        """Add the shared environment cell right after the title."""
        self.code(SETUP)


def header(n: int, title: str, subtitle: str) -> str:
    """Consistent notebook title block."""
    return f"# Lesson {n} — {title}\n\n**{subtitle}**\n\n---"


def section(n: int, title: str) -> str:
    """Consistent section heading with the numbering required by the syllabus."""
    return f"## {n}. {title}"


def note(text: str, kind: str = "Coach's note") -> str:
    """Call-out block."""
    return f"> **{kind}.** {text}"
