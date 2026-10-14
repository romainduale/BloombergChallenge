# Bloomberg Global Trading Challenge 2026 · ESILV

Portefeuille quantitatif long-only de 1 M$ sur les actions de l'indice Bloomberg World Large, Mid & Small Cap (WLS).

> **À lire en premier :** [`docs/guide_utilisation_pipeline.md`](docs/guide_utilisation_pipeline.md)
> explique simplement le fonctionnement complet, les résultats, le tutoriel PyCharm,
> les fichiers importants et les prochaines améliorations.

## Objectif

Le classement repose sur le rendement relatif face à l'indice WLS.

- **Objectif plancher** · battre l'indice
- **Objectif cible** · finir dans le top 5 % des équipes

## Contraintes du règlement

- Long-only, sans levier, sans ETF
- Actions membres du WLS uniquement
- 20 % maximum par position, dans l'optimiseur comme dans la couche d'exécution
- 1 M$ investi en totalité dès la première semaine
- Commissions simulées

## Ligne rouge de la stratégie

Trois briques, chacune avec un rôle unique.

| Brique | Méthode | Rôle |
|---|---|---|
| 1. Rendements | Elastic Net en coupe transversale | Classer les titres selon leur rendement relatif attendu à 5 semaines |
| 2. Covariance | Shrinkage de Ledoit-Wolf | Estimer un risque stable sur 200 à 500 titres |
| 3. Allocation | Optimisation robuste en poids actifs | Transformer prévisions et risque en poids, sous contraintes |

**Brique 1 · Elastic Net**
Un modèle commun à tous les titres, estimé sur un panel titre × semaine. Variables transformées en rangs par date (momentum 12-1, retour à la moyenne 1 mois, révisions d'analystes, surprises de résultats, volatilité, valeur, qualité). Validation walk-forward avec purge de 5 semaines. Les scores sont convertis en alphas par la formule de Grinold, α = IC × σ × z.

**Brique 2 · Ledoit-Wolf**
Covariance estimée sur un an de rendements en USD, utilisée pour mesurer la tracking error face à l'indice.

**Brique 3 · Optimisation robuste**
L'optimiseur raisonne en poids actifs (écart à l'indice), pas en poids absolus, pour éviter un biais de bêta implicite.

$$
\max_{w} \; \hat{\alpha}^{\top}(w - w_b) - \kappa \, \lVert \Omega^{1/2}(w - w_b) \rVert_2 - \gamma \, \lVert w - w_{prec} \rVert_1
$$

Avec w_b le benchmark répliqué, κ le paramètre de robustesse, γ la pénalité de rotation calée sur les commissions. Contraintes de positivité, somme à 100 %, 20 % par titre et tracking error maximale.

## Feuille de route

- [x] Prototype Elastic Net transversal avec walk-forward purgé
- [x] Prototype tail model et signal combiné
- [x] Prototype Ledoit-Wolf, filtre de corrélation et allocation long-only
- [x] Backtests sur cinq offsets et tests placebo du signal
- [ ] Requêtes BQL (composition historique du WLS, prix hebdomadaires, variables point-in-time)
- [ ] Panel réel et mesure de l'IC hors échantillon
- [ ] Rendements ajustés dans une devise commune
- [ ] Optimiseur en poids actifs avec tracking error et turnover
- [x] Backtest exploratoire avec coûts, turnover et règles d'exécution paramétrables
- [x] Ordres d'achat limite, conservation, réduction, vente et stop-loss
- [x] Audit annuel, focus 2025-2026, drawdowns et biais de données
- [x] Tests unitaires des nouvelles features et de la couche d'exécution
- [x] Template de données et procédure d'import hebdomadaire
- [x] Backtest à target 1 semaine et comparaison avec l'horizon 5 semaines
- [x] Allocation 80 % stratégie 5 semaines et 20 % poche opportuniste yfinance
- [x] Score opportuniste lisible : potentiel, risque, liquidité et justification
- [ ] Validation avec le Faculty Advisor
- [ ] Portefeuille initial prêt avant le lancement

Documentation du projet :

- [`docs/guide_utilisation_pipeline.md`](docs/guide_utilisation_pipeline.md) : guide
  simple, résultats et tutoriel ;
- [`docs/architecture_strategie.md`](docs/architecture_strategie.md) : détail technique
  et écarts entre la stratégie cible et le code ;
- [`docs/audit_execution_features.md`](docs/audit_execution_features.md) : audit détaillé
  du backtest, des stops et des features ;
- [`docs/audit_donnees.md`](docs/audit_donnees.md) : audit des données Bloomberg ;
- [`CONTRIBUTING.md`](CONTRIBUTING.md) : branches, pull requests et contrôles.

## Structure du dépôt

