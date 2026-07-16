from __future__ import annotations

import math
import unittest

import pandas as pd

from ts_forecast.io.parsing import (
    LabelRecognition,
    add_transforms,
    fill_missing_periods,
    infer_period_freq,
    read_tsv_like,
)

from tests.forecast_scenarios import (
    MISSING_PERIODS_WITH_ZERO_FILL,
    SCENARIOS,
    read_fixture,
)


class InputScenariosTest(unittest.TestCase):
    def test_fixture_files_are_parsed_into_expected_period_ranges(self) -> None:
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.name):
                df = read_tsv_like(read_fixture(scenario.fixture))

                self.assertEqual(scenario.rows_in, len(df))
                self.assertEqual(scenario.period_freq, infer_period_freq(df))
                self.assertEqual(
                    scenario.has_negative_values, bool((df["value"] < 0).any())
                )
                self.assertEqual(list(range(len(df))), df["period_index"].to_list())

                if scenario.period_freq is None:
                    self.assertTrue(df["period_start"].isna().all())
                else:
                    self.assertEqual(scenario.first_period, df["period_start"].min())
                    self.assertEqual(scenario.last_period, df["period_start"].max())

    def test_missing_periods_are_filled_with_zeroes_when_configured(self) -> None:
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.name):
                df = read_tsv_like(read_fixture(scenario.fixture))
                filled, missing_count = fill_missing_periods(df, fill_with_mean=False)

                self.assertEqual(scenario.missing_periods, missing_count)
                self.assertEqual(scenario.rows_after_zero_fill, len(filled))
                self.assertFalse(filled["value"].isna().any())

                expected_zero_periods = MISSING_PERIODS_WITH_ZERO_FILL.get(
                    scenario.fixture, []
                )
                zero_filled_values = filled.loc[
                    filled["period_start"].isin(expected_zero_periods),
                    "value",
                ].to_list()
                self.assertEqual([0.0] * len(expected_zero_periods), zero_filled_values)

    def test_missing_periods_are_interpolated_when_configured(self) -> None:
        scenario = next(
            item for item in SCENARIOS if item.fixture == "data_missing_periods.txt"
        )
        df = read_tsv_like(read_fixture(scenario.fixture))

        filled, missing_count = fill_missing_periods(df, fill_with_mean=True)

        self.assertEqual(scenario.missing_periods, missing_count)
        self.assertFalse(filled["value"].isna().any())
        for period in MISSING_PERIODS_WITH_ZERO_FILL[scenario.fixture]:
            value = float(filled.loc[filled["period_start"] == period, "value"].iloc[0])
            self.assertNotEqual(0.0, value)

    def test_log_transform_supports_negative_values(self) -> None:
        scenario = next(item for item in SCENARIOS if item.has_negative_values)
        df = read_tsv_like(read_fixture(scenario.fixture))
        filled, _ = fill_missing_periods(df, fill_with_mean=False)

        transformed = add_transforms(filled)

        self.assertGreater(float(transformed["log_shift"].iloc[0]), 0.0)
        self.assertTrue(all(math.isfinite(value) for value in transformed["y_log"]))
        self.assertGreaterEqual(
            float((transformed["y"] + transformed["log_shift"]).min()), 0.0
        )

    def test_iso_period_fixture_uses_contiguous_calendar_periods(self) -> None:
        scenario = next(
            item for item in SCENARIOS if item.fixture == "data_iso_periods.txt"
        )
        df = read_tsv_like(read_fixture(scenario.fixture))
        expected_periods = pd.date_range(
            scenario.first_period, scenario.last_period, freq="MS"
        )

        self.assertEqual(expected_periods.to_list(), df["period_start"].to_list())

    def test_quarterly_fixture_uses_contiguous_quarters_after_fill(self) -> None:
        scenario = next(
            item for item in SCENARIOS if item.fixture == "data_quarters.txt"
        )
        df = read_tsv_like(read_fixture(scenario.fixture))

        filled, missing_count = fill_missing_periods(df, fill_with_mean=False)

        expected_periods = pd.date_range(
            scenario.first_period, scenario.last_period, freq="QS"
        )
        self.assertEqual(scenario.missing_periods, missing_count)
        self.assertEqual(expected_periods.to_list(), filled["period_start"].to_list())
        self.assertTrue(
            set(filled["period_start"].dt.month.to_list()).issubset({1, 4, 7, 10})
        )

    def test_ordinal_fixture_keeps_input_order_without_period_filling(self) -> None:
        scenario = next(
            item for item in SCENARIOS if item.fixture == "data_ordinal.txt"
        )
        df = read_tsv_like(read_fixture(scenario.fixture))

        filled, missing_count = fill_missing_periods(df, fill_with_mean=False)

        self.assertIsNone(infer_period_freq(df))
        self.assertEqual(0, missing_count)
        self.assertEqual(df["label"].to_list(), filled["label"].to_list())
        self.assertEqual(scenario.next_period, filled["next_label"].iloc[-1])

    def test_external_label_recognizer_can_supply_period_metadata(self) -> None:
        class FakeRecognizer:
            def recognize(self, labels: list[str]) -> LabelRecognition:
                return LabelRecognition(
                    period_starts=list(
                        pd.date_range("2024-01-01", periods=len(labels), freq="MS")
                    ),
                    period_freq="MS",
                    next_label="2026-01",
                    confidence=0.95,
                )

        df = read_tsv_like(
            read_fixture("data_ordinal.txt"), label_recognizer=FakeRecognizer()
        )

        self.assertEqual("MS", infer_period_freq(df))
        self.assertEqual(pd.Timestamp(2024, 1, 1), df["period_start"].min())
        self.assertEqual("2026-01", df["next_label"].iloc[-1])
