from __future__ import annotations

import math
import unittest

from ts_forecast.core.config import ForecastConfig
from ts_forecast.core.service import run_forecast

from tests.forecast_scenarios import SCENARIOS, STABLE_MODEL_SET, read_fixture


class ForecastServiceScenariosTest(unittest.TestCase):
    def test_forecast_service_runs_stable_models_for_each_fixture(self) -> None:
        cfg = ForecastConfig(bootstrap_n=500)

        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.name):
                result = run_forecast(
                    read_fixture(scenario.fixture),
                    cfg=cfg,
                    models=STABLE_MODEL_SET,
                    use_all=False,
                )

                self.assertEqual(scenario.rows_in, result.rows_in)
                self.assertEqual(scenario.rows_after_zero_fill, result.rows_after_fill)
                self.assertEqual(
                    scenario.missing_periods, result.missing_periods_filled
                )
                self.assertEqual(scenario.next_period, result.next_period)
                self.assertIn(
                    result.chosen_model,
                    {*STABLE_MODEL_SET, "Ensemble_top3_weighted"},
                )
                self.assertFalse(result.metrics.empty)
                self.assertFalse(result.backtest.empty)
                self.assertGreater(len(result.backtest), 0)
                self.assert_interval_is_valid(result.intervals)

    def test_forecast_service_runs_interpolated_missing_period_scenario(self) -> None:
        scenario = next(
            item for item in SCENARIOS if item.fixture == "data_missing_periods.txt"
        )

        result = run_forecast(
            read_fixture(scenario.fixture),
            cfg=ForecastConfig(bootstrap_n=500),
            models=STABLE_MODEL_SET,
            use_all=False,
            fill_missing_with_mean=True,
        )

        self.assertEqual(scenario.rows_in, result.rows_in)
        self.assertEqual(scenario.rows_after_zero_fill, result.rows_after_fill)
        self.assertEqual(scenario.missing_periods, result.missing_periods_filled)
        self.assertEqual(scenario.next_period, result.next_period)
        self.assert_interval_is_valid(result.intervals)

    def assert_interval_is_valid(self, intervals: dict[str, float]) -> None:
        point = float(intervals["point"])
        lo80 = float(intervals["lo80"])
        hi80 = float(intervals["hi80"])
        lo95 = float(intervals["lo95"])
        hi95 = float(intervals["hi95"])

        for value in [point, lo80, hi80, lo95, hi95]:
            self.assertTrue(math.isfinite(value))
        self.assertLessEqual(lo95, lo80)
        self.assertLessEqual(lo80, hi80)
        self.assertLessEqual(hi80, hi95)
