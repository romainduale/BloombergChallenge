# Guide simple de la stratégie et de la pipeline

Ce document est le point de départ pour comprendre, lancer et améliorer le projet.
Il décrit ce que fait réellement le code aujourd'hui, les résultats obtenus, les
limites connues et les prochaines étapes avant une utilisation réelle.

## 1. Résumé en une minute

La stratégie cherche des actions capables de battre l'indice Bloomberg World Large,
Mid & Small Cap (`WLS`) pendant les cinq semaines suivantes.

Le processus est le suivant :

```text
Prix, volumes et indice WLS
          ↓
Features calculées chaque semaine
          ↓
Elastic Net + modèle Tail
          ↓
Classement des actions
          ↓
Top 30 puis filtre de risque Ledoit-Wolf
          ↓
Shortlist de 12 actions
          ↓
Optimisation des poids, 20 % maximum par action
          ↓
Backtest avec coûts et turnover
          ↓
Fichier d'ordres à examiner
```

La stratégie est aujourd'hui un prototype de recherche fonctionnel. Elle peut produire
un portefeuille et un plan d'ordres, mais ces ordres ne doivent pas encore être envoyés
réellement : il manque notamment les conversions de devises, des prix ajustés vérifiés
et un univers historique point-in-time.

## 2. Ce qui a été ajouté

Le signal V1 existant a été conservé. La seule modification directe de son allocation
est le passage du plafond par action de 18 % à 20 %.

Les nouvelles briques ont été construites autour de cette V1 :

- profils d'exécution modifiables dans un seul fichier JSON ;
- calcul du turnover et des coûts de transaction ;
- backtest sur cinq calendriers avec suivi des positions ;
- comparaison sans stop, stop fixe et stop lié à la volatilité ;
- ordres `BUY`, `INCREASE`, `HOLD`, `REDUCE`, `SELL` et `SELL_STOP` ;
- prix limite d'achat et durée de validité ;
- audit annuel, focus 2025-2026, drawdowns, meilleures et pires périodes ;
- détection explicite des biais de données ;
- test des features proposées dans le classeur externe ;
- pipeline unique allant du signal jusqu'au fichier d'ordres ;
- 36 tests automatiques et contrôles de style exécutés localement.

## 3. Comment le signal est construit

### Étape A — Features hebdomadaires

Les prix et volumes quotidiens sont ramenés au vendredi. La V1 utilise :

- momentum à 1 mois ;
- momentum à 3 mois ;
- momentum à 6 mois ;
- volatilité sur 13 semaines ;
- volume anormal sur 13 semaines ;
- distance au plus haut des 52 dernières semaines.

Chaque valeur est convertie en rang entre 0 et 1 à la date concernée. Cette
transformation permet de comparer des actions et des marchés ayant des unités très
différentes.

La cible est la performance future de l'action sur cinq semaines moins celle du WLS
sur la même période.

### Étape B — Elastic Net

L'Elastic Net estime la surperformance relative future. Il est entraîné sur trois ans
glissants, avec une purge de cinq semaines avant chaque date test.

La régularisation L1/L2 limite les coefficients trop instables. La qualité du classement
est mesurée avec l'Information Coefficient de Spearman, appelé `IC`.

### Étape C — Modèle Tail

Le modèle Tail estime la probabilité qu'une action termine dans les 10 % meilleures
actions au cours des cinq semaines suivantes.

Le score utilisé pour classer les actions est :

```text
75 % du rang Tail + 25 % du rang Elastic Net
```

Les 30 meilleurs scores passent à l'étape de risque.

### Étape D — Covariance Ledoit-Wolf

Pour les 30 candidats, le code calcule les rendements hebdomadaires relatifs au WLS
sur les 52 dernières semaines. Ledoit-Wolf stabilise la matrice de covariance afin
d'éviter de sur-réagir à des corrélations historiques trop bruitées.

Un titre est ensuite écarté si sa corrélation absolue avec un titre déjà sélectionné
dépasse 0,80. Le résultat est une shortlist allant jusqu'à 12 actions.

### Étape E — Optimisation des poids

L'optimiseur cherche un compromis entre alpha prévu et risque relatif :

```text
score = alpha prévu − 0,15 × risque estimé à cinq semaines
```

Contraintes actuelles :

- portefeuille long-only ;
- somme des poids égale à 100 % ;
- pas de levier ;
- 20 % maximum par action.

