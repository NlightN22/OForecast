from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "Sales.xlsx"
OUTPUT_FILE = BASE_DIR / "output" / "Sales_Forecast_API.xlsx"

# API_URL = "http://fc.corp.komponent-m.ru/forecast"
API_URL = "http://172.16.16.106/forecast"

HEADER_ROW = 8
FIRST_BRAND_COLUMN = 2
PERIOD_COLUMN = 1

USE_ALL = False

MODELS = [
    "SES_log",
    "ETS_log_trend=None_seasonal=None",
    "ETS_log_trend=add_seasonal=None",
    "ETS_log_trend=None_seasonal=add",
    "ETS_log_trend=add_seasonal=add",
    "SeasonalNaive_y",
    "AutoARIMA_log",
    "SF_CrostonSBA",
    "SF_TSB",
    "SF_ADIDA",
    "SF_IMAPA",
    "SF_MSTL",
]
FILL_MISSING_WITH_MEAN = False

DROP_ZERO_ROWS = False
