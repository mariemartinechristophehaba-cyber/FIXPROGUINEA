# FixPro Guinée

Plateforme console de mise en relation artisans-clients (Guinée), avec
géolocalisation, interventions, évaluations, paiements et notifications.

## Prérequis

- Python 3.10+
- MySQL (base `FixPro`)

## Installation

```bash
pip install -r requirements.txt        # exécution
pip install -r requirements-dev.txt    # + outils de test
```

## Configuration

La connexion MySQL est lue depuis des variables d'environnement :

| Variable          | Défaut      |
| ----------------- | ----------- |
| `FIXPRO_DB_HOST`  | `localhost` |
| `FIXPRO_DB_USER`  | `root`      |
| `FIXPRO_DB_PASS`  | *(vide)*    |
| `FIXPRO_DB_NAME`  | `FixPro`    |

## Lancer l'application

```bash
python fixpro.py
```

## Tests

Les tests unitaires simulent la base de données (aucune connexion réelle
n'est ouverte). Importer `fixpro` n'ouvre pas de connexion MySQL : la
connexion et le menu ne démarrent que via `python fixpro.py`.

```bash
pytest
```

La couverture est affichée automatiquement (voir `pytest.ini`).
