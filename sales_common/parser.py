from __future__ import annotations

from pathlib import Path

import pandas as pd


class ExcelParser:
    def __init__(self, sheet_name=0):
        self.sheet_name = sheet_name

    def read(self, filename: str | Path) -> pd.DataFrame:
        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(f"File not found:\n{path}")

        try:
            dataframe = pd.read_excel(
                path,
                sheet_name=self.sheet_name,
                header=None,
                engine="openpyxl",
            )
        except Exception as exc:
            raise RuntimeError(f"Excel read error:\n{exc}") from exc

        if dataframe.empty:
            raise ValueError("Excel file is empty.")

        return dataframe

    @staticmethod
    def sheet_names(filename: str | Path) -> list[str]:
        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        excel = pd.ExcelFile(path, engine="openpyxl")
        return list(excel.sheet_names)

    @staticmethod
    def read_sheet(filename: str | Path, sheet_name: str) -> pd.DataFrame:
        return pd.read_excel(
            Path(filename),
            sheet_name=sheet_name,
            header=None,
            engine="openpyxl",
        )
