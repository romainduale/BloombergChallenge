# Travailler ensemble sur le dépôt

On est cinq sur le même projet. Pour avancer sans se gêner, chacun prend une tâche
précise et fait relire son travail avant de le fusionner.

## Une branche pour chaque tâche

Actualise ta branche principale avec `git pull --ff-only`, puis crée ta branche.
Choisis un nom qui dit ce que tu fais, par exemple `data/import-wls` ou
`backtest/controle-prix`.

Quand ton travail est prêt, ouvre une pull request : explique ce que tu as changé
et comment tu l'as vérifié. Un autre membre la relit avant la fusion. Si tu changes
le format d'un fichier utilisé par les autres, préviens-les avant de coder.

La relecture obligatoire et la protection de la branche principale doivent encore
être activées dans les paramètres GitHub.

### Types de branches

| Préfixe | Usage |
|---|---|
| `feature/` | Nouvelle capacité de modèle ou de portefeuille |
| `fix/` | Correction d'un bug ou d'une fuite de données |
| `data/` | Import, audit ou contrat de données |
| `research/` | Expérience qui ne modifie pas encore la stratégie de référence |
| `backtest/` | Moteur, métrique ou contrôle de backtest |
| `docs/` | Documentation uniquement |

Une branche reste courte et centrée sur un seul objectif. Les expériences utiles
passent de `research/` vers une PR de production seulement après comparaison à une
baseline et validation hors échantillon.

### Cycle d'une modification

1. Décrire l'hypothèse, le résultat attendu et le contrôle qui prouvera le succès.
2. Créer la branche depuis une `main` à jour.
3. Ajouter le code, les tests et la documentation dans la même PR.
4. Exécuter les contrôles locaux puis pousser la branche.
5. Ouvrir une PR avec le modèle fourni dans `.github/pull_request_template.md`.
6. Corriger la CI et faire relire par au moins une autre personne.
7. Fusionner par squash, puis supprimer la branche.

Pour `main`, activer dans GitHub : PR obligatoire, une approbation, résolution des
conversations, contrôles Linux et Windows obligatoires, interdiction des force-push
et des suppressions. On ne fusionne pas une PR dont la CI est rouge.

## Ce qu'on garde dans Git

Le code, les notebooks utiles, la documentation et les petits jeux de données
inventés pour les tests. Mets ces jeux de test dans `tests/fixtures/`.

Les Excel déjà présents dans le dépôt restent versionnés et inchangés à la racine.
Les données partagées dans `data/bloomberg/` restent également versionnées.
Les prochains exports locaux iront dans `data/raw/` et les résultats générés dans
`outputs/`. Ces nouveaux fichiers et résultats sont ignorés par Git.

Il nous reste à choisir un dossier partagé pour que chacun récupère les mêmes
exports. Le `.gitignore` évite de les committer, mais ne les partage pas.

## Avant de committer

1. Regarde `git status` et `git diff`.
2. Ajoute seulement les fichiers de ta tâche avec `git add chemin/du/fichier`.
3. Relis `git diff --cached` et lance les contrôles utiles.

Garde les clés et mots de passe dans un `.env` local. Si besoin, un `.env.example`
peut montrer les variables à remplir, avec des valeurs fictives.

## Préparer Python

On utilise **Python 3.14** pour ce premier import. Les bibliothèques et leurs
dépendances sont figées dans `requirements-lock.txt` ; `requirements.txt` les installe.
Sous Windows, depuis le dossier du dépôt :

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Pas besoin d'activer l'environnement pour ces commandes. Sur macOS ou Linux,
crée-le avec `python3.14 -m venv .venv` et remplace le chemin Python par
`.venv/bin/python`. Le dossier `.venv` reste local et est ignoré par Git.

## Lancer le premier import

Avec ta copie locale de l'export :

```powershell
.\.venv\Scripts\python.exe src/import_wls.py --input wls.xlsx --output-dir data/interim/wls_2026-10-02
```

Si ton fichier est dans `data/raw/`, utilise `--input data/raw/wls.xlsx`.
Le dossier de sortie doit être nouveau : l'import ne remplace pas les résultats
d'une exécution précédente. Choisis un autre nom pour le relancer.

Il produit `snapshot.parquet`, `anomalies.csv`, `report.json` et `data_dictionary.json`.
Les valeurs restent brutes. Les trois volatilités manquantes deviennent des valeurs
nulles avec un motif ; aucun titre n'est supprimé. Les unités restent à confirmer
avec Data avant de parler de données validées pour un backtest.

## Vérifier avant de demander une relecture

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
```

Les règles Ruff sur les imports et le formatage préservent le module
`src/covariance.py` déjà fusionné par l’équipe ; ses tests et les autres règles
de contrôle restent actifs.

Les tests créent de petits classeurs fictifs. L'équipe peut les lancer sans Terminal
Bloomberg ni export privé. GitHub Actions lance les mêmes contrôles sous Windows
et Linux ; les résultats distants restent à vérifier après publication de la branche.

Pour un changement quantitatif, la PR précise aussi la date des données, l'univers,
le benchmark, les devises, les règles d'ajustement, les coûts et la baseline. Un gain
de backtest sans ces informations n'est pas une preuve suffisante pour modifier la
stratégie de référence.

## Historique de l'import WLS

Le premier import, initialement développé sur `data/python-import-wls`, est
désormais fusionné dans `main`. Les Excel restent suivis par Git et inchangés ; les
nouveaux résultats d'import restent locaux dans `data/interim/` jusqu'à validation.
