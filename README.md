# viagoscrap

Application de suivi Viagogo:
- scraping regulier des prix
- historique + graphique
- alerte email quand le prix minimum baisse
- abonnements email (toi + tes potes)

## 1) Prerequis

- Python 3.10+
- Playwright Chromium
- (Optionnel) compte Resend pour les emails

## 2) Installation locale

Depuis le dossier du projet:

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .
python -m playwright install chromium
```

## 3) Configuration `.env`

Copie `.env.example` vers `.env`, puis adapte:

```env
HEADLESS=false
TIMEOUT_MS=30000
DB_PATH=data/viagoscrap.db
SCRAPE_INTERVAL_MIN=15
DASHBOARD_URL=http://127.0.0.1:8000

EMAIL_PROVIDER=resend
RESEND_API_KEY=
ALERT_FROM_EMAIL=alerts@yourdomain.com
ALERT_TO_EMAIL=

# SMTP (alternative)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=true
```

## 4) Lancer l'application

```bash
python -m viagoscrap.webapp
```

Puis ouvre `http://127.0.0.1:8000`.

## 5) Utilisation (workflow)

1. Ajouter un event (nom + URL Viagogo).
2. Cliquer `Scraper maintenant` pour initialiser les donnees.
3. Regler la frequence auto (`Actualisation auto`).
4. Ajouter des emails dans la section `Notifications`:
   - scope `Tous les events` ou un event specifique.
5. Les emails partent automatiquement si un nouveau minimum est detecte.

## 6) Email: solution la plus simple

Recommande: `EMAIL_PROVIDER=resend`.

Pourquoi:
- pas besoin de ton Gmail perso
- pas de mot de passe SMTP a gerer
- plus simple a securiser en prod

Alternative Gmail SMTP:
- possible, mais utilise un **App Password** (pas ton mot de passe normal).

## 7) API utile

- `GET /healthz`
- `GET /api/config`
- `POST /api/config/interval`
- `GET /api/events`
- `POST /api/events`
- `POST /api/events/{id}/scrape`
- `POST /api/scrape-all`
- `GET /api/events/{id}/history`
- `GET /api/events/{id}/chart`
- `GET /api/subscribers`
- `POST /api/subscribers`
- `DELETE /api/subscribers/{subscriber_id}`
- `GET /api/runs`

## 8) Deployment Railway (prod)

1. Push le repo sur GitHub (**repo prive OK**).
2. Creer un projet Railway et connecter le repo.
3. Railway detecte le `Dockerfile`.
4. Ajouter un volume persistant monte sur `/data`.
5. Variables Railway minimales:
   - `DB_PATH=/data/viagoscrap.db`
   - `HEADLESS=true`
   - `SCRAPE_INTERVAL_MIN=15`
   - `DASHBOARD_URL=https://<ton-domaine>`
   - config email (`RESEND_API_KEY`, `ALERT_FROM_EMAIL`, etc.)
6. Deploy.
7. Verifier `GET /healthz`.

## 9) Tests

```bash
$env:PYTHONPATH='src'
python -m pytest -q
```

## 10) Notes

- Les selecteurs Viagogo peuvent changer avec le temps.
- Respecte les CGU de la plateforme et la legislation locale.
