"""OLS with HAC standard errors. Pure numpy/scipy: no pandas below this line of the package."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from .hac import auto_lags, newey_west_cov


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
