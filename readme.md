# OForecast

## Quick start (Docker Compose)
```bash
wget https://github.com/NlightN22/OForecast/raw/refs/heads/main/docker-compose.yml
docker compose up -d
```
Then open http://localhost:80.

## Overview
OForecast is a small FastAPI service and CLI tool for time series forecasting.

## Features
- HTTP API for forecasts via FastAPI.
- CLI mode for local runs.
- Models based on statsforecast, sktime, tbats, and scikit-learn.
- Optional filling of missing months by interpolation (default is 0 for gaps).

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
