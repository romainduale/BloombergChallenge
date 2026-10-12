# Audit du backtest, règles d'exécution et features candidates

Ce document décrit la couche ajoutée autour de la stratégie V1. Les résultats restent
exploratoires : l'univers n'est pas encore point-in-time, les devises ne sont pas
normalisées et la nature ajustée ou non des prix n'est pas documentée.

## 1. Coûts de transaction et turnover

Les paramètres sont centralisés dans `config/execution_profiles.json` :

- `commission_bps` : commission en points de base ;
- `slippage_bps` : écart estimé entre le prix théorique et le prix réellement obtenu ;
- `minimum_trade_weight` : variation minimale de poids avant de créer un ordre ;
- paramètres d'ordre limite et de stop-loss ;
- `max_position_weight`, fixé à 20 % pour tous les profils.

Un point de base vaut 0,01 %. Le coût imputé au portefeuille est :

```text
notionnel échangé × (commission_bps + slippage_bps) / 10 000
```

Le turnover « one-way » vaut la moitié de la somme des variations absolues des poids,
cash compris. Un turnover de 100 % signifie que l'équivalent du portefeuille entier a
été remplacé une fois. Il s'agit d'une mesure, pas d'un rendement.

Sur la V1 sans stop, le turnover moyen ressort à 87,13 % par rebalancement de cinq
semaines. Avec 10 bps de commission et 5 bps de slippage par transaction, le coût moyen
est de 0,259 % par période. C'est élevé et cela montre que la rotation du portefeuille
doit être surveillée avant le challenge.

## 2. Règles simples et réglables

Le plan d'exécution compare le portefeuille actuel au portefeuille cible :

| Action | Règle | Type d'ordre |
|---|---|---|
| Acheter | poids cible − poids actuel ≥ seuil minimal | limite d'achat |
| Conserver | variation absolue sous le seuil minimal | aucun ordre |
| Réduire | baisse de poids supérieure au seuil minimal | vente au marché |
| Vendre | cible proche de zéro avec position existante | vente au marché |
| Stop | prix inférieur au stop calculé depuis le prix d'entrée | vente au marché |

Le prix limite d'achat vaut `dernier prix × (1 − décote)` et expire après le nombre de
jours ouvrés configuré. Le fichier d'ordres contient aussi le poids, le montant et le
stop de protection. Le nombre d'actions reste vide avec le statut `FX_REQUIRED` tant
que la conversion de la devise locale vers l'USD n'est pas fournie ; cela évite de
diviser un montant en dollars par un cours coté en KRW, JPY ou EUR.

Deux familles de stops sont testables :

- fixe : distance constante, par exemple 8 % sous le prix d'entrée ;
- volatilité : `multiplicateur × volatilité quotidienne × √5`, bornée par un minimum
  et un maximum.

Les exports ne contiennent pas les historiques high/low nécessaires à un ATR exact.
Le mode « volatilité » est donc un proxy testable, pas un ATR. Le backtest détecte les
franchissements sur les clôtures et peut exécuter le jour suivant pour éviter une
hypothèse de remplissage instantané trop favorable.

Les profils fournissent des points de départ modifiables, pas des recommandations
définitives :

| Profil | Limite d'achat | Validité | Stop | Seuil minimal de trade |
|---|---:|---:|---|---:|
| `sans_stop`, défaut | −0,50 % | 3 jours | désactivé | 0,50 % |
| `stop_fixe`, contrôle | −0,50 % | 3 jours | fixe 8 % | 0,50 % |
| `prudent` | −0,75 % | 2 jours | fixe 6 % | 0,50 % |
| `equilibre` | −0,50 % | 3 jours | volatilité, bornes 5-15 % | 0,50 % |
| `dynamique` | −0,25 % | 1 jour | volatilité, bornes 6-20 % | 1,00 % |

Chaque valeur peut être changée dans le JSON puis retestée. Un seuil minimal de trade
plus élevé évite les micro-ajustements et réduit généralement le turnover.

## 3. Test historique des stops

Les trois variantes suivantes utilisent le même signal, les mêmes coûts et les mêmes
paramètres de limites. Seul le stop change. Le test porte sur 304 périodes, cinq offsets,
du 6 novembre 2020 au 2 octobre 2026.

| Variante | Excès net moyen à 5 semaines | Taux de victoire | Turnover | Coût moyen | Pire drawdown d'un offset |
|---|---:|---:|---:|---:|---:|
| Sans stop | +2,94 % | 64,80 % | 87,13 % | 0,259 % | −39,86 % |
| Stop fixe 8 % | +1,61 % | 57,24 % | 95,16 % | 0,283 % | −38,32 % |
| Stop volatilité | +1,81 % | 57,24 % | 92,95 % | 0,275 % | −41,37 % |

Conclusion provisoire : ne pas activer de stop par défaut. Le stop fixe réduit très
légèrement le pire drawdown, mais dégrade le rendement moyen de 1,33 point par période.
Le stop volatilité réduit la dispersion des résultats entre offsets, sans améliorer le
pire drawdown. La logique reste disponible dans les profils pour être retestée avec des
données OHLC fiables.

