# Bloomberg Global Trading Challenge 2026 

This repository presents the quantitative investment strategy developed by our ESILV team for the **Bloomberg Global Trading Challenge 2026**.

The competition consists of managing a $1 million virtual equity portfolio over several weeks, with the objective of outperforming the Bloomberg World Large, Mid & Small Cap Index (WLS).

Our approach combines statistical learning, quantitative risk management and constrained portfolio optimization to identify investment opportunities and generate systematic portfolio allocations.

### Investment constraints

- Initial capital: $1,000,000
- Investment universe: WLS constituents
- Long-only portfolio, without leverage or ETFs
- Maximum exposure of 20% per security
- Simulated transaction costs

## Quantitative Strategy

Our final strategy follows an 80/20 allocation framework:

| Component | Allocation | Objective |
|---|---:|---|
| Quantitative core | 80% | Systematic benchmark outperformance |
| Opportunistic portfolio | 20% | Capture higher-upside opportunities |

### 1. Expected Return Estimation

We use a cross-sectional Elastic Net regression to estimate the expected relative returns of individual securities over a four-week investment horizon.

The model is trained on a stock-week panel using financial and market-based features. Combining L1 and L2 regularization helps control overfitting and multicollinearity while identifying relevant predictors.

A complementary tail model is used to capture potential extreme-return opportunities and improve stock selection.

Model validation relies on purged walk-forward testing to prevent look-ahead bias and assess out-of-sample predictive performance.

### 2. Risk Modeling

The covariance matrix is estimated using the Ledoit-Wolf shrinkage estimator on one year of historical USD-denominated returns.

Compared with the empirical covariance matrix, shrinkage provides more stable risk estimates in a high-dimensional investment universe.

Correlation screening is also implemented to limit portfolio concentration across highly correlated securities.

### 3. Portfolio Optimization

Expected returns and covariance estimates are combined within a constrained long-only allocation framework.

The target optimization problem is formulated in active weights relative to the benchmark:

$$
\max_w \quad
\hat{\alpha}^{T}(w-w_b)
-\kappa\sqrt{(w-w_b)^T\Omega(w-w_b)}
-\gamma\|w-w_{prev}\|_1
$$

Where:

- $\hat{\alpha}$: expected relative returns
- $w_b$: benchmark weights
- $\Omega$: estimated covariance matrix
- $\kappa$: risk and robustness parameter
- $\gamma$: turnover penalty

The objective balances expected outperformance, active risk and transaction costs under investment constraints.

### 4. Opportunistic Allocation

The remaining 20% is allocated across four distinct securities, each representing 5% of the total portfolio.

Stock selection relies on a dedicated scoring model incorporating momentum, volatility, drawdown, liquidity and upside potential.

This allocation aims to complement the systematic core with higher-conviction opportunities.

## Data

The main data source is Bloomberg, through Bloomberg Query Language (BQL) and terminal exports.

Yahoo Finance is used as a complementary source to refresh market prices and volumes.

The research pipeline includes:

- Data cleaning and feature engineering
- Cross-sectional financial indicators
- Historical returns and risk estimation
- Forward relative-return targets
- Benchmark and market data alignment

Particular attention is given to data leakage, currency consistency and historical data quality.

## Backtesting & Validation

The research framework includes:

- Purged walk-forward validation
- Comparison of one-, four- and five-week investment horizons
- Information coefficient and placebo tests
- Transaction costs and portfolio turnover
- Drawdown and execution analysis
- Comparison of conservative, intermediate and aggressive risk profiles

The primary performance criterion is relative performance against the WLS benchmark.

## Repository Structure

```text
.
├── data/           # Raw and processed market data
├── src/            # Models, optimization and backtesting
│   └── strategies/ # Tested investment strategies
├── config/         # Model and portfolio parameters
├── docs/           # Research and technical documentation
├── tests/          # Model and execution validation
└── requirements.txt
```

The code is organized into independent modules covering data processing, signal generation, risk estimation, portfolio construction and trade execution planning.

## Getting Started

Clone the repository and install the dependencies using Python 3.14:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the final investment strategy:

```bash
python -m src.strategies.final_four_week.pipeline \
  --refresh-market-data \
  --data-end 2026-10-16 \
  --require-signal-date 2026-10-16
```

Run the test suite:

```bash
python -m pytest
```

The pipeline generates portfolio allocations, individual stock scores, feature contributions and execution recommendations. Results are stored in `data/processed/`.

Bloomberg data must be available locally before running the complete pipeline.

## Documentation

- [Pipeline guide](docs/guide_utilisation_pipeline.md)
- [Final investment strategy](docs/guide_pipeline_finale_4_semaines.md)
- [Quantitative architecture](docs/architecture_strategie.md)
- [Backtesting and execution audit](docs/audit_execution_features.md)

---

*Developed by ESILV engineering students for the Bloomberg Global Trading Challenge 2026. This project is intended for academic and quantitative research purposes.*
