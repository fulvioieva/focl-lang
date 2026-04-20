"""Codebase analyzer: detects language/framework and collects source files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Files/dirs always ignored
_IGNORE_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".idea", ".vscode", "target", "build", "dist", ".gradle", ".mvn",
    "out", "bin", ".next", ".nuxt", "coverage", ".pytest_cache",
}
_IGNORE_EXTENSIONS = {
    ".class", ".jar", ".war", ".ear", ".zip", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".mp3", ".mp4", ".pdf", ".lock",
}
_MAX_FILE_BYTES = 200_000  # skip files larger than 200KB

# Language detection rules: (glob_pattern, language, framework)
_LANG_RULES: list[tuple[str, str, str | None]] = [
    ("pom.xml",            "java",       "spring-boot"),
    ("build.gradle",       "java",       "gradle"),
    ("build.gradle.kts",   "kotlin",     "gradle"),
    ("package.json",       "typescript", None),
    ("pyproject.toml",     "python",     None),
    ("setup.py",           "python",     None),
    ("requirements.txt",   "python",     None),
    ("go.mod",             "go",         None),
    ("Gemfile",            "ruby",       None),
    ("composer.json",      "php",        None),
    ("*.csproj",           "csharp",     None),
]

# Source extensions per language
_SOURCE_EXTENSIONS: dict[str, set[str]] = {
    "java":       {".java"},
    "kotlin":     {".kt", ".kts"},
    "typescript": {".ts", ".tsx", ".js", ".jsx"},
    "python":     {".py"},
    "go":         {".go"},
    "ruby":       {".rb"},
    "php":        {".php"},
    "csharp":     {".cs"},
}
_GENERIC_EXTENSIONS = {".java", ".kt", ".ts", ".tsx", ".js", ".jsx", ".py",
                        ".go", ".rb", ".php", ".cs", ".yaml", ".yml", ".xml",
                        ".json", ".properties", ".env.example", ".sql"}


@dataclass
class ProjectInfo:
    root: Path
    language: str
    framework: str | None
    files: list[Path] = field(default_factory=list)
    total_bytes: int = 0
    skipped_files: list[tuple[Path, str]] = field(default_factory=list)
    """Files excluded during collection, as (path, reason) tuples."""


def detect(root: Path) -> ProjectInfo:
    """Detect project language/framework and collect all source files."""
    language, framework = _detect_language(root)
    extensions = _SOURCE_EXTENSIONS.get(language, set()) | {
        ".yaml", ".yml", ".xml", ".properties", ".json", ".sql", ".env.example"
    }
    files, skipped = _collect_files(root, extensions)
    total_bytes = sum(f.stat().st_size for f in files if f.exists())
    return ProjectInfo(root=root, language=language, framework=framework,
                       files=files, total_bytes=total_bytes, skipped_files=skipped)


def _detect_language(root: Path) -> tuple[str, str | None]:
    for pattern, lang, fw in _LANG_RULES:
        if "*" in pattern:
            if any(root.rglob(pattern)):
                return lang, fw
        else:
            if (root / pattern).exists():
                # Refine Spring Boot detection
                if lang == "java" and fw == "spring-boot":
                    fw = _detect_spring_framework(root)
                return lang, fw
    return "unknown", None


def _detect_spring_framework(root: Path) -> str:
    pom = root / "pom.xml"
    if pom.exists():
        text = pom.read_text(errors="ignore")
        if "spring-boot" in text:
            return "spring-boot"
    return "java"


def _collect_files(root: Path, extensions: set[str]
                   ) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Collect source files under root, returning (included, skipped) lists.

    Skipped entries are (path, reason) tuples so callers can warn users.
    """
    result: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for fname in filenames:
            path = Path(dirpath) / fname
            if path.suffix.lower() in _IGNORE_EXTENSIONS:
                continue
            if path.suffix.lower() not in extensions and path.suffix.lower() not in _GENERIC_EXTENSIONS:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_BYTES:
                skipped.append((path, f"exceeds {_MAX_FILE_BYTES // 1024} KB limit ({size // 1024} KB)"))
                continue
            result.append(path)
    result.sort()
    return result, skipped


def build_context(info: ProjectInfo) -> str:
    """Concatenate all source files into a single context string."""
    parts: list[str] = []
    for f in info.files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = f.relative_to(info.root)
        parts.append(f"=== {rel} ===\n{content}")
    return "\n\n".join(parts)
