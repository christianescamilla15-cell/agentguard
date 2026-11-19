"""Golden file for the shipped example and the README (parity against an independent oracle).

The decisions printed by examples/llm_tool_call_guard.py are pinned in tests/golden/. The README
shows the same block as "Output:", so the documentation cannot drift from what the code does
(it did: the README promised a 4th ALLOW that the 3-per-window rate limit correctly denies).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DORADO = RAIZ / "tests" / "golden" / "llm_tool_call_guard.txt"


def _decisiones(texto: str) -> list[str]:
    return [linea.strip() for linea in texto.splitlines() if linea.strip()[:1] in ("✓", "✗")]


def test_example_decisions_match_the_golden_file():
    salida = subprocess.run([sys.executable, str(RAIZ / "examples" / "llm_tool_call_guard.py")],
                            capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert _decisiones(salida) == _decisiones(DORADO.read_text(encoding="utf-8"))


def test_readme_output_block_matches_the_golden_file():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    bloque = re.search(r"Output:\n```\n(.*?)```", readme, re.S)
    assert bloque, "README lost its Output: block"
    assert _decisiones(bloque.group(1)) == _decisiones(DORADO.read_text(encoding="utf-8"))