Le Tail sert à construire la shortlist. L'alpha utilisé par l'optimiseur vient ensuite
de l'Elastic Net.

## 4. Comment lire le résultat final actuel

Le dernier portefeuille généré utilise le signal du 2 octobre 2026 et les derniers prix
disponibles au 7 octobre 2026.

| Indicateur | Valeur | Interprétation simple |
|---|---:|---|
| Positions supérieures à 0,5 % | 10 | Dix positions portent réellement le portefeuille |
| Poids maximum | 15,10 % | Le plafond de 20 % est respecté |
| Somme des poids | 100,00 % | Tout le capital est investi |
| Alpha relatif prévu à 5 semaines | +3,32 % | Surperformance prédite face au WLS, non garantie |
| Risque relatif estimé à 5 semaines | 13,35 % | Incertitude élevée autour de la performance relative |
| Tracking error annualisée indicative | 43,06 % | Portefeuille actuellement très éloigné du WLS |
| Score robuste | 1,32 % | `3,32 % − 0,15 × 13,35 %` |

Le score robuste sert à comparer plusieurs allocations possibles. Il ne signifie pas
que le portefeuille gagnera 1,32 % ou 3,32 % avec certitude.

La tracking error de 43,06 % est élevée. Une contrainte explicite de tracking error
fait partie des prochaines améliorations prioritaires.

## 5. Résultats du modèle et des features

Sur l'échantillon commun utilisé pour comparer les variantes :

| Modèle | IC Elastic Net | IC combiné | AUC Tail | Précision top 10 % |
|---|---:|---:|---:|---:|
| V1 actuelle | 0,1001 | 0,1157 | 0,7342 | 27,63 % |
| V1 + révision EPS | 0,1019 | 0,1167 | 0,7358 | 27,69 % |
| V1 + IVOL | 0,0993 | 0,1097 | 0,7477 | 28,79 % |
| V1 + IVOL + EPS | 0,1016 | 0,1113 | 0,7487 | 29,01 % |
| V2 complète | 0,0872 | 0,1067 | 0,7466 | 28,09 % |

La V2 complète n'améliore pas le signal combiné. La V1 reste donc la stratégie de
référence. EPS et IVOL restent des expériences intéressantes, mais elles ne sont pas
activées automatiquement.

Un IC supérieur à 0,08 est inhabituellement élevé. Il faut d'abord rechercher une
fuite ou un biais de données avant de conclure que le modèle est exceptionnel.

## 6. Comment le backtest fonctionne

À chaque date historique, le code recommence tout le processus :

1. entraînement sur les trois années précédentes ;
2. purge des cinq dernières semaines ;
3. nouvelles prédictions Elastic Net et Tail ;
4. nouveau top 30 ;
5. nouvelle covariance Ledoit-Wolf ;
6. nouvelle shortlist ;
7. nouvelle optimisation ;
8. mesure des cinq semaines suivantes ;
9. dérive des positions avant le rebalancement suivant ;
10. déduction des coûts de transaction.

Le test est répété sur cinq calendriers de départ, appelés `offsets`. Les périodes sont
non chevauchantes au sein d'un offset, mais les cinq offsets se chevauchent entre eux.
Les 304 observations ne doivent donc pas être composées dans une seule courbe.

### Turnover et coûts

Le turnover one-way mesure la part du portefeuille remplacée lors d'un rebalancement.
Un turnover de 100 % signifie que l'équivalent du portefeuille entier a été renouvelé.

Les coûts sont calculés ainsi :

```text
notionnel échangé × (commission + slippage) / 10 000
```

Le scénario de référence utilise 10 points de base de commission et 5 points de base
de slippage.

### Résultats des règles de stop

| Variante | Excès net moyen à 5 semaines | Taux de victoire | Turnover | Coût moyen | Pire drawdown |
|---|---:|---:|---:|---:|---:|
| Sans stop, défaut | +2,94 % | 64,80 % | 87,13 % | 0,259 % | −39,86 % |
| Stop fixe 8 % | +1,61 % | 57,24 % | 95,16 % | 0,283 % | −38,32 % |
| Stop volatilité | +1,81 % | 57,24 % | 92,95 % | 0,275 % | −41,37 % |

Le stop est désactivé par défaut car il ne présente pas encore un meilleur compromis
rendement/drawdown. Son code reste disponible pour de nouveaux tests.

### Focus 2025-2026

- 2025 : rendement relatif net moyen de +64,93 % entre les cinq offsets ;
- 2026 partiel : +32,02 % ;
- meilleure période de cinq semaines : +33,74 % d'excès net ;
- pire période : −24,34 %.

