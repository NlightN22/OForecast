from __future__ import annotations

import math
import os
import unittest

from ts_forecast.core.config import ForecastConfig
from ts_forecast.core.service import run_forecast

from tests.forecast_scenarios import SCENARIOS, read_fixture


RUN_FULL_INTEGRATION = os.environ.get("OFORECAST_RUN_FULL_INTEGRATION") == "1"
FULL_INTEGRATION_FIXTURE = os.environ.get("OFORECAST_FULL_FIXTURE")


@unittest.skipUnless(
    RUN_FULL_INTEGRATION,
    "Set OFORECAST_RUN_FULL_INTEGRATION=1 to run slow full-model integration tests.",
)
class FullModelIntegrationTest(unittest.TestCase):
    def test_all_available_models_run_for_each_fixture(self) -> None:
        cfg = ForecastConfig(bootstrap_n=1_000)
        scenarios = [
            scenario
            for scenario in SCENARIOS
            if FULL_INTEGRATION_FIXTURE in (None, "", scenario.fixture, scenario.name)
        ]

        if not scenarios:
            self.fail(f"No full integration fixture matched: {FULL_INTEGRATION_FIXTURE}")

        for scenario in scenarios:
            with self.subTest(scenario=scenario.name):
                print(f"\nfull-integration: fixture={scenario.fixture}", flush=True)

                def log(message: str) -> None:
                    print(f"{scenario.fixture}: {message}", flush=True)

                result = run_forecast(
                    read_fixture(scenario.fixture),
                    cfg=cfg,
                    use_all=True,
                    on_log=log,
                )

                self.assertEqual(scenario.rows_in, result.rows_in)
                self.assertEqual(scenario.rows_after_zero_fill, result.rows_after_fill)
                self.assertEqual(scenario.missing_periods, result.missing_periods_filled)
                self.assertEqual(scenario.next_period, result.next_period)
                self.assertFalse(result.metrics.empty)
                self.assertFalse(result.backtest.empty)
                self.assertTrue(math.isfinite(float(result.intervals["point"])))
