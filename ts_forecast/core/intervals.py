from __future__ import annotations

import numpy as np

def safe_expm1_arr(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = np.clip(x, -50, 50)
    return np.expm1(x)

def bootstrap_intervals_log1p(
    errors_log: np.ndarray,
    point_log: float,
    n: int,
    seed: int,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    draws = rng.choice(errors_log, size=n, replace=True)
    sims = point_log + draws

    q80 = np.quantile(sims, [0.10, 0.90])
    q95 = np.quantile(sims, [0.025, 0.975])

    point = float(max(0.0, safe_expm1_arr(np.array([point_log]))[0]))
    lo80, hi80 = safe_expm1_arr(q80)
    lo95, hi95 = safe_expm1_arr(q95)

    return {
        "point": point,
        "lo80": float(max(0.0, lo80)),
        "hi80": float(max(0.0, hi80)),
        "lo95": float(max(0.0, lo95)),
        "hi95": float(max(0.0, hi95)),
    }