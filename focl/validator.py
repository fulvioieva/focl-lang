"""Validate the structure of a ``.focl`` file — offline, no API call.

The FOCL grammar is intentionally open (LLM-generated and evolving), so this
checks only things that are *reliably* wrong rather than enforcing a rigid
schema:

- **errors** (definite defects, fail CI): empty file, markdown code fences,
  a ``# src:`` annotation with no path, and empty blocks.
- **warnings** (advisory): no ``# src:`` annotations at all (breaks MCP lookup
  and surgical update), and duplicate ``# src:`` paths.

It also returns light stats (module count, lines, a histogram of the known
primitives used).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from . import index

# The primitive vocabulary from the generator's system prompt / README.
_KNOWN_PRIMITIVES = (
    "OWNED_FETCH", "TRANSITION", "SILENT_GUARD", "PAGE", "PRESIGN_URL",
    "PATCH", "PARSE_ENUM", "OTP_FLOW", "ISSUE_SESSION", "PERSIST", "NOTIFY",
    "MAP", "INJECT", "UPLOAD", "ENTITY", "FILTER_",
)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _raw_src_paths(content: str) -> list[str]:
    """All ``# src:`` paths in order, including duplicates."""
    paths: list[str] = []
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("# src:"):
            rest = s[len("# src:"):].strip()
            if rest:
                paths.append(rest)
    return paths


def _primitive_histogram(content: str) -> dict[str, int]:
    hist: dict[str, int] = {}
    for prim in _KNOWN_PRIMITIVES:
        pattern = rf"\b{re.escape(prim)}\w*" if prim.endswith("_") else rf"\b{re.escape(prim)}\b"
        n = len(re.findall(pattern, content))
        if n:
            hist[prim.rstrip("_") + ("*" if prim.endswith("_") else "")] = n
    return hist


def validate(content: str) -> ValidationResult:
    """Validate ``.focl`` text and return errors, warnings, and stats."""
    res = ValidationResult()

    if not content.strip():
        res.errors.append("File is empty.")
        return res

    if "```" in content:
        res.errors.append(
            "Contains markdown code fences (```) — a .focl file must be plain text."
        )

    if any(
        line.strip() == "# src:" or
        (line.strip().startswith("# src:") and not line.strip()[len("# src:"):].strip())
        for line in content.splitlines()
    ):
        res.errors.append("Found a `# src:` annotation with no path.")

    paths = index.module_paths(content)
    blocks = index.parse_focl_blocks(content)

    if not paths:
        res.warnings.append(
            "No `# src:` annotations — MCP module lookup and surgical update "
            "won't work. Regenerate with a newer focl, or use `focl sync`."
        )

    dups = sorted(p for p, c in Counter(_raw_src_paths(content)).items() if c > 1)
    if dups:
        res.warnings.append(f"Duplicate `# src:` paths: {', '.join(dups)}.")

    for path, block in blocks.items():
        body = [
            ln for ln in block.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if not body:
            res.errors.append(f"Empty FOCL block for `{path}`.")

    res.stats = {
        "modules": len(paths),
        "lines": len(content.splitlines()),
        "primitives": _primitive_histogram(content),
    }
    return res
