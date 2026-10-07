# Bloomberg Trading Challenge — exports nettoyés

Snapshot du 7 octobre 2026. Les XLSX fournis restent les sources originales. Ce dossier contient des CSV pour Python/GitHub ; il ne contient pas de classeurs Excel réécrits.

## Utilisation

Copier le contenu du dossier dans `data/bloomberg/` du dépôt de l'équipe. Les historiques sont des CSV compressés (`.csv.gz`) : pandas les lit directement.

```python
import pandas as pd
from pathlib import Path
root = Path('data/bloomberg')
features = pd.read_csv(root / 'data/features_snapshot.csv', dtype={'id': str})
prices = pd.read_csv(root / 'data/prices_10y.csv.gz', index_col='date', parse_dates=True)
volumes = pd.read_csv(root / 'data/volumes_10y.csv.gz', index_col='date', parse_dates=True)
benchmark = pd.read_csv(root / 'data/benchmark_10y.csv', index_col='date', parse_dates=True)
```

Une cellule vide signifie une donnée manquante, jamais zéro. Les tickers Bloomberg complets sont les clés de jointure. Les dates sont au format ISO `YYYY-MM-DD`. Les valeurs numériques sont conservées sans arrondi volontaire. Les week-ends et autres dates sans observation restent dans les historiques avec des valeurs manquantes. Aucun remplissage, suppression de titre, winsorisation ou conversion de devise n'est effectué.

## Données principales

| Fichier (`data/`) | Contenu |
|---|---|
| `universe.csv` | 10 420 membres WLS, noms, poids et positions tels qu'exportés |
| `history_universe.csv` | Les 1 262 titres présents dans les historiques |
| `prices_10y.csv.gz` | Prix du 07/10/2016 au 07/10/2026, dates en lignes, tickers en colonnes |
| `volumes_10y.csv.gz` | Volumes sur la même période et les mêmes titres |
| `benchmark_10y.csv` | WLS Index ; export source `wls_benchmark_10y 1(1).xlsx` |
| `static.csv` | Dernier prix, volume, capitalisation, secteur |
| `momentum.csv` | MOM 1M, 3M, 6M et prix au snapshot |
| `rmom_inputs.csv` | Rendements 1M et 3M ; ce sont des entrées, pas un residual momentum calculé |
| `eps_actual.csv` | Dernier EPS trimestriel réalisé, pas l'EPS prévisionnel |
| `eps_estimates.csv` | EPS estimé annuel à maintenant, -1M et -3M, avec dates observées |
| `revision_breadth.csv` | Nombre de révisions haussières/baissières sur 30D/90D et breadth dérivé |
| `roe.csv` | ROE maintenant et -3M, en points de pourcentage |
| `leverage.csv` | Dette et actifs maintenant/-3M ; ratios dette/actifs dérivés |
| `features_snapshot.csv` | Jointure par ticker des facteurs, de l'univers et des données statiques |

`index_weight_pct` reprend les poids Bloomberg dont la somme est 100. `index_weight` est leur conversion en fractions dont la somme est 1. `index_position_source` conserve le champ exporté ; ce n'est pas une position recommandée pour notre portefeuille. `px_last_universe` est conservé séparément du prix statique car les valeurs peuvent provenir de captures différentes.

MOM est une fraction (0,05 = 5 %). Le ROE source est en points de pourcentage (10 = 10 %). Le leverage dérivé est une fraction. Le breadth est `(num_up - num_down) / (num_up + num_down)` ; il reste vide lorsque le dénominateur vaut zéro ou qu'un compte manque. Les zéro révisions sont conservés dans les colonnes de comptes. Les niveaux EPS, capitalisations, dettes et actifs gardent les unités du fournisseur : aucune devise commune n'est fournie dans les sources. Ne pas comparer les niveaux bruts entre devises sans enrichissement.

## Nettoyage effectué

- Retrait des lignes de commande/erreur qui précèdent les tables identifiables.
- Remplacement des marqueurs d'erreur Bloomberg par des valeurs manquantes dans les tables nettoyées.
- Normalisation des dates, y compris les dates stockées en numéros de série Excel.
- Regroupement des colonnes de snapshots EPS/ROE/dette/actifs sur une ligne par titre, en conservant les dates observées par champ.
- Une seule copie du ROE principal : `Classeur7wls_roe2(1).xlsx` et `wls_roe(1).xlsx` ont les mêmes données.
- Séparation des blocs superposés du gros classeur. Les exports 1Y, 3Y, 5Y et le benchmark qu'il contient sont conservés dans `supplementary/`.
- Conservation des versions alternatives et des conflits, sans sélectionner silencieusement un prix selon sa valeur.

## Points à compléter ou à traiter dans le modèle

- Les historiques couvrent un sous-univers de 1 262 titres, pas les 10 420 membres WLS. Le poids exact couvert figure dans `audit/report.json` et le bilan.
- La date de dernière annonce n'est pas récupérée correctement. La formule à `K17573` renvoie `Undefined item: latest_announcement_dt()`. Les colonnes D/E du bloc à gauche sont une série de périodes/dates historiques et ne doivent pas être jointes ligne par ligne aux tickers A/B.
- Aucun champ bêta ni shares outstanding n'est identifiable dans les sources. Les colonnes G/H/I n'ont pas d'en-tête : elles restent dans `supplementary/unlabeled_columns_a_i.csv` avec leur ligne Excel d'origine, sans attribution de sens. Les numéros de série Excel y sont conservés comme nombres bruts.
- ROE et leverage sont disponibles maintenant/-3M, pas à -1M.
- Le fichier RMOM contient les mêmes types de rendements que MOM, avec quelques différences de capture. `audit/momentum_conflicts.csv` conserve les différences ; le master utilise le fichier MOM, et RMOM reste séparé.
- Les deux exports benchmark diffèrent le 07/10/2026 : 2 575,81 contre 2 576,08. Le principal conserve la première source citée ci-dessus ; l'autre export et celui du gros classeur sont conservés. `audit/benchmark_conflicts.csv` signale ce point. L'heure de capture n'est pas connue et la valeur du jour peut être intrajournalière.
- Les facteurs constituent un snapshot, avec quelques observations à -1M/-3M. Ils ne forment pas un panel historique de 10 ans pour entraîner ou valider des signaux sans anticipation. Les membres de l'univers sont ceux du snapshot ; utiliser cet univers pour un backtest ancien introduit un risque de biais de survivance.
- Les sources ne précisent pas une politique homogène d'ajustement des prix ni les devises. Ne pas supposer des prix total return ou des valeurs en USD.

## Traçabilité

`audit/missing_values.csv` compte les valeurs manquantes dans chaque colonne des tables. `audit/report.json` décrit les blocs historiques, leurs dimensions, valeurs manquantes, dates et empreintes SHA-256 des sources et sorties. `audit/column_mapping.csv` relie les en-têtes Bloomberg aux noms normalisés. Le bilan français fournit la couverture lisible.

Pour reproduire le nettoyage à partir des 13 XLSX, avec `pandas`, `openpyxl` et `lxml` disponibles :

```bash
python scripts/prepare_data.py --input /chemin/vers/les_xlsx --output /chemin/vers/la_sortie
```