Les ordres limites ont un taux de remplissage indicatif d'environ 62,6 % sur les
clôtures disponibles. Ils sont étudiés séparément et ne modifient pas encore les
rendements du backtest : sans intraday ou au minimum high/low, imposer un prix de
remplissage serait trop approximatif.

## 4. Audit annuel de la variante sans stop

Les résultats suivants sont les moyennes des cinq offsets. Ils ne doivent pas être
additionnés entre offsets car les périodes se chevauchent.

| Année | Rendement relatif net moyen | Intervalle entre offsets | Taux de victoire moyen | Drawdown moyen |
|---|---:|---:|---:|---:|
| 2020, partiel | +17,96 % | +5,86 % à +35,39 % | 100,00 % | 0,00 % |
| 2021 | +12,81 % | −5,11 % à +27,52 % | 62,36 % | −15,10 % |
| 2022 | +18,99 % | +6,58 % à +30,52 % | 61,82 % | −23,87 % |
| 2023 | +12,03 % | −1,64 % à +41,90 % | 57,27 % | −15,81 % |
| 2024 | +21,50 % | −2,08 % à +36,56 % | 59,64 % | −8,50 % |
| 2025 | +64,93 % | +39,71 % à +104,04 % | 74,91 % | −11,43 % |
| 2026, partiel | +32,02 % | +13,76 % à +48,73 % | 68,57 % | −16,77 % |

La meilleure période est l'offset 1 du 13 novembre au 18 décembre 2020 : +33,74 %
d'excès net à cinq semaines. La pire est l'offset 4 du 26 juin au 31 juillet 2026 :
−24,34 %. Les niveaux 2025-2026 sont anormalement élevés et renforcent la nécessité de
corriger les biais avant d'interpréter la performance comme réalisable.

## 5. Features candidates testées

Les sept idées du classeur ont été rapprochées des données disponibles : Sortino,
révision d'EPS, momentum résiduel, Frog-in-the-Pan, distance au plus haut 52 semaines,
volatilité idiosyncratique et illiquidité d'Amihud. La distance au plus haut 52 semaines
était déjà présente en V1 et n'a pas été dupliquée. La révision d'EPS reçoit un retard
conservateur d'un mois.

La comparaison walk-forward est faite sur le même échantillon de 73 périodes :

| Jeu de features | IC Elastic Net moyen | IC combiné moyen | AUC tail | Précision top décile |
|---|---:|---:|---:|---:|
| V1, échantillon commun | 0,1001 | 0,1157 | 0,7342 | 0,2763 |
| V1 + révision EPS | 0,1019 | 0,1167 | 0,7358 | 0,2769 |
| V1 + IVOL | 0,0993 | 0,1097 | 0,7477 | 0,2879 |
| V1 + IVOL + EPS | 0,1016 | 0,1113 | 0,7487 | 0,2901 |
| V2 complète | 0,0872 | 0,1067 | 0,7466 | 0,2809 |

La V2 complète n'améliore pas le score combiné. La révision d'EPS apporte un petit gain
global, tandis qu'IVOL améliore le modèle tail mais réduit l'IC combiné. La décision
prudente est de conserver V1 en production et de garder EPS/IVOL comme expériences.

## 6. Biais identifiés

| Biais | Constat | Action requise |
|---|---|---|
| Survivorship | 1 262 titres historiques contre 10 420 au snapshot, couvrant 84,17 % du poids | compositions WLS historiques point-in-time |
| Données manquantes | couverture moyenne prix/volumes 64,51 %, EPS 82,66 % | publier la couverture par date et éviter l'imputation cachée |
| Devises | aucun historique FX exploité | convertir tous les rendements en USD |
| Prix ajustés | politique dividendes/splits non documentée | figer un champ total-return ou adjusted-price vérifié |
| Timing EPS | dates exactes de publication absentes | conserver les timestamps source ; retard d'un mois en attendant |

## 7. Commandes utiles

Pipeline portefeuille et ordres, sans stop par défaut :

```bash
.venv/bin/python -m src.run_pipeline --skip-features
```

Pour obtenir des décisions de conservation, réduction ou vente, fournir les positions
actuelles dans un CSV contenant `id`, `weight` et, si disponible, `entry_price` :

```bash
.venv/bin/python -m src.run_pipeline --skip-features \
  --current-positions data/current_positions.csv
```

Sans ce fichier, la pipeline suppose un portefeuille initialement en cash et produit
logiquement uniquement des achats pour les poids cibles significatifs.

Pour générer des ordres avec le stop volatilité expérimental :

```bash
.venv/bin/python -m src.run_pipeline --skip-features --profile equilibre
```

Pour reconstruire l'audit des trois règles de stop :

```bash
.venv/bin/python -m src.backtest_execution_v2 --profile sans_stop
.venv/bin/python -m src.backtest_execution_v2 --profile stop_fixe
.venv/bin/python -m src.backtest_execution_v2 --profile equilibre
.venv/bin/python -m src.compare_execution_profiles
```

Pour reconstruire et comparer les features :

```bash
.venv/bin/python -m src.features_v2
.venv/bin/python -m src.compare_features_v2
```
