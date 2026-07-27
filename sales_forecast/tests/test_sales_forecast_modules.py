from __future__ import annotations

import pandas as pd
import pytest
import requests

from sales_common.parser import ExcelParser
from sales_forecast.transformer import SalesTransformer
from sales_forecast_api.api_client import ForecastApiClient, ForecastApiError
from sales_forecast_api.transformer import SalesApiTransformer


def sales_frame() -> pd.DataFrame:
    rows = [["" for _ in range(4)] for _ in range(36)]
    rows[7][2:] = ["Brand A", "Brand B"]
    rows[9][1] = "Alice"
    rows[22][1] = "Bob"
    rows[35][1] = "Total"

    months = pd.date_range("2024-01-01", periods=12, freq="MS")
    for index, month in enumerate(months, start=10):
        rows[index][1] = month.strftime("%B %Y")
        rows[index][2] = 100 + index
        rows[index][3] = 200 + index

    for index, month in enumerate(months, start=23):
        rows[index][1] = month.strftime("%B %Y")
        rows[index][2] = 50 + index
        rows[index][3] = 75 + index

    return pd.DataFrame(rows)


def test_excel_parser_reads_workbook(tmp_path):
    path = tmp_path / "Sales.xlsx"
    sales_frame().to_excel(path, index=False, header=False)

    dataframe = ExcelParser().read(path)

    assert dataframe.shape == (36, 4)
    assert dataframe.iloc[7, 2] == "Brand A"


def test_sales_transformer_builds_total_and_employee_series():
    result = SalesTransformer().run(sales_frame())

    series = result[["forecast_level", "manager", "brand"]].drop_duplicates()

    assert len(series) == 6
    assert set(series["manager"]) == {"All managers", "Alice", "Bob"}
    assert result["period_start"].min() == pd.Timestamp("2024-01-01")
    assert result["period_start"].max() == pd.Timestamp("2024-12-01")


def test_api_transformer_prepares_raw_forecast_tasks():
    tasks = SalesApiTransformer().run(sales_frame())

    assert len(tasks) == 6
    assert tasks[0].forecast_level == "brand_total"
    assert tasks[0].manager == "All managers"
    assert tasks[0].raw.splitlines()[0] == "2024-01\t183,00"


class FakeResponse:
    def __init__(self, data=None, error=None):
        self._data = data
        self._error = error
        self.status_code = 500

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.payload = None

    def post(self, api_url, json, timeout):
        self.payload = {"api_url": api_url, "json": json, "timeout": timeout}
        if self.error:
            raise self.error
        return self.response


def test_api_client_sends_expected_payload():
    session = FakeSession(response=FakeResponse({"intervals": [{"point": 123.0}]}))
    client = ForecastApiClient(
        api_url="http://example.test/forecast",
        timeout=3,
        session=session,
    )

    assert client.forecast("2024-01\t100,00")["intervals"][0]["point"] == 123.0
    assert session.payload["json"]["raw"] == "2024-01\t100,00"
    assert session.payload["json"]["use_all"] is False
    assert session.payload["timeout"] == 3


@pytest.mark.parametrize(
    ("response", "error", "message"),
    [
        (None, requests.Timeout(), "timed out"),
        (
            FakeResponse(error=requests.HTTPError(response=FakeResponse())),
            None,
            "HTTP error",
        ),
        (FakeResponse(ValueError("bad json")), None, "invalid JSON"),
        (FakeResponse({"intervals": []}), None, "no intervals"),
    ],
)
def test_api_client_raises_clear_errors(response, error, message):
    client = ForecastApiClient(
        api_url="http://example.test/forecast",
        timeout=3,
        session=FakeSession(response=response, error=error),
    )

    with pytest.raises(ForecastApiError, match=message):
        client.forecast("2024-01\t100,00")
