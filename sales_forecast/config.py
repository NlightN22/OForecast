"""
Sales Forecast project settings.
"""

from pathlib import Path

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent

INPUT_FILE = PROJECT_DIR / "Sales.xlsx"

OUTPUT_DIR = PROJECT_DIR / "output"

OUTPUT_FILE = OUTPUT_DIR / "Sales_Forecast.xlsx"

# -----------------------------------------------------------------------------
# Excel
# -----------------------------------------------------------------------------

# First workbook sheet
SHEET_NAME = 0

# Brand header row, 1-based
HEADER_ROW = 8

# First two columns:
# 0 - employee
# 1 - month
ROW_LABEL_COLUMN = 1
FIRST_BRAND_COLUMN = 2

# These values are not treated as brands
IGNORED_COLUMNS = {
    "",
    "Итог",
    "Итого",
    "Всего",
    "Total",
}

# -----------------------------------------------------------------------------
# Forecasting
# -----------------------------------------------------------------------------

# Forecast horizon in months
FORECAST_MONTHS = 3

# Minimum history length in months
MIN_HISTORY_MONTHS = 12

# Fill missing months
FILL_MISSING_MONTHS = True

# -----------------------------------------------------------------------------
# OForecast
# -----------------------------------------------------------------------------

# Models to exclude
DISABLED_MODELS = {
    "TBATS_y",
}

# Print full report
PRINT_FULL_REPORT = True