Ces niveaux sont anormalement élevés. Ils doivent être considérés comme exploratoires,
pas comme une promesse de performance.

## 7. Limites connues des données

| Sujet | Situation actuelle | Conséquence possible |
|---|---|---|
| Univers historique | 1 262 titres historiques contre 10 420 au snapshot | Survivorship bias |
| Poids WLS couvert | 84,17 % | Une partie du benchmark n'est pas représentée |
| Prix et volumes | Couverture moyenne de 64,51 % | Sélection des titres les mieux renseignés |
| EPS mensuel | Couverture moyenne de 82,66 % | Échantillon plus réduit pour les tests EPS |
| Devises | Pas encore de conversion quotidienne en USD | Rendements et quantités non comparables |
| Prix ajustés | Dividendes et splits non documentés | Rendements historiques potentiellement faux |
| Univers point-in-time | Pas encore disponible | Titres disparus insuffisamment représentés |

Pour cette raison, la colonne `estimated_shares` du fichier d'ordres reste vide avec
le statut `FX_REQUIRED`. Le code refuse implicitement de transformer des dollars en
actions japonaises ou coréennes sans taux de change.

## 8. Mini tutoriel avec PyCharm

### Première vérification

Dans PyCharm, vérifier :

- que le projet ouvert est `bloomberg-trading-challenge-quant-lab` ;
- que l'interpréteur est `.venv/bin/python` sur macOS/Linux ou
  `.venv\Scripts\python.exe` sous Windows ;
- que le terminal est ouvert à la racine du projet.

Tant que la pull request n'est pas fusionnée, sélectionner la branche :

```text
codex/feature/backtest-execution-audit
```

### Lancement rapide

Si les features ont déjà été construites :

```bash
.venv/bin/python -m src.run_pipeline --skip-features
```

Sous Windows :

```powershell
.venv\Scripts\python.exe -m src.run_pipeline --skip-features
```

La pipeline recalcule le signal, le risque, le portefeuille et les ordres.

### Reconstruction complète

Pour reconstruire également les features V1 :

```bash
.venv/bin/python -m src.run_pipeline
```

### Où lire le résultat

Ouvrir dans PyCharm :

```text
data/processed/execution/execution_orders.csv
```

Sans positions actuelles, la pipeline considère que le portefeuille part de 100 % cash
et propose principalement des achats.

### Utiliser des positions existantes

Créer `data/current_positions.csv` :

```csv
id,weight,entry_price
TTMI UW Equity,0.12,120.50
ALAB UW Equity,0.15,350.00
RKLB UW Equity,0.08,68.00
```

`0.12` signifie 12 % du portefeuille. Puis lancer :

```bash
.venv/bin/python -m src.run_pipeline --skip-features \
  --current-positions data/current_positions.csv
```

Le fichier d'ordres pourra alors contenir :

- `BUY` : nouvelle position ;
- `INCREASE` : augmentation ;
- `HOLD` : aucune modification ;
- `REDUCE` : diminution ;
- `SELL` : sortie complète ;
- `SELL_STOP` : stop franchi si un profil de stop est activé.

### Tester un stop expérimental

```bash
.venv/bin/python -m src.run_pipeline --skip-features \
  --current-positions data/current_positions.csv \
  --profile equilibre
```

Le profil par défaut reste `sans_stop`.

### Créer une configuration ▶ dans PyCharm

Dans `Run > Edit Configurations`, créer une configuration Python :

| Champ | Valeur |
|---|---|
| Run | Module name |
| Module | `src.run_pipeline` |
| Parameters | `--skip-features` |
| Working directory | racine du dépôt |
| Interpreter | environnement `.venv` du dépôt |

Il suffit ensuite de cliquer sur ▶.

## 9. Où trouver chaque élément

### Documentation

| Fichier | Contenu |
|---|---|
| `README.md` | Présentation courte du projet et commandes principales |
| `docs/guide_utilisation_pipeline.md` | Ce guide, à lire en premier |
| `docs/architecture_strategie.md` | Architecture technique et écart entre cible et code réel |
| `docs/audit_execution_features.md` | Résultats détaillés du backtest, stops et features |
| `docs/audit_donnees.md` | Audit des exports Bloomberg |
| `CONTRIBUTING.md` | Branches, pull requests, tests et règles de collaboration |

### Code principal

