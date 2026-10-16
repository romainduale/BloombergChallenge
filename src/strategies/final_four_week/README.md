# Stratégie finale quatre semaines — 80/20

Cette stratégie aligne le signal du vendredi 16 octobre 2026 sur la fin du
challenge, vendredi 13 novembre 2026.

- Le cœur de 80 % est réentraîné sur une cible relative à quatre semaines.
- La covariance et le risque sont mis à l'échelle sur quatre semaines.
- La poche opportuniste de 20 % conserve strictement ses règles, ses poids et sa
  configuration existants.
- Le CSV final expose les scores Elastic Net et Tail, chaque feature, les bêta
  standardisés et la contribution de chaque feature au score du titre.

Une contribution Elastic s'additionne sur l'échelle de rendement prédit. Une
contribution Tail s'additionne sur l'échelle des log-odds avant conversion en
probabilité ; elle ne doit donc pas être lue directement comme un pourcentage.

Après la clôture du 16 octobre :

```bash
.venv/bin/python -m src.strategies.final_four_week.pipeline \
  --refresh-market-data \
  --data-end 2026-10-16 \
  --require-signal-date 2026-10-16
```

Pour éviter l'appel lent aux objectifs analystes Yahoo, ajouter
`--skip-analysts`. Cela ne change pas les autres règles de la poche 20 %.

Le livrable principal est :

```text
data/processed/strategies/final_four_week/final_allocation_explained.csv
```

Le backtest quatre semaines se lance séparément :

```bash
.venv/bin/python -m src.strategies.final_four_week.backtest \
  --rebuild-features \
  --strategy-profile agressif \
  --profile sans_stop
```

## Comparer les profils de risque

Les paramètres de sélection et d'optimisation sont centralisés dans
`config/final_strategy_profiles.json`. Les trois profils conservent la même cible,
les mêmes features et les mêmes modèles entraînés ; ils changent le poids Tail,
la pénalité de covariance, la corrélation maximale et la concentration autorisée.

```bash
.venv/bin/python -m src.strategies.final_four_week.compare_profiles
```

Cette commande génère les allocations prévues aujourd'hui et trois backtests sur
des périodes historiques strictement communes. Ajouter `--forecast-only` pour ne
calculer que les prévisions actuelles.

Les résultats se trouvent dans :

```text
data/processed/strategies/profile_comparison/profile_comparison.csv
data/processed/strategies/profile_comparison/profile_comparison.md
```

La prévision de profit porte uniquement sur le cœur de 80 % et représente une
surperformance estimée face au WLS, jamais un gain garanti. La poche opportuniste
de 20 % reste inchangée et hors de cette comparaison afin d'isoler le profil testé.

Le manifeste `run_manifest.json` indique les dates réellement présentes dans les
prix, le benchmark, le signal et les données opportunistes. Le benchmark WLS ne
peut pas être remplacé silencieusement par un proxy Yahoo : il doit être actualisé
avec l'export Bloomberg prévu par `src.weekly_data_update`.
