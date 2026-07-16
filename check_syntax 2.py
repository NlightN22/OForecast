import pathlib
import py_compile

bad = []
for f in pathlib.Path(".").rglob("*.py"):
    try:
        py_compile.compile(str(f), doraise=True)
    except Exception as e:
        bad.append((str(f), str(e)))

if bad:
    print("Syntax errors:")
    for f, e in bad:
        print(f" - {f}\n   {e}")
    raise SystemExit(1)

print("OK: syntax is valid for all .py files")