| Fichier | Rôle |
|---|---|
| `src/features.py` | Features V1 et cible à cinq semaines |
| `src/features_v2.py` | Features expérimentales |
| `src/elastic_net_transversal.py` | Modèle Elastic Net |
| `src/tail_model_v1.py` | Modèle Tail top 10 % |
| `src/combined_signal_v1.py` | Combinaison 75 % Tail / 25 % Elastic Net |
| `src/covariance.py` | Estimateur Ledoit-Wolf |
| `src/risk_screen_v1.py` | Top 30, covariance et shortlist de 12 |
| `src/robust_optimizer_v1.py` | Optimisation des poids |
| `src/backtest_execution_v2.py` | Backtest avec coûts, turnover et stops |
| `src/audit_backtest.py` | Résultats annuels, drawdowns et biais |
| `src/execution_rules.py` | Règles BUY/HOLD/REDUCE/SELL/SELL_STOP |
| `src/build_execution_plan.py` | Création du fichier d'ordres |
| `src/run_pipeline.py` | Commande unique de la pipeline |
| `config/execution_profiles.json` | Paramètres modifiables d'exécution |

### Résultats générés localement

Ces fichiers sont ignorés par Git et doivent être reconstruits sur chaque machine.

| Chemin | Contenu |
|---|---|
| `data/processed/features_weekly_v1.csv.gz` | Panel de features V1 |
| `data/processed/combined_signal/latest_combined_signal_v1.csv` | Classement actuel |
| `data/processed/risk_screen/shortlist_v1.csv` | Shortlist après filtre de risque |
| `data/processed/portfolio/portfolio_robust_v1.csv` | Poids cibles |
| `data/processed/execution/execution_orders.csv` | Ordres proposés |
| `data/processed/execution_backtest/` | Backtests et audits locaux |
| `data/processed/feature_comparison_v2/` | Comparaison V1/V2 |

### Tests

Les tests sont dans `tests/`. Pour tout vérifier :

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
```

GitHub Actions relance également ces contrôles à chaque pull request.

## 10. Ce qu'il reste à améliorer

Ajouter des features n'est pas la priorité immédiate. Les quatre chantiers suivants ont
plus d'impact sur la fiabilité du résultat.

### Priorité 1 — Corriger les données

- récupérer les compositions WLS historiques point-in-time ;
- inclure les entreprises sorties ou radiées ;
- convertir tous les prix et rendements en USD ;
- utiliser des prix total-return ajustés et vérifiés ;
- conserver les dates exactes de publication des données fondamentales ;
- définir une politique explicite pour les données manquantes.

### Priorité 2 — Compléter l'optimiseur

- optimiser les poids actifs par rapport aux poids du WLS ;
- imposer une tracking error maximale ;
- intégrer les positions actuelles dans l'optimisation ;
- pénaliser directement le turnover ;
- ajouter des contraintes secteur, pays, bêta et liquidité ;
- calibrer l'alpha à partir d'un IC réaliste.

### Priorité 3 — Rendre l'exécution réaliste

- récupérer les prix high/low pour calculer un vrai ATR ;
- intégrer les ordres limites aux rendements du backtest ;
- simuler les ordres non remplis, remplissages partiels et le cash restant ;
- intégrer bid-ask spreads, tailles minimales et round lots ;
- appliquer les coûts et règles exactes du challenge par marché.

### Priorité 4 — Valider et préparer le suivi live

- réserver une période finale jamais utilisée pour choisir les paramètres ;
- tester plusieurs régimes de marché et scénarios de crise ;
- créer des intervalles de confiance par bootstrap temporel ;
- figer les paramètres avant le début du challenge ;
- importer automatiquement les positions réelles ;
- suivre cash, devises, exécutions et dépassements de contraintes ;
- produire un rapport quotidien ou hebdomadaire reproductible.

## 11. Conditions minimales avant de passer de la recherche au réel

La stratégie ne devrait être considérée prête que lorsque :

- l'univers historique est point-in-time ;
- les rendements sont ajustés et exprimés en USD ;
- la tracking error est plafonnée ;
- le turnover est pénalisé dans l'optimiseur ;
- les ordres limites et le cash sont réellement simulés ;
- les coûts officiels du challenge sont intégrés ;
- la période finale hors échantillon confirme le résultat ;
- les paramètres ont été gelés et validés par l'équipe.

En attendant, le fichier d'ordres est un outil de recherche et de discussion, pas une
instruction automatique de trading.
