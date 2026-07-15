"""
Чтение Excel-файла.

Парсер не содержит никакой логики обработки данных.
Его задача — только загрузить лист Excel в DataFrame.
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
        Читает Excel-файл.

        Parameters
        ----------
        filename
            Путь к Excel-файлу.

        Returns
        -------
        pandas.DataFrame
        """

        filename = Path(filename)

        if not filename.exists():

            raise FileNotFoundError(
                f"Файл не найден:\n{filename}"
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
                f"Ошибка чтения Excel:\n{exc}"
            ) from exc

        if dataframe.empty:

            raise ValueError(
                "Excel-файл пуст."
            )

        return dataframe

    # ------------------------------------------------------------------

    @staticmethod
    def sheet_names(
        filename: str | Path,
    ) -> list[str]:
        """
        Возвращает список листов книги.
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
        Читает указанный лист книги.
        """

        filename = Path(filename)

        return pd.read_excel(
            filename,
            sheet_name=sheet_name,
            header=None,
            engine="openpyxl",
        )