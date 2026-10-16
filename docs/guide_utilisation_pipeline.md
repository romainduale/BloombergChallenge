# Guide rapide de la pipeline

Pour le mode d'emploi détaillé de la stratégie finale, des trois profils de risque et
de leur comparaison, voir
[`guide_pipeline_finale_4_semaines.md`](guide_pipeline_finale_4_semaines.md).

## Pipeline finale du challenge : 16 octobre → 13 novembre

Le cœur de 80 % utilise désormais une cible de quatre semaines. La poche
opportuniste de 20 % conserve ses règles et ses paramètres. Après la clôture du
vendredi 16 octobre 2026, lancer :

```bash
.venv/bin/python -m src.strategies.final_four_week.pipeline \
  --refresh-market-data \
  --data-end 2026-10-16 \
  --require-signal-date 2026-10-16
```

L'option `--require-signal-date` empêche de produire par erreur le portefeuille avec
le signal périmé du 9 octobre. Le fichier final est
`data/processed/strategies/final_four_week/final_allocation_explained.csv`.

Chaque ligne affiche notamment `elastic_net_score`, `tail_score`, leurs rangs, les
six features, les bêta standardisés et les contributions par feature. Les bêta sont
communs à tous les titres à une date donnée ; les contributions changent selon les
features du titre et expliquent donc plus directement sa sélection.
Pour le modèle Tail, ces contributions sont sur l'échelle des log-odds, avant la
conversion finale en probabilité.

Le backtest quatre semaines sans stop produit 307 périodes sur quatre offsets :
surperformance nette moyenne de +2,17 % par période, taux de victoire de 62,87 %,
turnover one-way moyen de 83,35 % et coût moyen de 0,248 %. Ces chiffres restent
exploratoires avec les mêmes limites de données que les backtests historiques.

## Objectif

La stratégie finale cherche les actions qui pourraient battre l'indice Bloomberg
WLS au cours des quatre semaines suivantes, puis construit un portefeuille de 1 M$.
Les horizons une et cinq semaines restent conservés comme expériences comparatives.

```text
Données → Features → Modèles → Risque → Portefeuille → Backtest → Ordres
```

## Ce qui a été ajouté

- plafond de 20 % maximum par action ;
- coûts de transaction et slippage réglables ;
- calcul du turnover du portefeuille ;
- backtest sur cinq calendriers différents ;
- résultats annuels, drawdown, taux de victoire, meilleures et pires périodes ;
- comparaison sans stop, stop fixe et stop lié à la volatilité ;
- ordres `BUY`, `INCREASE`, `HOLD`, `REDUCE`, `SELL` et `SELL_STOP` ;
- achats avec prix limite et durée de validité ;
- pipeline unique allant des features au fichier d'ordres ;
- template Excel pour actualiser toutes les données chaque semaine ;
- target et backtest séparés à une semaine, sans offsets ;
- comparaison normalisée entre détention 1 semaine et 5 semaines ;
- allocation finale de 80 % sur la stratégie quatre semaines et 20 % sur une poche
  opportuniste yfinance inchangée ;
- score opportuniste expliquant le potentiel, le risque, la liquidité et les raisons
  de chaque sélection ;
- tests automatiques et documentation des limites des données.

Les stratégies historiques n'ont pas été écrasées. Elles sont exposées à côté de la
version finale dans `src/strategies/`.

## Comment la stratégie fonctionne

### 1. Target

La target apprise par le modèle est :

```text
rendement futur de l'action à 4 semaines
− rendement futur du WLS à 4 semaines
```

Le modèle cherche donc une surperformance relative et pas uniquement une hausse du
cours de l'action.

### 2. Features utilisées actuellement

- momentum 1 mois ;
- momentum 3 mois ;
- momentum 6 mois ;
- volatilité 13 semaines ;
- volume anormal 13 semaines ;
- distance au plus haut des 52 semaines.

Ces six variables sont recalculées à partir de deux historiques seulement : le
prix de clôture et le volume quotidien. Elles ne dépendent pas des facteurs
fondamentaux du snapshot pour produire le classement actuel.

### 3. Modèles

Deux modèles classent les actions :

- l'Elastic Net prévoit leur surperformance relative ;
- le modèle Tail estime leur probabilité de terminer dans les 10 % meilleures.

Le score final utilise 75 % du rang Tail et 25 % du rang Elastic Net.

### 4. Risque et portefeuille

- les 30 meilleures actions sont conservées ;
- Ledoit-Wolf estime leurs risques et corrélations sur 52 semaines ;
- les titres trop corrélés sont écartés ;
- une shortlist de 12 actions maximum est créée ;
- l'optimiseur choisit les poids avec une limite de 20 % par action.