```
.
├── README.md
├── data/                          # exports partagés et zones de travail locales
├── src/
│   ├── elastic_net_transversal.py # brique 1
│   ├── covariance.py              # brique 2
│   ├── robust_optimizer_v1.py      # brique 3
│   ├── backtest_portfolio_v1.py
│   ├── backtest_execution_v2.py    # coûts, turnover, limites et stops
│   ├── backtest_execution_1w.py    # rebalancement chaque semaine
│   ├── refresh_feature_market_data.py # actualisation contrôlée prix/volumes
│   ├── weekly_data_update.py       # import du template hebdomadaire
│   ├── opportunistic_model.py      # score et allocation de la poche de 20 %
│   └── build_execution_plan.py     # ordres BUY/HOLD/REDUCE/SELL/SELL_STOP
├── config/execution_profiles.json  # paramètres de risque et d'exécution
├── config/portfolio_allocation.json # paramètres de l'allocation 80/20
├── docs/                          # audits et architecture de la stratégie
└── tests/                         # tests placebo et contrôles de conformité
```

## Démarrage

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest
```

La chaîne de recherche s'exécute ensuite dans cet ordre :

```bash
.venv/bin/python -m src.features
.venv/bin/python -m src.validate_elastic_net
.venv/bin/python -m src.validate_tail_model
.venv/bin/python -m src.combined_signal_v1
.venv/bin/python -m src.risk_screen_v1
.venv/bin/python -m src.validate_optimizer_v1
.venv/bin/python -m src.robust_optimizer_v1
.venv/bin/python -m src.validate_portfolio_offsets
```

La pipeline jusqu'au plan d'ordres s'exécute en une commande :

```bash
.venv/bin/python -m src.run_pipeline --skip-features
```

Pour récupérer d'abord les nouveaux prix et volumes nécessaires aux six features
de l'Elastic Net, puis produire le portefeuille cinq semaines sans stop :

```bash
.venv/bin/python -m src.run_pipeline --refresh-market-data --profile sans_stop
```

Le téléchargement Yahoo est contrôlé sur les jours communs avec Bloomberg. Un
titre dont le mapping ne recoupe pas l'historique est ignoré et signalé dans
`data/processed/data_refresh/yahoo_feature_refresh.csv`. Le script ne remplace
jamais le WLS par un proxy : la série du benchmark reste à actualiser depuis
Bloomberg.

La recherche hebdomadaire et sa comparaison avec la stratégie 5 semaines se lancent
avec :

```bash
.venv/bin/python -m src.run_weekly_research
```

Le template pour les données Bloomberg et les champs non disponibles sur Yahoo se trouve dans
[`data/templates/weekly_data_template.xlsx`](data/templates/weekly_data_template.xlsx).

Une fois les données Bloomberg importées, la stratégie 80/20 et son plan d'ordres
se lancent avec :

```bash
.venv/bin/python -m src.run_pipeline --opportunistic
```

Ce lancement génère également deux exports simplifiés :

- `data/processed/opportunistic/core_80_clean.csv` pour la poche cœur de 80 % ;
- `data/processed/opportunistic/opportunistic_20_clean.csv` pour la poche
  opportuniste de 20 %.

Ils contiennent les titres retenus, leur devise, l'allocation en pourcentage et en
dollars, les prix locaux et convertis en dollars, le score et la surperformance
estimée à cinq semaines. Cette estimation est relative au benchmark et ne constitue
pas une promesse de rendement.

Les 80 % utilisent la stratégie cinq semaines sans stop. Les 20 % restants sont
répartis sur quatre titres distincts, à 5 % chacun, après un filtre yfinance sur le
momentum, le risque, le drawdown et la liquidité. Cette poche opportuniste est une
première règle de sélection : elle doit encore recevoir son propre backtest avant
d'être considérée comme validée.

Le profil par défaut n'active pas le stop-loss, car son test historique n'améliore
pas encore le couple rendement/drawdown. Les variantes restent disponibles dans
`config/execution_profiles.json`. Voir
[`docs/audit_execution_features.md`](docs/audit_execution_features.md) pour les
résultats annuels, le focus 2025-2026 et le test des features candidates.

Les résultats sont écrits dans `data/processed/` et ne sont pas versionnés.

## Garde-fous

1. **Pas de fuite de données.** Toute variable doit être connue à la date t. Le test placebo (données sans signal) doit donner un IC proche de zéro.
2. **IC réaliste.** Un IC compris entre 0,02 et 0,05 est normal. Au-delà de 0,08, chercher la fuite avant de s'en réjouir.
3. **Indicateurs du backtest.** Probabilité de battre l'indice et probabilité de dépasser +10 % relatif, pas le ratio de Sharpe.
4. **Règles figées.** Les paramètres sont fixés avant le lancement et ne changent pas pendant le challenge, sauf erreur avérée.

## Points ouverts avec le Faculty Advisor

- Calibrage du paramètre de robustesse κ face à un signal faible
- Pilotage dynamique de la tracking error (CPPI relatif à cliquet)
- Ajustement du bêta selon un signal de tendance sur l'indice
- Barème exact des commissions et règles 2026 sur le cash

La stratégie pourra évoluer après ces échanges. Toute modification de la ligne rouge est consignée dans ce fichier.
