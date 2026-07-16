# OForecast

OForecast is a time-series forecasting project with a reusable forecasting
engine, a web interface, and Excel-oriented sales forecast applications.

## Project Structure

- `ts_forecast` - core forecasting package, CLI, and FastAPI web application.
- `sales_common` - shared helpers for reading sales workbooks and preparing
  forecast input.
- `sales_forecast` - local Excel sales forecast workflow using `ts_forecast`
  directly.
- `sales_forecast_api` - Excel sales forecast workflow that sends tasks to a
  remote OForecast API.
- `tests` - automated tests for the core service and sales integrations.

Sales forecast documentation lives in `sales_forecast/README.md`.

## Setup

Install the dependencies from the project root:

```bash
python -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

## Web Service

Run the OForecast web application locally:

```bash
./venv/bin/uvicorn ts_forecast.web.app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

Docker Compose can run the published web image:

```bash
docker compose up -d
```

The published service is then available at `http://localhost:80`.

## CLI

Run the package CLI when you want to forecast a text time series from the
command line:

```bash
./venv/bin/python -m ts_forecast.cli.main
```

## Development

Run the test suite:

```bash
./venv/bin/python -m pytest
```

Run syntax checks:

```bash
./venv/bin/python check_syntax.py
```

