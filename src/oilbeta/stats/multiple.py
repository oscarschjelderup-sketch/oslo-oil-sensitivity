"""Multiple testing. Sixty-three stocks means sixty-three chances to be "significant at 5%" by luck."""
from __future__ import annotations

import numpy as np


def benjamini_hochberg(p_values) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (q-values). NaNs stay NaN and do not count as tests.

    A finding with q <= 0.05 belongs to a set in which at most 5% are expected to be false
    discoveries. With m tests sorted so that p(1) <= ... <= p(m):
        q(i) = min over j >= i of  p(j) * m / j
    """
    p = np.asarray(p_values, dtype=float)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return q
    order = np.argsort(p[ok])
    ranked = p[ok][order] * m / np.arange(1, m + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1].clip(max=1.0)
    out = np.empty(m)
    out[order] = adjusted
    q[ok] = out
    return q
