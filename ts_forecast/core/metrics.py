import numpy as np


def mae(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def smape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.abs(y_true) + np.abs(y_pred)
    out = np.where(denom == 0, 0.0, 2.0 * np.abs(y_pred - y_true) / denom)
    return float(100.0 * np.mean(out))


def mape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = y_true > 0
    if not mask.any():
        return float("nan")
    return float(100.0 * np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])))


def calc_metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "MAE": mae(y_true, y_pred),
        "sMAPE": smape(y_true, y_pred),
        "MAPE": mape(y_true, y_pred),
    }
