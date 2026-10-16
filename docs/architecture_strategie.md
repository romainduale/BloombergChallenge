# Architecture de la stratégie et état réel du code

Ce document décrit le dépôt tel qu'il fonctionne aujourd'hui. Il sépare les
briques déjà codées des hypothèses qui figurent dans la stratégie cible mais qui
ne sont pas encore implémentées.

## Vue d'ensemble

```text
Exports Bloomberg
    |
    v
features.py
    |  panel hebdomadaire + cible relative à 5 semaines
    +--------------------+
    |                    |
    v                    v
Elastic Net          Tail model
    |                    |
    +---------+----------+
              v
    signal combiné 25 % / 75 %
              |
              v
 top 30 -> covariance Ledoit-Wolf -> filtre de corrélation -> shortlist de 12
              |
              v
optimisation long-only -> portefeuille -> backtests, audit et plan d'ordres
              |
              +-> option 80 % cœur + 20 % score opportuniste yfinance
```

## 1. Données

`data/bloomberg/` contient le snapshot nettoyé du 7 octobre 2026 : univers WLS,
prix et volumes sur dix ans, benchmark, facteurs statiques et fichiers d'audit.
Les historiques couvrent 1 262 titres, soit 84,17 % du poids du WLS au snapshot,
alors que l'univers statique contient 10 420 titres.

`src.refresh_feature_market_data` prolonge uniquement les prix et volumes nécessaires
aux features actives. Les nouveaux symboles sont contrôlés sur une période de
chevauchement avec Bloomberg avant import. Le WLS n'est pas remplacé par un indice
proxy ; les calculs de risque s'arrêtent à la dernière date commune disponible.

`src/import_wls.py` traite séparément le classeur historique `wls.xlsx`. Il
préserve les valeurs brutes, refuse les schémas ambigus et produit un snapshot,
un rapport, un dictionnaire et une liste d'anomalies.

Limites structurantes des données actuelles :

- l'univers historique est reconstruit à partir des titres présents au snapshot ;
- les devises et la politique d'ajustement des prix ne sont pas homogénéisées ;
- les facteurs fondamentaux et analystes sont surtout des snapshots, pas un panel
  point-in-time utilisable sur dix ans ;
- les résultats générés dans `data/processed/` sont locaux et ignorés par Git.

Ces limites autorisent un prototype de recherche, mais pas encore une conclusion
fiable sur la performance historique de la stratégie cible.

## 2. Features et cible

`src/features.py` transforme les prix et volumes quotidiens en observations du
vendredi. Il calcule six variables puis leur rang transversal à chaque date :

- momentum sur 1, 3 et 6 mois ;
- volatilité annualisée sur 13 semaines ;
- volume hebdomadaire rapporté à sa médiane sur 13 semaines ;
- distance au plus haut sur 52 semaines.

La cible est le rendement futur du titre à cinq semaines moins le rendement futur
du WLS sur la même période. La dernière semaine incomplète est écartée.

## 3. Modèles de signal

`src/elastic_net_transversal.py` entraîne un modèle Elastic Net commun à tous les
titres. Le walk-forward utilise trois ans d'apprentissage, une purge de cinq
semaines et une date de test toutes les cinq semaines. La métrique principale est
l'IC de rang de Spearman.

`src/tail_model_v1.py` transforme la cible en classification : un titre est positif
s'il termine dans le meilleur décile transversal à cinq semaines. Une régression
logistique produit une probabilité, évaluée notamment par AUC, average precision
et précision dans le décile supérieur.

`src/combined_signal_v1.py` combine les rangs des deux modèles : 75 % pour le
modèle tail et 25 % pour l'Elastic Net. Ces pondérations sont fixes.

## 4. Risque, sélection et allocation

`src/risk_screen_v1.py` prend les 30 meilleurs scores, estime sur 52 semaines une
covariance Ledoit-Wolf des rendements relatifs au WLS, puis sélectionne jusqu'à 12
titres. Un titre est refusé si sa corrélation absolue avec un titre déjà retenu
dépasse 0,80.

`src/robust_optimizer_v1.py` utilise SLSQP pour maximiser :

