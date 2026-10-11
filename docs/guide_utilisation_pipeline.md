# Guide rapide de la pipeline

## Objectif

La stratégie cherche les actions qui pourraient battre l'indice Bloomberg WLS au
cours des cinq semaines suivantes, puis construit un portefeuille de 1 M$.

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
- tests automatiques et documentation des limites des données.

Le signal principal déjà présent n'a pas été remplacé. La nouvelle couche a été
construite autour de lui.

## Comment la stratégie fonctionne

### 1. Target

La target apprise par le modèle est :

```text
rendement futur de l'action à 5 semaines
− rendement futur du WLS à 5 semaines
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

Les quantités d'actions restent marquées `FX_REQUIRED` tant que les conversions de
devises vers l'USD ne sont pas disponibles.

## Comment lancer la pipeline

Dans le terminal PyCharm, à la racine du projet :

```bash
.venv/bin/python -m src.run_pipeline --skip-features
```

Pour tout recalculer, y compris les features :

```bash
.venv/bin/python -m src.run_pipeline
```

Le fichier final se trouve ici :

```text
data/processed/execution/execution_orders.csv
```

## Fichiers importants

| Fichier | Rôle |
|---|---|
| `src/features.py` | Features et target |
| `src/elastic_net_transversal.py` | Modèle Elastic Net |
| `src/tail_model_v1.py` | Modèle Tail |
| `src/risk_screen_v1.py` | Ledoit-Wolf et shortlist |
| `src/robust_optimizer_v1.py` | Poids du portefeuille |
| `src/backtest_execution_v2.py` | Backtest avec coûts et stops |
| `src/execution_rules.py` | Règles d'achat et de vente |
| `src/run_pipeline.py` | Commande principale |
| `config/execution_profiles.json` | Paramètres modifiables |

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

Une fois ces points terminés, la même pipeline pourra être alimentée par les données
récentes pour produire le portefeuille et les ordres à contrôler par l'équipe.