### 5. Allocation 80/20

Le mode opportuniste conserve la stratégie principale et sépare le portefeuille en
deux poches :

- 80 % pour le portefeuille final quatre semaines issu des modèles ;
- 20 % pour quatre opportunités distinctes, avec 5 % maximum par titre.

La poche opportuniste part des meilleurs signaux de la pipeline puis utilise les prix
ajustés et volumes récupérés par yfinance. Son score combine :

- potentiel : momentum 20 et 60 séances, proximité du plus haut annuel, alpha du
  modèle principal et objectif analystes lorsqu'il est disponible ;
- risque : volatilité 20 séances, risque baissier et drawdown 60 séances ;
- liquidité : montant moyen échangé en USD grâce aux taux FX.

Le résultat contient aussi un niveau de risque et une justification textuelle. Ce
score est une règle transparente, pas un nouveau modèle entraîné. Il n'a pas encore
de backtest dédié et ne doit donc pas être interprété comme une prévision garantie.
Les historiques téléchargés, l'univers évalué, les scores et l'allocation sont
conservés dans `data/processed/opportunistic/` pour pouvoir contrôler chaque calcul.

## Features testées mais pas activées

Les features suivantes ont été calculées et comparées à la V1 :

- ratio de Sortino ;
- révision d'EPS ;
- momentum résiduel ;
- Frog-in-the-Pan momentum ;
- volatilité idiosyncratique, ou IVOL ;
- illiquidité d'Amihud.

La distance au plus haut des 52 semaines existait déjà dans la V1.

La V2 complète n'a pas amélioré le score global. La révision d'EPS apporte un petit
gain et IVOL aide surtout le modèle Tail, mais ce n'est pas assez clair pour modifier
la stratégie principale. Ces features restent donc expérimentales.

## Résultats des backtests

Le backtest réentraîne les modèles à chaque date uniquement avec le passé, reconstruit
le portefeuille, puis observe les cinq semaines suivantes. Il est répété sur cinq
calendriers de départ différents.

| Variante | Excès net moyen sur 5 semaines | Taux de victoire | Turnover | Coût moyen |
|---|---:|---:|---:|---:|
| Sans stop | +2,94 % | 64,80 % | 87,13 % | 0,259 % |
| Stop fixe 8 % | +1,61 % | 57,24 % | 95,16 % | 0,283 % |
| Stop volatilité | +1,81 % | 57,24 % | 92,95 % | 0,275 % |

Le stop-loss est disponible, mais désactivé par défaut car les deux variantes testées
ont réduit la performance sans améliorer suffisamment le drawdown.

Un second backtest à une semaine est maintenant disponible. Il ne réutilise pas la
target à cinq semaines : les modèles sont réentraînés pour prévoir la surperformance
de la semaine suivante. Le portefeuille est recalculé chaque vendredi et détenu
jusqu'au vendredi suivant. Il forme une seule trajectoire séquentielle, sans cinq
calendriers décalés.

### Comparaison 1 semaine contre 5 semaines

La comparaison est faite du 6 novembre 2020 au 2 octobre 2026, sur la même fenêtre
historique et avec le profil sans stop.

| Mesure | Rebalancement 1 semaine | Conservation 5 semaines |
|---|---:|---:|
| Périodes testées | 308 semaines | 304 périodes sur 5 trajectoires |
| Excès net moyen par période | +0,40 % | +2,94 % |
| Taux de victoire | 54,22 % | 64,79 % |
| Rendement relatif équivalent sur 5 semaines | +1,51 % | +2,49 % |
| Turnover one-way annualisé | 2 916 % | 906 % |
| Coûts annualisés indicatifs | 8,75 % | 2,69 % |
| Information ratio annualisé | 0,77 | 1,23 |
| Drawdown maximal moyen des trajectoires | -47,16 % | -35,84 % |

Le rebalancement hebdomadaire conserve un signal positif, mais il augmente fortement
le turnover et les coûts. Il réduit aussi le taux de victoire et dégrade le drawdown.
La détention cinq semaines reste donc la stratégie principale. Le backtest une semaine
reste disponible pour tester de futures améliorations sans modifier la stratégie de
référence.

### Afficher les deux stratégies dans les graphiques

Après avoir lancé `.venv/bin/python -m src.run_weekly_research`, exécuter depuis la
racine du projet :

```bash
.venv/bin/python scripts/plot_execution_results.py
.venv/bin/python scripts/plot_offsets.py
.venv/bin/python scripts/plot_wls_strategies.py
```

- `plot_execution_results.py` compare les indicateurs : rendement relatif, taux de
  victoire, turnover, coûts, drawdown et information ratio ;
