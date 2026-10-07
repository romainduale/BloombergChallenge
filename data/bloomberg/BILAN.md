# Bilan des données Bloomberg

Snapshot : 7 octobre 2026. Univers : **10 420 titres**. Historiques : **1 262 titres**, soit **84.17 % du poids WLS** au snapshot.

| Donnée | Présence et couverture |
|---|---|
| Prix 10Y | 1 262 titres, 3 653 dates calendaires ; valeurs manquantes conservées |
| Volumes 10Y | Même sous-univers et dates |
| WLS benchmark 10Y | Présent ; 2 832 observations non manquantes dans le principal |
| MOM 1M / 3M / 6M | 7 820 / 10 420 ; 10 401 / 10 420 ; 9 562 / 10 420 |
| EPS estimé actuel / -1M / -3M | 8 861 / 10 420 ; 8 847 / 10 420 ; 8 834 / 10 420 |
| Revision breadth 1M / 3M | Comptes présents ; ratio vide si aucun changement ou compte manquant |
| ROE actuel / -3M | 10 160 / 10 420 ; 10 139 / 10 420 ; -1M absent |
| Leverage actuel / -3M | 10 398 / 10 420 ; 10 397 / 10 420 ; -1M absent |
| Market cap | 10 420 / 10 420 ; devise non fournie |
| Secteur | 10 413 / 10 420 |
| Earnings latest date | Non exploitable : requête invalide et bloc historique non aligné aux titres |
| Beta | Aucun champ identifiable |
| Shares outstanding | Aucun champ identifiable |

Les colonnes sans en-tête sont préservées dans le dossier supplementary, avec leurs lignes Excel sources. Elles ne sont pas utilisées dans le master.

Écarts entre MOM et RMOM : 119 valeurs 1M et 119 valeurs 3M. Les fichiers restent séparés et le master prend MOM. Le fichier audit/momentum_conflicts.csv détaille les écarts.

Les deux benchmark diffèrent seulement au 07/10/2026 (2 575,81 contre 2 576,08). Les deux valeurs sont conservées, car les heures de capture ne sont pas connues.

Nettoyage vérifié : unicité des clés, jointures des 10 420 titres, ratio dette/actifs, ratio de breadth, lecture de tous les CSV historiques, dimensions, ordre des dates, valeurs manquantes et valeurs non positives. Aucun remplacement de données manquantes par zéro.

Les CSV sont prêts à être intégrés au dépôt. Le README explique les unités, la lecture Python et les limites pour un backtest historique.
