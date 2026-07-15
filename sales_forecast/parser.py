"""
Excel file reader.

The parser does not contain data transformation logic.
Its only job is to load an Excel sheet into a DataFrame.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class ExcelParser:

    def __init__(
        self,
        sheet_name=0,
    ):

        self.sheet_name = sheet_name

    # ------------------------------------------------------------------

    def read(
        self,
        filename: str | Path,
    ) -> pd.DataFrame:
        """
        Read an Excel file.

        Parameters
        ----------
        filename
            Path to the Excel file.

        Returns
        -------
        pandas.DataFrame
        """

        filename = Path(filename)

        if not filename.exists():

            raise FileNotFoundError(
                f"File not found:\n{filename}"
            )

        try:

            dataframe = pd.read_excel(
                filename,
                sheet_name=self.sheet_name,
                header=None,
                engine="openpyxl",
            )

        except Exception as exc:

            raise RuntimeError(
                f"Excel read error:\n{exc}"
            ) from exc

        if dataframe.empty:

            raise ValueError(
                "Excel file is empty."
            )

        return dataframe

    # ------------------------------------------------------------------

    @staticmethod
    def sheet_names(
        filename: str | Path,
    ) -> list[str]:
        """
        Return workbook sheet names.
        """

        filename = Path(filename)

        if not filename.exists():

            raise FileNotFoundError(filename)

        excel = pd.ExcelFile(
            filename,
            engine="openpyxl",
        )

        return list(excel.sheet_names)

    # ------------------------------------------------------------------

    @staticmethod
    def read_sheet(
        filename: str | Path,
        sheet_name: str,
    ) -> pd.DataFrame:
        """
        Read a specific workbook sheet.
        """

        filename = Path(filename)

        return pd.read_excel(
            filename,
            sheet_name=sheet_name,
            header=None,
            engine="openpyxl",
        )
