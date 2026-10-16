# Guide de la pipeline finale quatre semaines

Ce guide explique comment :

1. produire l'allocation finale à quatre semaines ;
2. choisir entre les profils `prudent`, `intermediaire` et `agressif` ;
3. comparer leurs prévisions et leurs backtests ;
4. modifier les paramètres sans toucher à la poche opportuniste de 20 %.

Toutes les commandes doivent être lancées depuis la racine du projet :

```bash
cd /Users/duale/bloomberg-trading-challenge-quant-lab
```

## 1. Ce que construit la pipeline

La pipeline finale partage le portefeuille en deux poches :

- **80 % cœur quatre semaines** : Elastic Net, modèle Tail, covariance
  Ledoit-Wolf, filtre de corrélation puis optimisation des poids ;
- **20 % opportuniste** : règles historiques conservées sans modification.

Le signal du vendredi 16 octobre 2026 est détenu quatre semaines, jusqu'au vendredi
13 novembre 2026.

Le profil stratégique ne modifie que le cœur de 80 %. Il ne change ni les règles, ni
les paramètres, ni le poids de la poche opportuniste.

## 2. Lancer la pipeline finale

### Lancement complet recommandé

Après la clôture du 16 octobre, cette commande actualise les prix et volumes, vérifie
que le signal est bien daté du 16 octobre et produit le portefeuille agressif :

```bash
.venv/bin/python -m src.strategies.final_four_week.pipeline \
  --refresh-market-data \
  --data-end 2026-10-16 \
  --require-signal-date 2026-10-16 \
  --strategy-profile agressif \
  --profile sans_stop
```

`agressif` est le profil stratégique par défaut. Il est néanmoins conseillé de le
préciser dans la commande afin que le lancement reste immédiatement lisible.

### Relancer sans retélécharger les prix

Si les prix et volumes locaux ont déjà été actualisés au 16 octobre :

```bash
.venv/bin/python -m src.strategies.final_four_week.pipeline \
  --data-end 2026-10-16 \
  --require-signal-date 2026-10-16 \
  --strategy-profile agressif \
  --profile sans_stop
```

L'absence de `--refresh-market-data` signifie que la pipeline réutilise les données
locales. L'option `--require-signal-date` bloque le calcul si le dernier signal n'est
pas celui attendu, ce qui évite de produire une allocation avec une semaine de retard.

### Choisir un autre profil

Il suffit de remplacer la valeur de `--strategy-profile` :

```bash
# Profil intermédiaire
.venv/bin/python -m src.strategies.final_four_week.pipeline \
  --strategy-profile intermediaire \
  --data-end 2026-10-16 \
  --require-signal-date 2026-10-16

# Profil prudent
.venv/bin/python -m src.strategies.final_four_week.pipeline \
  --strategy-profile prudent \
  --data-end 2026-10-16 \
  --require-signal-date 2026-10-16
```

### Options utiles

| Option | Rôle |
|---|---|
| `--strategy-profile` | Paramètres du modèle, du filtre de risque et de l'optimiseur du cœur 80 % |
| `--profile` | Profil d'exécution : frais, slippage, ordres limites et stop-loss |
| `--capital` | Capital total, 1 000 000 USD par défaut |
| `--current-positions` | Positions actuelles utilisées pour produire `BUY`, `HOLD`, `REDUCE` ou `SELL` |
| `--refresh-market-data` | Télécharge les prix et volumes jusqu'à `--data-end` |
| `--require-signal-date` | Arrête la pipeline si la date du signal est différente |
| `--skip-analysts` | Ignore les objectifs analystes si leur récupération est indisponible ou trop lente |
| `--opportunistic-period` | Profondeur de l'historique Yahoo de la poche 20 %, `2y` par défaut |

Exemple avec les positions réellement détenues :

```bash
.venv/bin/python -m src.strategies.final_four_week.pipeline \
  --strategy-profile agressif \
  --profile sans_stop \
  --capital 1000000 \
  --current-positions data/current_positions.csv \
  --data-end 2026-10-16 \
  --require-signal-date 2026-10-16
```

## 3. Fichiers produits

Les principaux résultats sont écrits dans
`data/processed/strategies/final_four_week/` :

