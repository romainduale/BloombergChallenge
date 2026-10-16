# Organisation des stratégies

Chaque horizon testé possède son propre dossier et une commande reproductible.

| Dossier | Statut | Commande |
|---|---|---|
| `one_week/` | expérience testée, non retenue | `python -m src.strategies.one_week.run` |
| `five_week/` | référence historique testée | `python -m src.strategies.five_week.run` |
| `final_four_week/` | stratégie finale du challenge | `python -m src.strategies.final_four_week.pipeline` |

Le dossier final contient la cible, les modèles, le portefeuille, le backtest,
l'export explicable et la pipeline. La poche opportuniste de 20 % continue
d'utiliser exactement les règles et paramètres de `src.opportunistic_model`.
