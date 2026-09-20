"""OLS with Newey-West (HAC) standard errors, written out in numpy so every number is explainable."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass
class OLSResult:
    names: list[str]
    params: np.ndarray
    cov: np.ndarray
    resid: np.ndarray
    r2: float
    nobs: int
    hac_lags: int

    @property
    def se(self) -> np.ndarray:
        return np.sqrt(np.diag(self.cov))

    @property
    def tstat(self) -> np.ndarray:
        return self.params / self.se

    @property
    def dof(self) -> int:
        return self.nobs - len(self.params)

    def idx(self, name: str) -> int:
        return self.names.index(name)

    def coef(self, name: str) -> float:
        return float(self.params[self.idx(name)])

    def stderr(self, name: str) -> float:
        return float(self.se[self.idx(name)])

    def ci(self, name: str, level: float = 0.95) -> tuple[float, float]:
        q = stats.t.ppf(0.5 + level / 2, self.dof)
        b, s = self.coef(name), self.stderr(name)
        return b - q * s, b + q * s

    def pvalue(self, name: str) -> float:
        return float(2 * stats.t.sf(abs(self.tstat[self.idx(name)]), self.dof))

    def test_equal(self, a: str, b: str) -> tuple[float, float, float]:
        """Wald/t test of H0: coef[a] == coef[b]. Returns (difference, t, p)."""
        i, j = self.idx(a), self.idx(b)
        diff = self.params[i] - self.params[j]
        var = self.cov[i, i] + self.cov[j, j] - 2 * self.cov[i, j]
        t = diff / np.sqrt(var)
        return float(diff), float(t), float(2 * stats.t.sf(abs(t), self.dof))


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


def ols(y: np.ndarray, X: np.ndarray, names: list[str], hac_lags: int | str = "auto") -> OLSResult:
    """Regress y on X (a constant is added as the first column)."""
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones(len(y)), np.asarray(X, dtype=float)])
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X = y[ok], X[ok]
    T, k = X.shape
    if T <= k + 1:
        raise ValueError(f"Too few observations ({T}) for {k} parameters")
    params, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ params
    tss = ((y - y.mean()) ** 2).sum()
    lags = auto_lags(T) if hac_lags == "auto" else int(hac_lags)
    return OLSResult(
        names=["const", *names],
        params=params,
        cov=newey_west_cov(X, resid, lags),
        resid=resid,
        r2=float(1 - (resid ** 2).sum() / tss) if tss > 0 else np.nan,
        nobs=T,
        hac_lags=lags,
    )


def orthogonalise(m: np.ndarray, o: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Residual of m regressed on o, plus the intercept and slope used (m = a + g*o + m_perp)."""
    ok = np.isfinite(m) & np.isfinite(o)
    g, a = np.polyfit(o[ok], m[ok], 1)
    return m - (a + g * o), float(a), float(g)