| Fichier | Contenu |
|---|---|
| `final_allocation_explained.csv` | Allocation finale 80/20, scores, features, bêta et contributions |
| `run_manifest.json` | Profil réellement utilisé, dates, paramètres et chemins de sortie |
| `latest_signal_4w.csv` | Classement de tout l'univers au dernier signal |
| `model_coefficients_4w.csv` | Coefficients des modèles Elastic Net et Tail |
| `core_80_source_portfolio_4w.csv` | Portefeuille du cœur avant assemblage 80/20 |
| `allocation_80_20.csv` | Allocation combinée avant construction des ordres |
| `execution_orders.csv` | Ordres proposés selon les positions actuelles |
| `ledoit_wolf_excess_covariance_weekly.csv` | Covariance utilisée par l'optimiseur |
| `ledoit_wolf_excess_correlation.csv` | Corrélations utilisées pour la shortlist |

Dans le CSV final :

- `elastic_net_score` est la surperformance relative prévue à quatre semaines ;
- `tail_score` est la probabilité estimée d'appartenir aux meilleurs titres ;
- `combined_score` combine les rangs des deux modèles selon le profil ;
- `feature_*` contient la valeur standardisée de chaque feature ;
- `elastic_beta_*` et `tail_beta_*` contiennent les coefficients appris ;
- `elastic_contribution_*` et `tail_contribution_*` montrent l'effet de chaque
  feature sur le score du titre.

Les contributions Elastic correspondent essentiellement à `bêta × feature`. Les
contributions Tail sont sur l'échelle des log-odds avant conversion en probabilité.

## 4. Comparer prudent, intermédiaire et agressif

### Comparaison complète recommandée

La commande suivante calcule la prévision actuelle et un backtest walk-forward pour
les trois profils sur exactement les mêmes périodes historiques :

```bash
.venv/bin/python -m src.strategies.final_four_week.compare_profiles
```

Les résultats sont écrits dans :

```text
data/processed/strategies/profile_comparison/
```

Les fichiers principaux sont :

- `profile_comparison.md` : tableau directement lisible ;
- `profile_comparison.csv` : toutes les métriques et tous les paramètres ;
- `latest_core_allocations/agressif.csv` ;
- `latest_core_allocations/intermediaire.csv` ;
- `latest_core_allocations/prudent.csv` ;
- un dossier par profil avec `periods.csv` et `holdings.csv`.

### Comparer uniquement les prévisions actuelles

Cette version est plus rapide, mais ne permet pas de juger la robustesse historique :

```bash
.venv/bin/python -m src.strategies.final_four_week.compare_profiles \
  --forecast-only
```

### Comparer seulement certains profils

```bash
.venv/bin/python -m src.strategies.final_four_week.compare_profiles \
  --profiles intermediaire agressif
```

### Recalculer aussi les features

```bash
.venv/bin/python -m src.strategies.final_four_week.compare_profiles \
  --rebuild-features
```

### Utiliser un autre profil d'exécution dans le backtest

```bash
.venv/bin/python -m src.strategies.final_four_week.compare_profiles \
  --execution-profile sans_stop
```

Le profil d'exécution est lu dans `config/execution_profiles.json`. Il est différent
du profil stratégique lu dans `config/final_strategy_profiles.json`.

## 5. Lire la comparaison

Les indicateurs doivent être examinés ensemble :

| Indicateur | Interprétation |
|---|---|
| `forecast_core_excess_return_4w` | Surperformance prévue du cœur pour les quatre prochaines semaines |
| `forecast_core_excess_profit_4w_usd` | Même prévision appliquée aux 800 000 USD du cœur |
| `backtest_mean_net_excess_4w` | Surperformance historique moyenne après coûts |
| `backtest_win_rate` | Fréquence historique à laquelle le portefeuille bat le WLS |
| `backtest_worst_period` | Pire période historique de quatre semaines |
| `backtest_worst_max_drawdown` | Pire drawdown parmi les trajectoires testées |
| `backtest_information_ratio` | Régularité de la surperformance relative |
| `backtest_mean_one_way_turnover` | Part moyenne du portefeuille remplacée à chaque rebalancement |
| `backtest_mean_cost` | Coût moyen lié au turnover et au profil d'exécution |
| `forecast_max_weight_total` | Poids maximal d'une position dans le portefeuille total |

Un profil agressif n'est pas automatiquement meilleur parce que sa prévision est
plus élevée. Il faut vérifier son pire mois, son drawdown, sa concentration, son
turnover et la stabilité de son information ratio.

Le turnover est un taux de remplacement. Par exemple, `83 %` signifie qu'en moyenne
83 % de l'allocation change lors d'un rebalancement quatre semaines ; cela ne veut pas
dire que le portefeuille perd 83 %.

## 6. Paramètres des trois profils

Les paramètres sont centralisés dans :

```text
config/final_strategy_profiles.json
```

Configuration actuelle :

