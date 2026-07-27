from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient
except RuntimeError as exc:
    TestClient = None
    TESTCLIENT_IMPORT_ERROR = exc
else:
    TESTCLIENT_IMPORT_ERROR = None

from tests.forecast_scenarios import SCENARIOS, STABLE_MODEL_SET, read_fixture
from ts_forecast.web.app import app


@unittest.skipIf(TestClient is None, f"FastAPI TestClient unavailable: {TESTCLIENT_IMPORT_ERROR}")
class ForecastWebScenariosTest(unittest.TestCase):
    def test_forecast_json_endpoint_runs_selected_models(self) -> None:
        scenario = next(item for item in SCENARIOS if item.fixture == "data_iso_periods.txt")
        client = TestClient(app)

        response = client.post(
            "/forecast",
            json={
                "raw": read_fixture(scenario.fixture),
                "models": STABLE_MODEL_SET,
                "use_all": False,
                "fill_missing_with_mean": False,
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(scenario.rows_in, payload["rows_in"])
        self.assertEqual(scenario.rows_after_zero_fill, payload["rows_after_fill"])
        self.assertEqual(scenario.next_period, payload["next_period"])
        self.assertTrue(payload["metrics"])
        self.assertTrue(payload["backtest"])
        self.assertTrue(payload["intervals"])

