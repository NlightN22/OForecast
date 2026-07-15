from __future__ import annotations

from pathlib import Path

import pandas as pd


class ExcelParser:
    def __init__(self, sheet_name=0):
        self.sheet_name = sheet_name

    def read(self, filename: str | Path) -> pd.DataFrame:
        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        try:
            df = pd.read_excel(
                path,
                sheet_name=self.sheet_name,
                header=None,
                engine="openpyxl",
            )

        except Exception as exc:
            raise RuntimeError(f"Excel read error: {exc}") from exc

        if df.empty:
            raise ValueError("Excel file is empty.")

        return df
