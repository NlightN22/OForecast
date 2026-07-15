"""
Application entry point.

Execution flow:

1. Read Excel
2. Transform data
3. Calculate forecast
4. Save the result
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
            f"File not found:\n{INPUT_FILE}"
        )

    print("Reading Excel...")

    parser = ExcelParser()

    raw_df = parser.read(
        INPUT_FILE
    )

    print(
        f"Rows: {len(raw_df)}"
    )

    print("Transforming data...")

    transformer = SalesTransformer()

    forecast_df = transformer.run(
        raw_df
    )

    print(
        f"Series prepared: {forecast_df['unique_id'].nunique()}"
    )

    print("Calculating forecast...")

    adapter = OForecastAdapter()

    result = adapter.forecast(
        forecast_df
    )

    print("Saving Excel...")

    writer = ExcelWriter()

    writer.save(
        result=result,
        filename=OUTPUT_FILE,
    )

    elapsed = time.perf_counter() - start

    print("-" * 60)

    print("Done.")

    print(
        f"Runtime: {elapsed:.2f} sec."
    )

    print(
        f"File saved:\n{OUTPUT_FILE}"
    )

    print("-" * 60)


if __name__ == "__main__":

    main()
