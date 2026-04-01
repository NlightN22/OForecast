from __future__ import annotations

from ..core.service import run_forecast, format_result_text

def main():
    # Paste your raw text here or load from file
    raw = open("data.txt", "r", encoding="utf-8").read()
    result = run_forecast(raw)
    print(format_result_text(result))

if __name__ == "__main__":
    main()
