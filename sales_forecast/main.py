"""
Точка входа.

Последовательность:

1. Чтение Excel
2. Преобразование данных
3. Расчет прогноза
4. Сохранение результата
"""

from pathlib import Path
import time

try:
    from .config import (
        INPUT_FILE,
        OUTPUT_FILE,
    )
    from .parser import ExcelParser
    from .transformer import SalesTransformer
    from .adapter import OForecastAdapter
    from .excel_writer import ExcelWriter
except ImportError:  # pragma: no cover - script execution fallback
    from config import (
        INPUT_FILE,
        OUTPUT_FILE,
    )
    from parser import ExcelParser
    from transformer import SalesTransformer
    from adapter import OForecastAdapter
    from excel_writer import ExcelWriter


def main():

    start = time.perf_counter()

    print("-" * 60)
    print("Sales Forecast")
    print("-" * 60)

    if not Path(INPUT_FILE).exists():

        raise FileNotFoundError(
            f"Файл не найден:\n{INPUT_FILE}"
        )

    print("Чтение Excel...")

    parser = ExcelParser()

    raw_df = parser.read(
        INPUT_FILE
    )

    print(
        f"Строк: {len(raw_df)}"
    )

    print("Преобразование данных...")

    transformer = SalesTransformer()

    forecast_df = transformer.run(
        raw_df
    )

    print(
        f"Получено рядов: {forecast_df['unique_id'].nunique()}"
    )

    print("Расчет прогноза...")

    adapter = OForecastAdapter()

    result = adapter.forecast(
        forecast_df
    )

    print("Сохранение Excel...")

    writer = ExcelWriter()

    writer.save(
        result=result,
        filename=OUTPUT_FILE,
    )

    elapsed = time.perf_counter() - start

    print("-" * 60)

    print("Готово.")

    print(
        f"Время выполнения: {elapsed:.2f} сек."
    )

    print(
        f"Файл сохранен:\n{OUTPUT_FILE}"
    )

    print("-" * 60)


if __name__ == "__main__":

    main()
