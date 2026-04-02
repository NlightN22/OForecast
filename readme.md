# OForecast

OForecast is a small FastAPI service and CLI tool for time series forecasting.

## Features
- HTTP API for forecasts via FastAPI.
- CLI mode for local runs.
- Models based on statsforecast, sktime, tbats, and scikit-learn.

## Run the API
```bash
uvicorn ts_forecast.web.app:app --host 0.0.0.0 --port 8000
```

## Run the CLI
```bash
python -m ts_forecast.main
```

## Data
The CLI reads `data.txt` from the project root.
