import ast
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "output",
    "venv",
}


def iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


bad = []
for file_path in iter_python_files(Path(".")):
    try:
        ast.parse(file_path.read_text(encoding="utf-8-sig"), filename=str(file_path))
    except Exception as exc:
        bad.append((str(file_path), str(exc)))

if bad:
    print("Syntax errors:")
    for file_path, error in bad:
        print(f" - {file_path}\n   {error}")
    raise SystemExit(1)

print("OK: syntax is valid for project .py files")
