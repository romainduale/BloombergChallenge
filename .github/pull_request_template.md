## Objectif

<!-- Quel problème cette PR résout-elle ? Une PR = un objectif principal. -->

## Changements

<!-- Résumer les changements fonctionnels et les fichiers importants. -->

## Validation

<!-- Commandes lancées, résultats et comparaison avec la baseline. -->

- [ ] `python -m pytest`
- [ ] `python -m ruff check src tests`
- [ ] `python -m ruff format --check src tests`

## Contrôles quantitatifs

<!-- Cocher « sans objet » dans le texte si la PR ne touche pas la stratégie. -->

- [ ] Les variables sont disponibles à la date où elles sont utilisées.
- [ ] La purge et les fenêtres d'apprentissage/test sont respectées.
- [ ] L'univers, le benchmark, les devises et les ajustements de prix sont explicités.
- [ ] Les coûts, le turnover et les contraintes de portefeuille sont pris en compte ou signalés.
- [ ] Le résultat est comparé à une baseline simple et sur une période hors échantillon.
- [ ] Les paramètres n'ont pas été choisis sur la période finale de test.

## Données et reproductibilité

- [ ] Aucun export privé, secret ou résultat généré volumineux n'est ajouté à Git.
- [ ] Toute modification de schéma ou de convention de données est documentée.
- [ ] Les paramètres, dates et chemins nécessaires pour reproduire le résultat sont indiqués.

## Risques et retour arrière

<!-- Limites connues, consommateurs impactés et manière d'annuler le changement. -->
