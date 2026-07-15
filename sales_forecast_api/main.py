from __future__ import annotations

import time

from config import INPUT_FILE, OUTPUT_FILE
from parser import ExcelParser
from transformer import SalesApiTransformer
from api_client import ForecastApiClient
from excel_writer import ExcelWriter


def main() -> None:
    started_at = time.perf_counter()

    parser = ExcelParser()
    transformer = SalesApiTransformer()
    client = ForecastApiClient()
    writer = ExcelWriter()

    print("Чтение Excel...")
    dataframe = parser.read(INPUT_FILE)

    print("Формирование данных для API...")
    rows = transformer.run(dataframe)

    if not rows:
        raise ValueError("Не найдено данных для отправки в API.")

    print(f"Задач прогноза: {len(rows)}")

    results = []

    for index, item in enumerate(rows, start=1):
        print(
            f"[{index}/{len(rows)}] "
            f"{item.forecast_level} / {item.manager} / {item.brand}"
        )

        response = client.forecast(item.raw)

        results.append(
            {
                "forecast_level": item.forecast_level,
                "manager": item.manager,
                "brand": item.brand,
                "response": response,
            }
        )

    print("Сохранение Excel...")

    writer.save(
        results=results,
        filename=OUTPUT_FILE,
    )

    elapsed = time.perf_counter() - started_at

    print(f"Готово: {OUTPUT_FILE}")
    print(f"Время работы: {elapsed:.2f} сек.")


if __name__ == "__main__":
    main()
