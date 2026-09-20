import numpy as np
import pytest
from scipy import stats

from oilbeta.regression import auto_lags, newey_west_cov, ols, orthogonalise


def test_ols_matches_scipy_on_one_regressor(rng):
    x = rng.normal(size=300)
    y = 0.3 + 0.7 * x + rng.normal(scale=0.5, size=300)
    res, ref = ols(y, x[:, None], ["x"]), stats.linregress(x, y)
    assert np.isclose(res.coef("x"), ref.slope)
    assert np.isclose(res.coef("const"), ref.intercept)
    assert np.isclose(res.r2, ref.rvalue ** 2)


def test_hac_with_zero_lags_is_white(rng):
    X = np.column_stack([np.ones(200), rng.normal(size=(200, 2))])
    e = rng.normal(size=200) * (1 + np.abs(X[:, 1]))
    bread = np.linalg.inv(X.T @ X)
    white = bread @ (X.T @ np.diag(e ** 2) @ X) @ bread * 200 / (200 - 3)
    assert np.allclose(newey_west_cov(X, e, lags=0), white)


def test_hac_matches_a_naive_double_loop(rng):
    T, L = 60, 3
    X = np.column_stack([np.ones(T), rng.normal(size=T)])
    e = rng.normal(size=T)
    S = np.zeros((2, 2))
    for t in range(T):
        for s in range(T):
            lag = abs(t - s)
            if lag <= L:
                S += (1 - lag / (L + 1)) * e[t] * e[s] * np.outer(X[t], X[s])
    bread = np.linalg.inv(X.T @ X)
    assert np.allclose(newey_west_cov(X, e, L), bread @ S @ bread * T / (T - 2))


def test_hac_is_close_to_classical_when_errors_are_iid(rng):
    x = rng.normal(size=5000)
    y = 1.0 + 2.0 * x + rng.normal(size=5000)
    res = ols(y, x[:, None], ["x"])
    assert res.stderr("x") == pytest.approx(stats.linregress(x, y).stderr, rel=0.08)


def test_hac_widens_the_interval_under_autocorrelation(rng):
    T = 2000
    x, e = np.zeros(T), np.zeros(T)
    for t in range(1, T):
        x[t] = 0.8 * x[t - 1] + rng.normal()
        e[t] = 0.8 * e[t - 1] + rng.normal()
    y = x + e
    assert ols(y, x[:, None], ["x"], hac_lags="auto").stderr("x") > 1.3 * ols(y, x[:, None], ["x"], hac_lags=0).stderr("x")


def test_nans_are_dropped_and_confidence_interval_covers_truth(rng):
    x = rng.normal(size=400)
    y = 0.5 * x + rng.normal(scale=0.2, size=400)
    y[:10] = np.nan
    res = ols(y, x[:, None], ["x"])
    lo, hi = res.ci("x")
    assert res.nobs == 390 and lo < 0.5 < hi


def test_equality_test_detects_a_real_difference(rng):
    X = rng.normal(size=(1000, 2))
    same = ols(X @ [0.5, 0.5] + rng.normal(size=1000), X, ["a", "b"])
    diff = ols(X @ [0.2, 0.8] + rng.normal(size=1000), X, ["a", "b"])
    assert same.test_equal("a", "b")[2] > 0.05
    assert diff.test_equal("a", "b")[2] < 0.001
    assert diff.test_equal("a", "b")[0] == pytest.approx(-diff.test_equal("b", "a")[0])


def test_orthogonalised_market_is_uncorrelated_with_oil(rng):
    o = rng.normal(size=500)
    m = 0.3 * o + rng.normal(size=500)
    m_perp, a, g = orthogonalise(m, o)
    assert abs(np.corrcoef(m_perp, o)[0, 1]) < 1e-12
    assert g == pytest.approx(0.3, abs=0.1)


def test_auto_lags_rule():
    assert auto_lags(100) == 4 and auto_lags(994) == 6


def test_too_few_observations_raises():
    with pytest.raises(ValueError):
        ols(np.array([1.0, 2.0]), np.array([[1.0], [2.0]]), ["x"])