```text
alpha Elastic Net attendu - 0,15 x risque relatif estimé à 5 semaines
```

Les poids sont positifs, totalisent 100 % et sont plafonnés à 20 %. Le score tail
sert à construire la shortlist ; l'optimiseur utilise ensuite seulement la
prédiction Elastic Net comme alpha.

`src/opportunistic_model.py` peut ensuite ramener ces poids à 80 % et réserver 20 %
à quatre titres absents du portefeuille cœur. Il classe ces candidats avec des
données yfinance récentes : momentum, volatilité, drawdown, liquidité en USD et,
quand elle existe, cible moyenne des analystes. Cette couche est explicable mais
n'a pas encore été backtestée ; elle reste séparée du modèle principal.

## Configuration finale du challenge

La V1 à cinq semaines reste la référence historique. La stratégie exécutable finale
se trouve dans `src/strategies/final_four_week/` : elle recalcule la cible, la purge,
les modèles et le risque sur quatre semaines. Le signal attendu du 16 octobre 2026
arrive ainsi au 13 novembre 2026. La poche opportuniste conserve exactement la
configuration de `config/portfolio_allocation.json` et les fonctions de scoring
existantes.

L'export final ajoute, par titre, les scores bruts et les rangs Elastic Net/Tail,
les valeurs des features, les bêta standardisés des deux modèles et les contributions
`feature standardisée × bêta`. Les contributions expliquent le sens et l'amplitude
de l'effet de chaque variable sur le choix du titre.

## 5. Backtests et validations

- `src/backtest_portfolio_v1.py` réentraîne les modèles à chaque date, reconstruit
  le risque, alloue le portefeuille et mesure les rendements à cinq semaines ;
- `src/validate_portfolio_offsets.py` répète le test sur les cinq calendriers
  possibles afin d'éviter de dépendre d'un seul point de départ ;
- `src/validate_elastic_net.py` teste les offsets, les coefficients, un placebo par
  permutation de cible et une statistique de moyenne Newey-West ;
- `src/validate_tail_model.py` valide le modèle tail sur plusieurs offsets ;
- `src/validate_optimizer_v1.py` compare plusieurs valeurs de robustesse ;
- `src/benchmark_signals.py` compare les modèles à des signaux unitaires simples ;
- `src/compare_weighting_v1.py` compare les résultats d'allocation agrégés.

La couche d'exécution ajoutée autour de cette V1 ne change pas le signal :

- `src/backtest_execution_v2.py` ajoute coûts, turnover et simulations de stops ;
- `src/audit_backtest.py` produit les résultats annuels, les extrêmes, les drawdowns
  et le diagnostic des biais ;
- `src/build_execution_plan.py` transforme la cible en ordres d'achat, conservation,
  réduction, vente et vente sur stop ;
- `src/run_pipeline.py` enchaîne le signal, le risque, l'allocation et les ordres ;
- `src/features_v2.py` et `src/compare_features_v2.py` isolent les essais de nouvelles
  variables sans modifier la V1.

Les paramètres d'exécution se trouvent dans `config/execution_profiles.json`. Le stop
reste désactivé par défaut après comparaison historique ; il peut être réactivé via un
profil pour de nouveaux tests. Les résultats détaillés figurent dans
`docs/audit_execution_features.md`.

## Écart avec la stratégie cible du README

La chaîne V1 est un prototype cohérent, mais l'allocation décrite dans le README
n'est pas encore celle du code. Les éléments suivants restent à implémenter ou à
valider :

1. univers historique et variables réellement point-in-time ;
2. prix ajustés et rendements dans une devise commune ;
3. momentum 12-1, révisions, surprises, valeur et qualité historiques ;
4. conversion des scores en alpha calibré par l'IC ;
5. optimisation explicite en poids actifs par rapport aux poids WLS ;
6. contrainte de tracking error et pénalité de turnover dans l'optimiseur ;
7. règles exactes du challenge et simulation fidèle des ordres limites intraday ;
8. couverture exhaustive des briques historiques déjà présentes.

Tant que les points 1 et 2 ne sont pas réglés, les métriques historiques doivent
être présentées comme exploratoires : le biais de survivance et les devises peuvent
dominer le signal mesuré.
