from __future__ import annotations

import requests

from config import (
    API_URL,
    USE_ALL,
    MODELS,
    FILL_MISSING_WITH_MEAN,
)


class ForecastApiClient:
    def forecast(self, raw: str) -> dict:
        payload = {
            "raw": raw,
            "models": MODELS,
            "use_all": USE_ALL,
            "fill_missing_with_mean": FILL_MISSING_WITH_MEAN,
        }

        response = requests.post(
            API_URL,
            json=payload,
            timeout=900,
        )

        response.raise_for_status()

        return response.json()