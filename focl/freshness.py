"""Per-module freshness of a ``.focl`` map, offline (no API call).

Each ``# src:`` line can carry a short content hash of the source file its
block was generated from::

    # src: services/UserService.java @h:1a2b3c4d5e6f

The generator stamps these right after compressing (all blocks on a full
``generate()``, only the regenerated blocks on a surgical ``update()``), so a
stamp always describes the source the block actually reflects. Comparing them
with the files on disk tells, per module, whether the map can be trusted —
unlike mtimes, this survives ``git clone``/``checkout`` and line-ending
conversion (CRLF is normalised before hashing).

Used by ``focl check`` and by the MCP server to flag stale modules.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from . import index

_HASH_LEN = 12

# Module states returned by module_status().
FRESH = "fresh"
CHANGED = "changed"
DELETED = "deleted"
UNVERIFIED = "unverified"  # block has no stamp (older focl) — can't tell

_cache: dict[tuple[str, int, int], str] = {}


def file_hash(path: Path) -> str:
    """Short, line-ending-insensitive content hash of ``path``.

    Cached on (path, mtime_ns, size) so repeated MCP calls stay cheap.
    """
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    data = path.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()[:_HASH_LEN]
    _cache[key] = digest
    return digest


def resolve_source(root: Path, rel: str) -> Path | None:
    """The file ``rel`` (as written in a ``# src:`` line) under ``root``.

    Returns None when it doesn't exist or would escape ``root``.
    """
    candidate = root / rel.replace("\\", "/")
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def stamp_block(block: str, rel: str, digest: str) -> str:
    """Force ``block``'s leading ``# src:`` line to ``rel`` stamped with ``digest``.

    Adds the marker if the block has none, so a regenerated block always keys
    back to the file it was generated from.
    """
    marker = index.format_src(rel, digest)
    lines = block.lstrip("\n").splitlines(keepends=True)
    if lines and index.split_src(lines[0])[0] is not None:
        eol = lines[0][len(lines[0].rstrip("\r\n")):]
        lines[0] = marker + (eol or "\n")
        return "".join(lines)
    return marker + "\n" + "".join(lines)


def stamp(content: str, root: Path) -> str:
    """Stamp every ``# src:`` line whose file exists under ``root``.

    Only call this right after the whole map was generated from the current
    sources — stamping asserts "this block reflects the file as it is now".
    Lines pointing at unknown files are left untouched.
    """
    out: list[str] = []
    for line in content.splitlines(keepends=True):
        path = index.split_src(line)[0]
        if path is not None:
            src = resolve_source(root, path)
            if src is not None:
                indent = line[:len(line) - len(line.lstrip())]
                eol = line[len(line.rstrip("\r\n")):]
                line = indent + index.format_src(path, file_hash(src)) + eol
        out.append(line)
    return "".join(out)


def module_status(content: str, root: Path,
                  paths: list[str] | None = None) -> dict[str, str]:
    """Map source paths in the map to FRESH / CHANGED / DELETED / UNVERIFIED.

    ``paths`` limits the check to those modules (default: all of them).
    """
    hashes = index.module_hashes(content)
    wanted = hashes if paths is None else {p: hashes.get(p) for p in paths if p in hashes}
    status: dict[str, str] = {}
    for path, digest in wanted.items():
        if digest is None:
            status[path] = UNVERIFIED
            continue
        src = resolve_source(root, path)
        if src is None:
            status[path] = DELETED
        elif file_hash(src) != digest:
            status[path] = CHANGED
        else:
            status[path] = FRESH
    return status


@dataclass
class FreshnessReport:
    changed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    fresh: int = 0

    @property
    def tracked(self) -> bool:
        """True when the map carries stamps, i.e. per-module tracking works."""
        return bool(self.fresh or self.changed or self.deleted)

    @property
    def stale(self) -> bool:
        return bool(self.changed or self.deleted or self.added)

    @property
    def stale_paths(self) -> list[str]:
        """Paths an incremental update would need to regenerate or drop."""
        return self.changed + self.deleted + self.added


def check(content: str, root: Path, sources: list[Path],
          focl_mtime: float | None = None,
          exclude: Path | None = None) -> FreshnessReport:
    """Compare a map against the current sources.

    ``added`` lists source files with no block in the map that were modified
    after the map was written (``focl_mtime``). The generator legitimately
    omits trivial files, so un-mapped files that predate the map are not
    reported — otherwise they would show up as "new" forever.
    """
    report = FreshnessReport()
    for path, st in module_status(content, root).items():
        if st == FRESH:
            report.fresh += 1
        elif st == CHANGED:
            report.changed.append(path)
        elif st == DELETED:
            report.deleted.append(path)
        else:
            report.unverified.append(path)

    covered = {p.replace("\\", "/") for p in index.module_paths(content)}
    excl = exclude.resolve() if exclude else None
    for f in sources:
        try:
            if excl is not None and f.resolve() == excl:
                continue
            rel = f.relative_to(root).as_posix()
            if rel in covered:
                continue
            if focl_mtime is not None and f.stat().st_mtime <= focl_mtime:
                continue
        except (OSError, ValueError):
            continue
        report.added.append(rel)
    return report
