from __future__ import annotations

import numpy as np
from typing import Dict, Tuple

from .metrics import calc_metrics

def build_ensemble_or_best(
    actual_y: np.ndarray,
    preds_y: Dict[str, np.ndarray],
    topk: int,
    max_degradation: float,
) -> Tuple[str, np.ndarray, Dict[str, dict]]:
    model_metrics = {m: calc_metrics(actual_y, p) for m, p in preds_y.items()}
    ranked = sorted(model_metrics.items(), key=lambda kv: kv[1]["MAE"])
    best_name, best_m = ranked[0][0], ranked[0][1]

    top = [m for m, _ in ranked[:topk]]
    w = np.array([1.0 / max(model_metrics[m]["MAE"], 1e-9) for m in top], dtype=float)
    w = w / w.sum()

    ens = np.zeros_like(actual_y, dtype=float)
    for wi, m in zip(w, top):
        ens += wi * preds_y[m]

    ens_m = calc_metrics(actual_y, ens)
    model_metrics["Ensemble_top3_weighted"] = ens_m

    if ens_m["MAE"] <= best_m["MAE"] * (1.0 + max_degradation):
        return "Ensemble_top3_weighted", ens, model_metrics
    return best_name, preds_y[best_name], model_metrics