- `plot_offsets.py` affiche les cinq calendriers décalés de la stratégie cinq semaines,
  leur moyenne et la stratégie une semaine continue ;
- `plot_wls_strategies.py` compare les deux stratégies au WLS, en valeur puis en
  performance relative.

La courbe « 5 semaines sans stop » est la moyenne normalisée des cinq calendriers
décalés. La courbe « 1 semaine » est une seule trajectoire rééquilibrée chaque semaine.
Fermer une fenêtre graphique pour afficher la suivante lorsqu'un script produit
plusieurs graphiques.

Ces résultats sont encore exploratoires. Les données historiques contiennent notamment
un biais de survivance, des devises non converties et des prix dont l'ajustement n'est
pas encore totalement vérifié.

## Ordres produits par la pipeline

La pipeline compare le portefeuille cible aux positions actuelles :

- `BUY` : acheter une nouvelle position ;
- `INCREASE` : augmenter une position ;
- `HOLD` : ne rien faire ;
- `REDUCE` : réduire la position ;
- `SELL` : vendre toute la position ;
- `SELL_STOP` : vendre après déclenchement du stop.

Sans fichier de positions actuelles, elle suppose que le portefeuille part entièrement
en cash et propose principalement des achats.

Les quantités d'actions restent marquées `FX_REQUIRED` tant que `currency` dans le
snapshot et `usd_rate` dans l'onglet FX ne sont pas disponibles. Le taux attendu est
le nombre de dollars pour une unité de devise locale ; le taux USD vaut 1.

## Comment lancer la pipeline

Dans le terminal PyCharm, à la racine du projet :

```bash
.venv/bin/python -m src.run_pipeline --skip-features
```

Pour tout recalculer, y compris les features :

```bash
.venv/bin/python -m src.run_pipeline
```

Pour produire l'allocation 80/20, télécharger les données yfinance et générer les
ordres combinés :

```bash
.venv/bin/python -m src.run_pipeline --opportunistic
```

Si les données d'objectifs analystes sont trop lentes ou indisponibles :

```bash
.venv/bin/python -m src.run_pipeline --opportunistic --skip-analysts
```

Le fichier final se trouve ici :

```text
data/processed/execution/execution_orders.csv
```

## Mise à jour hebdomadaire des données

### Prix et volumes des features Elastic Net

Les historiques Bloomberg s'arrêtaient au 7 octobre 2026. La mise à jour Yahoo du
14 octobre 2026 a validé 1 186 des 1 262 titres par comparaison des cours sur les
jours de chevauchement. Cela représente 97,6 % du poids de l'échantillon historique
et 82,1 % du poids total du WLS au snapshot. Les 76 symboles non recoupés restent
inchangés et figurent dans le rapport de contrôle.

Pour les prochaines mises à jour :

```bash
.venv/bin/python -m src.refresh_feature_market_data
```

La commande repart de la dernière date locale, télécharge les clôtures non ajustées
et volumes par lots, contrôle chaque symbole, puis écrit le détail dans
`data/processed/data_refresh/yahoo_feature_refresh.csv`.

Le WLS n'est pas disponible sous une série Yahoo équivalente vérifiable. Il reste
donc arrêté au 7 octobre 2026 tant qu'un nouvel export Bloomberg n'est pas importé.
Le calcul de covariance utilise automatiquement la dernière date commune aux
actions et au WLS ; aucune valeur de benchmark n'est inventée.

### Données Bloomberg, snapshot et WLS

Le fichier `data/templates/weekly_data_template.xlsx` contient :

- une zone pour coller ou corriger les prix et volumes quotidiens ;
- une zone pour les nouveaux niveaux quotidiens du WLS ;
- les 44 colonnes du snapshot Bloomberg, dont `currency` et `yahoo_ticker` ;
- un onglet FX prérempli avec les devises à compléter ;
- un dictionnaire indiquant les champs et requêtes Bloomberg ;
- un univers opportuniste de départ avec les symboles Yahoo à vérifier ;
- le catalogue des features actives, expérimentales et opportunistes.

Les cellules jaunes sont les seules zones à renseigner. Les feuilles de données sont
volontairement vides : il faut y coller les nouveaux exports Bloomberg, sans renommer
les colonnes. Ajouter toutes les séances postérieures à la dernière date présente,
selon le calendrier local de chaque titre.

Valider d'abord le fichier sans modifier les données :

```bash
.venv/bin/python -m src.weekly_data_update
```

Après validation, importer les nouvelles données :

```bash
.venv/bin/python -m src.weekly_data_update --apply
```

L'option `--apply` est volontairement obligatoire. Sans elle, aucun fichier source
n'est modifié.

