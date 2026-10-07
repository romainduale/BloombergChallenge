import numpy as np
import pandas as pd

from src.covariance import estimate_ledoit_wolf


def test_ledoit_wolf_is_symmetric_psd():
    rng = np.random.default_rng(42)
    returns = pd.DataFrame(
        rng.normal(0, 0.02, size=(60, 8)),
        columns=[f"A{i}" for i in range(8)],
    )

    result = estimate_ledoit_wolf(returns, min_observations=40)
    cov = result.covariance_weekly.to_numpy()

    assert np.allclose(cov, cov.T, atol=1e-12)
    assert np.linalg.eigvalsh(cov).min() >= -1e-10
    assert 0.0 <= result.shrinkage <= 1.0
