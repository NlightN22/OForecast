# OForecast Sales Forecast

## Overview

The sales forecast workflow predicts monthly brand sales by employee and for the
company as a whole. It has two entry points:

- `sales_forecast` - runs the local `ts_forecast` engine directly.
- `sales_forecast_api` - sends forecast tasks to a remote OForecast API.

Both applications read the same sales workbook and generate two report sheets:

- `Brand Totals` - total forecast for each brand.
- `Employee Forecasts` - forecast for every employee and brand combination.

`TBATS_y` is disabled in both workflows because it significantly increases the
calculation time without improving the selected forecasts for the current data.

## Input Workbook

The real sales workbook should be named `Sales.xlsx`. It may contain sensitive
commercial data and should not be committed to Git.

Place a copy of `Sales.xlsx` in the application directory you want to run:

- Local: `sales_forecast/Sales.xlsx`
- API: `sales_forecast_api/Sales.xlsx`

The repository includes `sales_forecast/sales_example.xlsx` with synthetic
data. Use it as a layout reference or copy it to one of the application
directories and rename it to `Sales.xlsx` for a test run.

The default workbook layout is configured as follows:

- The first worksheet is used.
- Row 8 contains brand names, starting from column C.
- Row 9 is ignored by the current parser and may stay blank.
- Column B contains employee names and month labels.
- Employee names appear as section rows in column B, starting from row 10.
- Monthly rows follow each employee row.
- Sales values are placed at the intersection of a monthly row and a brand
  column.
- The expected month label format is a localized month name plus year, for
  example `January 2026` or another format supported by the parser.
- Zero sales must remain in the history; they are valid observations.
- Total rows are ignored and are not treated as sales data.

If the workbook layout changes, update the constants in the corresponding
`config.py` file.

Minimal structure:

| Row | Column B | Column C | Column D |
| --- | --- | ---: | ---: |
| 8 | | Brand A | Brand B |
| 9 | | | |
| 10 | Employee 1 | | |
| 11 | January 2024 | 1200 | 850 |
| 12 | February 2024 | 1300 | 910 |
| 13 | March 2024 | 0 | 970 |
| 14 | Employee 2 | | |
| 15 | January 2024 | 700 | 430 |
| 16 | February 2024 | 760 | 510 |
| 17 | March 2024 | 810 | 0 |

## Local Version

The local version calls `ts_forecast` directly and does not require a running
HTTP service.

Run it from the project root:

```bash
./venv/bin/python -m sales_forecast.main
```

Configuration: `sales_forecast/config.py`

Output: `sales_forecast/output/Sales_Forecast.xlsx`

The workbook title is `Local version OForecast`. The report contains brand
totals and the available employee-brand forecasts. Individual series with less
than `MIN_HISTORY_MONTHS` observations or no positive sales are skipped.

## API Version

The API version converts each series to the OForecast text contract and sends
the requests sequentially to the endpoint configured in
`sales_forecast_api/config.py`.

Run it from the project root:

```bash
./venv/bin/python sales_forecast_api/main.py
```

Configuration: `sales_forecast_api/config.py`

Output: `sales_forecast_api/output/Sales_Forecast_API.xlsx`

Runtime depends on the server and enabled models and may exceed 15 minutes.

Important API settings:

- `API_URL` - forecast endpoint.
- `MODELS` - models sent to the server; `TBATS_y` is intentionally excluded.
- `USE_ALL = False` - use only the configured model list.
- `FILL_MISSING_WITH_MEAN = False` - missing recognized periods use zero.
- `DROP_ZERO_ROWS = False` - preserve zero-sales months.

API request format:

```json
{
  "raw": "2024-01\t1200\n2024-02\t1350",
  "models": ["SES_log", "ETS_log_trend=None_seasonal=None", "AutoARIMA_log"],
  "use_all": false,
  "fill_missing_with_mean": false
}
```

Fields: `raw` is one time series in the OForecast text format, `models` are the
requested model names, `use_all=false` limits the run to that list, and
`fill_missing_with_mean=false` keeps missing periods from being interpolated with
the mean value.

The response is JSON from the OForecast server. The application uses the final
forecast, intervals, selected model, selected dataset, and metadata for the
Excel report. API task failures are written to the output with `Status=error`
and the error message.

## Troubleshooting

- Close the output workbook before running the application; Excel may lock it.
- If forecasts differ, compare every historical value, including zeros and the
  final month. Different input values correctly produce different forecasts.
- If the API request fails, verify network access and `API_URL`.
- Optional model availability depends on the installed package versions.
