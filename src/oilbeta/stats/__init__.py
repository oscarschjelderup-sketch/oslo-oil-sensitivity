"""Estimators. Arrays in, numbers out: nothing here knows about tickers, dates or files."""
from .hac import auto_lags, newey_west_cov
from .multiple import benjamini_hochberg
from .ols import OLSResult, ols, orthogonalise

__all__ = ["OLSResult", "auto_lags", "benjamini_hochberg", "newey_west_cov", "ols", "orthogonalise"]
