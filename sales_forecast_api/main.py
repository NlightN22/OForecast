from __future__ import annotations

import time

from config import INPUT_FILE, OUTPUT_FILE
from parser import ExcelParser
from transformer import SalesApiTransformer
from api_client import ForecastApiClient, ForecastApiError
from excel_writer import ExcelWriter


def main() -> None:
    started_at = time.perf_counter()

    parser = ExcelParser()
    transformer = SalesApiTransformer()
    client = ForecastApiClient()
    writer = ExcelWriter()

    print("Reading Excel...")
    dataframe = parser.read(INPUT_FILE)

    print("Preparing API data...")
    rows = transformer.run(dataframe)

    if not rows:
        raise ValueError("No data found to send to the API.")

    print(f"Forecast tasks: {len(rows)}")

    results = []

    for index, item in enumerate(rows, start=1):
        print(
            f"[{index}/{len(rows)}] "
            f"{item.forecast_level} / {item.manager} / {item.brand}"
        )

        try:
            response = client.forecast(item.raw)
        except ForecastApiError as exc:
            response = {
                "intervals": [{"point": None}],
                "next_period": "",
                "chosen_model": "",
                "chosen_dataset": "",
                "rows_in": None,
                "status": "error",
                "error": str(exc),
            }

        results.append(
            {
                "forecast_level": item.forecast_level,
                "manager": item.manager,
                "brand": item.brand,
                "response": response,
            }
        )

    print("Saving Excel...")

    writer.save(
        results=results,
        filename=OUTPUT_FILE,
    )

    elapsed = time.perf_counter() - started_at

    print(f"Done: {OUTPUT_FILE}")
    print(f"Runtime: {elapsed:.2f} sec.")


if __name__ == "__main__":
    main()
