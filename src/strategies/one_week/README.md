# Stratégie une semaine

Cette variante réentraîne les modèles sur une cible relative à une semaine et
rééquilibre chaque vendredi. Elle est conservée comme expérience : son turnover
et ses coûts sont supérieurs à ceux de la stratégie de référence.

```bash
.venv/bin/python -m src.strategies.one_week.run --profile sans_stop
```

Le code historique reste dans `src.features_weekly_1w` et
`src.backtest_execution_1w`; ce dossier fournit un point d'entrée stable.
