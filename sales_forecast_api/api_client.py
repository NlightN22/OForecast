from __future__ import annotations

import requests

try:
    from .config import (
        API_URL,
        USE_ALL,
        MODELS,
        FILL_MISSING_WITH_MEAN,
    )
except ImportError:  # pragma: no cover - script execution fallback
    from config import (
        API_URL,
        USE_ALL,
        MODELS,
        FILL_MISSING_WITH_MEAN,
    )


class ForecastApiError(RuntimeError):
    pass


class ForecastApiClient:
    def __init__(
        self,
        api_url: str = API_URL,
        timeout: int = 900,
        session=requests,
    ):
        self.api_url = api_url
        self.timeout = timeout
        self.session = session

    def forecast(self, raw: str) -> dict:
        payload = {
            "raw": raw,
            "models": MODELS,
            "use_all": USE_ALL,
            "fill_missing_with_mean": FILL_MISSING_WITH_MEAN,
        }

        try:
            response = self.session.post(
                self.api_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise ForecastApiError("Forecast API request timed out.") from exc
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", "unknown")
            raise ForecastApiError(f"Forecast API HTTP error: {status}.") from exc
        except requests.RequestException as exc:
            raise ForecastApiError(f"Forecast API request failed: {exc}") from exc
        except ValueError as exc:
            raise ForecastApiError("Forecast API returned invalid JSON.") from exc

        self._validate_response(data)
        return data

    @staticmethod
    def _validate_response(data: dict) -> None:
        if not isinstance(data, dict):
            raise ForecastApiError("Forecast API response must be a JSON object.")

        intervals = data.get("intervals")
        if not isinstance(intervals, list) or not intervals:
            raise ForecastApiError("Forecast API response has no intervals.")

        first_interval = intervals[0]
        if not isinstance(first_interval, dict):
            raise ForecastApiError("Forecast API interval must be an object.")

        if "point" not in first_interval:
            raise ForecastApiError("Forecast API interval has no point forecast.")
