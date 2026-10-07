from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf


@dataclass(frozen=True)
class CovarianceResult:
    assets: list[str]
    covariance_weekly: pd.DataFrame
    shrinkage: float
    n_observations: int


def _validate_returns(returns: pd.DataFrame, min_observations: int) -> pd.DataFrame:
    if not isinstance(returns, pd.DataFrame):
        raise TypeError("returns must be a pandas DataFrame.")
    if returns.empty:
        raise ValueError("returns is empty.")

    x = returns.astype(float).replace([np.inf, -np.inf], np.nan)

    # Conservative first version: the optimizer must receive a covariance
    # estimated on the exact same asset set, with no hidden imputation.
    valid_assets = x.columns[x.notna().sum(axis=0) >= min_observations]
    x = x.loc[:, valid_assets].dropna(axis=0, how="any")

    if x.shape[1] < 2:
        raise ValueError("Need at least two assets with enough valid history.")
    if x.shape[0] < min_observations:
        raise ValueError(
            f"Only {x.shape[0]} complete observations remain; "
            f"need at least {min_observations}."
        )
    return x


def estimate_ledoit_wolf(
    returns: pd.DataFrame,
    *,
    min_observations: int = 26,
) -> CovarianceResult:
    """
    Estimate a weekly return covariance matrix using Ledoit-Wolf shrinkage.

    Parameters
    ----------
    returns:
        Rows = dates, columns = asset identifiers. Values are simple weekly returns
        expressed as decimals (e.g. 0.01 = +1%).
    min_observations:
        Minimum number of weekly observations required.

    Returns
    -------
    CovarianceResult
        Covariance is in WEEKLY return units.
    """
    x = _validate_returns(returns, min_observations)

    model = LedoitWolf(assume_centered=False).fit(x.to_numpy())
    cov = pd.DataFrame(
        model.covariance_,
        index=x.columns,
        columns=x.columns,
        dtype=float,
    )

    # Numerical hygiene: force exact symmetry.
    cov = 0.5 * (cov + cov.T)

    return CovarianceResult(
        assets=list(x.columns),
        covariance_weekly=cov,
        shrinkage=float(model.shrinkage_),
        n_observations=int(x.shape[0]),
    )


def nearest_psd(matrix: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    """Return a symmetric positive-semidefinite projection."""
    a = np.asarray(matrix, dtype=float)
    a = 0.5 * (a + a.T)
    eigenvalues, eigenvectors = np.linalg.eigh(a)
    eigenvalues = np.maximum(eigenvalues, eps)
    return (eigenvectors * eigenvalues) @ eigenvectors.T


def covariance_square_root(matrix: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    """Symmetric square root of a PSD covariance matrix."""
    a = nearest_psd(matrix, eps=eps)
    eigenvalues, eigenvectors = np.linalg.eigh(a)
    return (eigenvectors * np.sqrt(eigenvalues)) @ eigenvectors.T
