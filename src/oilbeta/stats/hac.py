"""Newey-West covariance, written out in numpy so every standard error is explainable."""
from __future__ import annotations

import numpy as np


def auto_lags(nobs: int) -> int:
    """Newey-West (1994) rule of thumb."""
    return int(np.floor(4 * (nobs / 100) ** (2 / 9)))


def newey_west_cov(X: np.ndarray, resid: np.ndarray, lags: int) -> np.ndarray:
    """HAC covariance with a Bartlett kernel and a T/(T-k) small-sample correction.

    With lags=0 this is White's heteroskedasticity-robust covariance.
    """
    T, k = X.shape
    u = X * resid[:, None]                      # score contributions x_t * e_t
    S = u.T @ u
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        G = u[lag:].T @ u[:-lag]
        S += w * (G + G.T)
    XtX_inv = np.linalg.inv(X.T @ X)
    return XtX_inv @ S @ XtX_inv * T / (T - k)
