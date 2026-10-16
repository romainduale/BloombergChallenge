# Stratégie cinq semaines

Cette variante est la référence historique déjà testée sur cinq offsets. Elle
est conservée pour comparer les résultats, mais elle n'est plus la stratégie
finale du challenge 2026 puisque le signal du 16 octobre doit être clôturé le
13 novembre, soit quatre semaines plus tard.

```bash
.venv/bin/python -m src.strategies.five_week.run --profile sans_stop
```

Le code historique reste dans `src.features` et `src.backtest_execution_v2`.