| Paramètre | Prudent | Intermédiaire | Agressif |
|---|---:|---:|---:|
| `tail_weight` | 0,50 | 0,65 | 0,75 |
| `elastic_weight` | 0,50 | 0,35 | 0,25 |
| `kappa` | 0,30 | 0,20 | 0,15 |
| `max_correlation` | 0,65 | 0,75 | 0,80 |
| `max_position_weight` | 0,12 | 0,15 | 0,20 |
| `top_n` | 50 | 40 | 30 |
| `shortlist_size` | 15 | 14 | 12 |

### Effet de chaque paramètre

| Paramètre | Si on l'augmente |
|---|---|
| `tail_weight` | Donne plus d'importance à la probabilité de faire partie du meilleur décile |
| `elastic_weight` | Donne plus d'importance à la surperformance chiffrée prévue par Elastic Net |
| `kappa` | Pénalise davantage le risque estimé par Ledoit-Wolf |
| `max_correlation` | Autorise des titres plus corrélés dans la shortlist |
| `max_position_weight` | Autorise davantage de concentration sur une position |
| `top_n` | Donne au filtre de risque un univers initial plus large |
| `shortlist_size` | Autorise davantage de titres avant l'optimisation finale |

`tail_weight + elastic_weight` doit toujours être égal à `1`.

`max_position_weight` est exprimé à l'intérieur du cœur. Comme le cœur représente
80 % du portefeuille, une limite de `0.20` autorise au maximum `16 %` du portefeuille
total sur un titre : `20 % × 80 % = 16 %`.

La configuration doit aussi permettre d'investir tout le cœur :

```text
shortlist_size × max_position_weight >= 1
```

Le code refusera automatiquement un profil invalide.

## 7. Méthode recommandée pour régler les paramètres

1. Conserver les trois profils existants comme points de référence.
2. Modifier un petit nombre de paramètres dans
   `config/final_strategy_profiles.json`.
3. Lancer la comparaison complète.
4. Comparer rendement, taux de victoire, pire période, drawdown, information ratio,
   concentration et turnover.
5. Vérifier les allocations actuelles dans `latest_core_allocations/`.
6. Éviter de choisir un réglage uniquement parce qu'il gagne sur la dernière période.
7. Une fois le profil choisi, le figer puis lancer la pipeline finale avec son nom.

Il vaut mieux modifier un paramètre à la fois. Par exemple, pour isoler l'effet de la
concentration, conserver tous les autres paramètres identiques et ne changer que
`max_position_weight`.

Ne pas ajuster les paramètres jusqu'à obtenir artificiellement le meilleur backtest.
Cela crée du surapprentissage et rend la performance future moins fiable.

## 8. Frais, slippage et stops

Les coûts et règles d'exécution sont configurés séparément dans :

```text
config/execution_profiles.json
```

Pour supprimer les frais simulés d'un profil d'exécution :

```json
{
  "commission_bps": 0,
  "slippage_bps": 0
}
```

Avec ces deux valeurs à zéro, le coût simulé du turnover est nul. Le turnover reste
néanmoins calculé et affiché : il mesure toujours la quantité de portefeuille à
remplacer.

La pipeline finale utilise `--profile sans_stop` par défaut. Changer le profil
d'exécution ne change pas les scores Elastic Net/Tail ; cela change les ordres, les
coûts simulés et éventuellement les règles de stop.

## 9. Contrôles avant d'utiliser le CSV final

Vérifier dans `run_manifest.json` :

- `strategy_profile.name` correspond au profil choisi ;
- `signal_date` vaut `2026-10-16` ;
- `planned_exit_date` vaut `2026-11-13` ;
- `challenge_aligned` vaut `true` ;
- `prices_through` et `benchmark_through` sont suffisamment récents.

Le WLS n'est pas remplacé par un proxy Yahoo. Si `benchmark_through` est plus ancien
que `prices_through`, importer le nouvel export Bloomberg avant le lancement final :

```bash
.venv/bin/python -m src.weekly_data_update
.venv/bin/python -m src.weekly_data_update --apply
```

Enfin, contrôler que :

- les allocations totalisent 100 % ;
- le cœur totalise 80 % et la poche opportuniste 20 % ;
- `data_quality` vaut `OK` pour toutes les lignes ;
- les devises, prix USD et ordres sont renseignés ;
- aucune position ne dépasse les limites du challenge.

## 10. Validation du code

Après toute modification des paramètres ou du code :

```bash
.venv/bin/ruff format --check src/strategies/final_four_week tests
.venv/bin/ruff check src/strategies/final_four_week tests
.venv/bin/pytest -q
```

