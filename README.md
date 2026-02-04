# viagoscrap

Demarrage rapide d'un scraper Viagogo avec Playwright.

## Installation

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .
python -m playwright install chromium
```

## Utilisation

```bash
viagoscrap --url "https://www.viagogo.com/ww/Sports-Tickets/..."
```

Le script ouvre la page, attend le rendu JS, puis extrait les cartes de resultats (titre, date, prix, lien).

## Notes

- Respecte les CGU de la plateforme et la legislation locale.
- Les selecteurs CSS peuvent evoluer, adapte `src/viagoscrap/scraper.py` si besoin.
