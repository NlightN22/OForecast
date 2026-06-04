# Test Scenarios

The test suite is split by responsibility:

- `test_input_scenarios.py` validates fixture parsing, period detection, period filling, interpolation, abbreviated period formats, ordinal labels, and negative values in the log transform.
- `test_service_scenarios.py` runs `run_forecast` with a stable model set that exercises log models, ETS models, seasonal naive forecasts, backtests, ensembles, and intervals without relying on optional heavy model packages.
- `test_web_scenarios.py` validates the FastAPI JSON delivery path with the same stable model set. It requires the dev dependency `httpx`.
- `test_full_model_integration.py` runs `run_forecast(..., use_all=True)` for every fixture and is disabled by default because optional model packages can take several minutes.

Fixture coverage:

- `data_complete_periods.txt`: complete period series with no missing periods.
- `data_missing_periods.txt`: missing periods plus negative values; this guards against log transform domain errors.
- `data_iso_periods.txt`: ISO period labels with space-grouped numbers.
- `data_quarters.txt`: quarterly series with one missing quarter; this verifies quarter parsing and quarter-based gap filling.
- `data_ordinal.txt`: arbitrary labels with no recognized calendar; this verifies values-only forecasting.

Run the default suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Install test dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run full model integration tests:

```powershell
$env:OFORECAST_RUN_FULL_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest tests.test_full_model_integration -v
```

The full model suite intentionally has no in-test timeout. Depending on optional model packages and the input data, it can run for several minutes.

Run one full model fixture:

```powershell
$env:OFORECAST_RUN_FULL_INTEGRATION = "1"
$env:OFORECAST_FULL_FIXTURE = "data_missing_periods.txt"
.\.venv\Scripts\python.exe -m unittest tests.test_full_model_integration -v
```

