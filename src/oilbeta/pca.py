"""Step 6 (side analysis) - is there an oil factor in the returns themselves?

PCA on engineered columns (moving averages, distance to them...) would only rediscover
that they are all functions of the same price. PCA on the cross-section of stock
*returns* is informative: PC1 is "the market", and the question is whether a later
component lines up with Brent without being told about it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import MARKET, OIL


def return_pca(stock_returns: pd.DataFrame, factors: pd.DataFrame, n_components: int = 5,
               min_coverage: float = 0.98) -> dict[str, pd.DataFrame]:
    coverage = stock_returns.notna().mean()
    panel = stock_returns.loc[:, coverage >= min_coverage].dropna()
    z = (panel - panel.mean()) / panel.std()
    u, s, vt = np.linalg.svd(z.to_numpy(), full_matrices=False)
    explained = s ** 2 / (s ** 2).sum()
    names = [f"PC{i + 1}" for i in range(n_components)]
    scores = pd.DataFrame(u[:, :n_components] * s[:n_components], index=panel.index, columns=names)
    loadings = pd.DataFrame(vt[:n_components].T, index=panel.columns, columns=names)

    # sign convention: PC1 moves with the market, every later PC moves with oil
    ref = factors.loc[panel.index]
    for i, pc in enumerate(names):
        anchor = ref[MARKET] if i == 0 else ref[OIL]
        if scores[pc].corr(anchor) < 0:
            scores[pc], loadings[pc] = -scores[pc], -loadings[pc]

    corr = pd.DataFrame({col: [scores[pc].corr(ref[col]) for pc in names] for col in ref.columns}, index=names)
    summary = pd.concat([pd.Series(explained[:n_components], index=names, name="variance_share"), corr], axis=1)
    summary.attrs["n_stocks"], summary.attrs["n_weeks"] = panel.shape[1], panel.shape[0]
    return {"summary": summary, "loadings": loadings, "scores": scores}