## Backtest hebdomadaire et comparaison

Après une mise à jour des données, recalculer les deux horizons et leur comparaison :

```bash
.venv/bin/python -m src.run_weekly_research
```

Pour tester seulement l'horizon une semaine en conservant le résultat cinq semaines
déjà présent :

```bash
.venv/bin/python -m src.run_weekly_research --reuse-five-week
```

La comparaison utilise la même fenêtre historique et annualise les rendements, la
volatilité, le turnover et les coûts. Elle se trouve dans
`data/processed/execution_backtest/horizon_comparison/`.

## Lancer la stratégie cinq semaines sans stop

`sans_stop` signifie « sans stop-loss ». Il ne faut pas laisser un processus Python
tourner pendant cinq semaines. La pipeline est lancée une fois au rebalancement,
puis les positions remplies sont conservées jusqu'à la prochaine date de
rebalancement.

Pour un premier investissement depuis le cash :

```bash
.venv/bin/python -m src.run_pipeline --refresh-market-data --profile sans_stop
```

Si les données viennent déjà d'être actualisées :

```bash
.venv/bin/python -m src.run_pipeline --skip-features --profile sans_stop
```

Vérifier ensuite `data/processed/execution/execution_orders.csv` avant de saisir les
ordres. Le profil `sans_stop` utilise des achats limites valables trois jours et ne
produit aucun prix de stop. Les quantités restent `FX_REQUIRED` tant que les devises
et taux USD ne sont pas renseignés.

La date de sortie ou rebalancement est la date du signal plus cinq semaines. Avec le
signal actuel du vendredi 9 octobre 2026, la prochaine date théorique est le vendredi
13 novembre 2026. Un achat réalisé le 14 octobre subit toutefois trois séances de
retard par rapport au backtest. Pour une exécution strictement alignée, actualiser les
données après la clôture du vendredi 16 octobre, exécuter le nouveau signal, puis
conserver le portefeuille jusqu'au vendredi 20 novembre.

Au rebalancement suivant, fournir les positions réellement remplies :

```bash
.venv/bin/python -m src.run_pipeline \
  --refresh-market-data \
  --profile sans_stop \
  --current-positions data/current_positions.csv
```

Le fichier de positions contient `id`, `weight` et `entry_price`. Le poids est une
fraction du portefeuille, par exemple `0.08` pour 8 %. Conserver le prix réellement
exécuté dans `entry_price` afin de garder une trace d'exécution propre.

## Fichiers importants

| Fichier | Rôle |
|---|---|
| `src/features.py` | Features et target |
| `src/elastic_net_transversal.py` | Modèle Elastic Net |
| `src/tail_model_v1.py` | Modèle Tail |
| `src/risk_screen_v1.py` | Ledoit-Wolf et shortlist |
| `src/robust_optimizer_v1.py` | Poids du portefeuille |
| `src/backtest_execution_v2.py` | Backtest avec coûts et stops |
| `src/features_weekly_1w.py` | Target relative à une semaine |
| `src/refresh_feature_market_data.py` | Prix/volumes Yahoo contrôlés pour les features actives |
| `src/backtest_execution_1w.py` | Backtest et rebalancement hebdomadaires |
| `src/compare_backtest_horizons.py` | Comparaison 1 semaine contre 5 semaines |
| `src/weekly_data_update.py` | Validation et import du template hebdomadaire |
| `src/run_weekly_research.py` | Recalcul complet des deux horizons |
| `src/opportunistic_model.py` | Score yfinance et poche opportuniste de 20 % |
| `src/execution_rules.py` | Règles d'achat et de vente |
| `src/run_pipeline.py` | Commande principale |
| `config/execution_profiles.json` | Paramètres modifiables |
| `config/portfolio_allocation.json` | Poids 80/20, nombre de titres et filtres opportunistes |

## Ce qu'il reste à faire

La base de la pipeline est prête. Avant de l'utiliser avec des ordres réels, il reste
principalement à :

1. connecter des données actualisées et un univers WLS historique fiable ;
2. convertir tous les prix et rendements en USD ;
3. vérifier les prix ajustés des dividendes et splits ;
4. ajouter une limite de tracking error et une pénalité de turnover dans l'optimiseur ;
5. intégrer réellement les ordres limites, le cash et les remplissages au backtest ;
6. appliquer les coûts et règles exactes du challenge ;
7. lancer une dernière validation hors échantillon puis figer les paramètres.
8. backtester séparément la poche opportuniste et sa fréquence de rotation.

Une fois ces points terminés, la même pipeline pourra être alimentée par les données
récentes pour produire le portefeuille et les ordres à contrôler par l'équipe.
