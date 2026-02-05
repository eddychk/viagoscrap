from __future__ import annotations

import os
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False

from .config import Settings
from .storage import (
    active_events,
    add_subscriber,
    add_event,
    chart_points,
    deactivate_subscriber,
    event_history,
    get_event,
    init_db,
    list_events,
    list_runs,
    list_subscribers,
)
from .tracker import scrape_event_once


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8)
    active: bool = True


class IntervalUpdate(BaseModel):
    scrape_interval_min: int = Field(ge=1, le=1440)


class SubscriberCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    event_id: int | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().strip('"').strip("'").lower() in {"1", "true", "yes", "y", "on"}


def _build_dashboard_html() -> str:
    return """<!doctype html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ViagoScrap Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root { --bg:#eef2ff; --ink:#0f172a; --muted:#64748b; --card:#ffffff; --line:#dbe4ef; --primary:#0b5fff; --primary2:#00a6fb; }
    * { box-sizing: border-box; }
    body { margin:0; font-family:"Aptos","Trebuchet MS","Segoe UI",sans-serif; color:var(--ink); background:radial-gradient(circle at 0% 0%, #dbeafe, transparent 40%), radial-gradient(circle at 100% 100%, #fde68a, transparent 30%), var(--bg); }
    .wrap { max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:18px; box-shadow:0 18px 40px rgba(15,23,42,.08); padding:1rem; margin-top:1rem; }
    .row { display:grid; gap:1rem; grid-template-columns:1fr; margin-top:1rem; }
    .cluster { display:flex; flex-wrap:wrap; gap:.55rem; align-items:center; }
    input, select, button { border-radius: 10px; border:1px solid #cbd5e1; padding:.58rem .75rem; font-size:.95rem; }
    button { border:none; color:#fff; font-weight:700; cursor:pointer; background:linear-gradient(140deg,var(--primary),var(--primary2)); box-shadow:0 10px 22px rgba(11,95,255,.25); transition:transform .05s ease, opacity .2s ease; }
    button:hover { opacity:.96; }
    button:active { transform:translateY(1px); }
    button.ghost { background:#fff; color:#1d4ed8; border:1px solid #bfdbfe; box-shadow:none; }
    button[disabled] { opacity:.55; cursor:not-allowed; }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; border-bottom:1px solid #eef2f7; padding:.55rem; font-size:.92rem; }
    .muted { color:var(--muted); font-size:.9rem; }
    .status { display:inline-block; margin-top:.6rem; padding:.45rem .7rem; border-radius:999px; background:#e2e8f0; font-weight:700; font-size:.83rem; }
    .status.ok { background:#dcfce7; color:#166534; }
    .status.error { background:#fee2e2; color:#991b1b; }
    .status.busy { background:#dbeafe; color:#1d4ed8; }
    .chart-box { min-height:370px; background:linear-gradient(180deg, #fff, #f8fbff); }
    @media (min-width: 960px) { .row { grid-template-columns:1fr 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>ViagoScrap Dashboard</h1>
    <p class="muted" id="meta"></p>
    <span id="status" class="status">Pret</span>
    <div class="card">
      <h3>Controles</h3>
      <div class="cluster">
        <input id="name" placeholder="Nom (ex: Tomorrowland)" />
        <input id="url" style="min-width:420px;max-width:100%;" placeholder="https://www.viagogo.fr/..." />
        <button id="btnAdd" onclick="addEvent()">Ajouter</button>
        <button id="btnScrapeAll" onclick="scrapeAll()">Scraper maintenant</button>
      </div>
      <div class="cluster" style="margin-top:.65rem;">
        <label for="intervalMin"><strong>Actualisation auto (min)</strong></label>
        <input id="intervalMin" type="number" min="1" max="1440" style="width:110px;" />
        <button id="btnInterval" class="ghost" onclick="updateInterval()">Appliquer</button>
      </div>
    </div>
    <div class="card">
      <h3>Notifications</h3>
      <div class="cluster">
        <input id="subEmail" placeholder="email@exemple.com" />
        <select id="subEvent"></select>
        <button id="btnSub" class="ghost" onclick="addSubscriber()">Ajouter email</button>
      </div>
      <table id="subs" style="margin-top:.65rem;"></table>
    </div>
    <div class="row">
      <div class="card">
        <h3>Events suivis</h3>
        <table id="events"></table>
      </div>
      <div class="card chart-box">
        <h3>Evolution du prix min</h3>
        <select id="eventSelect" onchange="refreshChart()"></select>
        <canvas id="chart"></canvas>
      </div>
    </div>
  </div>
<script>
let chart = null;

function setStatus(message, kind='') {
  const el = document.getElementById('status');
  el.textContent = message;
  el.className = 'status' + (kind ? ` ${kind}` : '');
}

function setBusyButton(btn, busyText, finalText) {
  if (!btn) return () => {};
  btn.disabled = true;
  btn.textContent = busyText;
  return () => { btn.disabled = false; btn.textContent = finalText; };
}

async function api(path, opts={}) {
  const res = await fetch(path, { headers: {'Content-Type':'application/json'}, cache: 'no-store', ...opts });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadMeta() {
  const cfg = await api('/api/config?ts=' + Date.now());
  document.getElementById('meta').textContent = `DB: ${cfg.db_path} | Auto: ${cfg.scrape_interval_min} min`;
  document.getElementById('intervalMin').value = cfg.scrape_interval_min;
}

async function loadEvents() {
  const events = await api('/api/events?ts=' + Date.now());
  const select = document.getElementById('eventSelect');
  const subSelect = document.getElementById('subEvent');
  const selectedBefore = select.value;
  const table = document.getElementById('events');
  table.innerHTML = '<tr><th>ID</th><th>Nom</th><th>Prix min</th><th>Dernier scrape</th><th>Action</th></tr>';
  select.innerHTML = '';
  subSelect.innerHTML = '<option value=\"\">Tous les events</option>';
  events.forEach((e) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${e.id}</td><td>${e.name}</td><td>${e.lowest_price_raw ?? '-'}</td><td>${e.last_scraped_at ?? '-'}</td><td><button class="ghost" onclick="scrapeOne(${e.id}, this)">Scrape</button></td>`;
    table.appendChild(tr);
    const opt = document.createElement('option');
    opt.value = e.id;
    opt.textContent = `${e.id} - ${e.name}`;
    select.appendChild(opt);
    const subOpt = document.createElement('option');
    subOpt.value = e.id;
    subOpt.textContent = `${e.id} - ${e.name}`;
    subSelect.appendChild(subOpt);
  });
  if (events.length) {
    if (selectedBefore && events.some((e) => String(e.id) === String(selectedBefore))) {
      select.value = selectedBefore;
    }
    await refreshChart();
  }
  await loadSubscribers();
}

async function loadSubscribers() {
  const rows = await api('/api/subscribers?ts=' + Date.now());
  const table = document.getElementById('subs');
  table.innerHTML = '<tr><th>Email</th><th>Scope</th><th>Action</th></tr>';
  rows.forEach((s) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${s.email}</td><td>${s.event_id ?? 'Tous'}</td><td><button class=\"ghost\" onclick=\"removeSubscriber(${s.id})\">Retirer</button></td>`;
    table.appendChild(tr);
  });
}

async function addEvent() {
  const name = document.getElementById('name').value.trim();
  const url = document.getElementById('url').value.trim();
  if (!name || !url) return setStatus('Nom + URL requis', 'error');
  const done = setBusyButton(document.getElementById('btnAdd'), 'Ajout...', 'Ajouter');
  setStatus('Ajout en cours...', 'busy');
  try {
    await api('/api/events', { method: 'POST', body: JSON.stringify({ name, url, active: true }) });
    document.getElementById('name').value = '';
    await loadEvents();
    setStatus('Event ajoute', 'ok');
  } catch (e) {
    setStatus(`Erreur: ${e.message}`, 'error');
  } finally { done(); }
}

async function scrapeOne(id, btn=null) {
  const done = setBusyButton(btn, 'Scrape...', 'Scrape');
  setStatus(`Scrape ${id}...`, 'busy');
  try {
    await api(`/api/events/${id}/scrape`, { method: 'POST' });
    document.getElementById('eventSelect').value = String(id);
    await loadEvents();
    await refreshChart();
    setStatus(`Scrape ${id} termine`, 'ok');
  } catch (e) {
    setStatus(`Erreur scrape: ${e.message}`, 'error');
  } finally { done(); }
}

async function scrapeAll() {
  const done = setBusyButton(document.getElementById('btnScrapeAll'), 'Scrape en cours...', 'Scraper maintenant');
  setStatus('Scrape global en cours...', 'busy');
  try {
    await api('/api/scrape-all', { method: 'POST' });
    await loadEvents();
    await refreshChart();
    setStatus('Scrape global termine', 'ok');
  } catch (e) {
    setStatus(`Erreur globale: ${e.message}`, 'error');
  } finally { done(); }
}

async function updateInterval() {
  const val = parseInt(document.getElementById('intervalMin').value || '0', 10);
  if (!val || val < 1) return setStatus('Intervalle invalide', 'error');
  const done = setBusyButton(document.getElementById('btnInterval'), 'Mise a jour...', 'Appliquer');
  setStatus('Changement de periode...', 'busy');
  try {
    await api('/api/config/interval', { method: 'POST', body: JSON.stringify({ scrape_interval_min: val }) });
    await loadMeta();
    setStatus(`Periode auto: ${val} min`, 'ok');
  } catch (e) {
    setStatus(`Erreur periode: ${e.message}`, 'error');
  } finally { done(); }
}

async function addSubscriber() {
  const email = document.getElementById('subEmail').value.trim();
  const eventRaw = document.getElementById('subEvent').value;
  const event_id = eventRaw ? parseInt(eventRaw, 10) : null;
  if (!email || !email.includes('@')) return setStatus('Email invalide', 'error');
  const done = setBusyButton(document.getElementById('btnSub'), 'Ajout...', 'Ajouter email');
  try {
    await api('/api/subscribers', { method: 'POST', body: JSON.stringify({ email, event_id }) });
    document.getElementById('subEmail').value = '';
    await loadSubscribers();
    setStatus('Email ajoute aux notifications', 'ok');
  } catch (e) {
    setStatus(`Erreur notif: ${e.message}`, 'error');
  } finally { done(); }
}

async function removeSubscriber(id) {
  try {
    await api(`/api/subscribers/${id}`, { method: 'DELETE' });
    await loadSubscribers();
    setStatus('Abonnement retire', 'ok');
  } catch (e) {
    setStatus(`Erreur retrait: ${e.message}`, 'error');
  }
}

function prettyDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('fr-FR', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit' });
}

async function refreshChart() {
  const id = document.getElementById('eventSelect').value;
  if (!id) return;
  const points = await api(`/api/events/${id}/chart?ts=${Date.now()}`);
  if (!points.length) {
    if (chart) { chart.destroy(); chart = null; }
    setStatus('Pas encore de donnees', 'busy');
    return;
  }
  const labels = points.map((p) => prettyDate(p.scraped_at));
  const data = points.map((p) => p.min_price);
  if (chart) chart.destroy();
  const ctx = document.getElementById('chart').getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 320);
  gradient.addColorStop(0, 'rgba(11,95,255,.30)');
  gradient.addColorStop(1, 'rgba(11,95,255,.03)');
  chart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'Prix min', data, borderColor:'#0b5fff', backgroundColor:gradient, fill:true, tension:.35, borderWidth:3, pointRadius:3, pointHoverRadius:5 }] },
    options: {
      responsive: true,
      animation: { duration: 450 },
      interaction: { mode:'nearest', axis:'x', intersect:false },
      plugins: { legend: { labels: { usePointStyle:true, boxWidth:10 } }, tooltip: { mode:'index', intersect:false } },
      scales: {
        x: { grid: { display:false }, ticks: { maxRotation:0, autoSkip:true, maxTicksLimit:7 } },
        y: { beginAtZero:false, grid: { color:'rgba(148,163,184,.2)' }, ticks: { callback: (v) => `${v} EUR` } }
      }
    }
  });
}

async function refreshDataSilently() {
  try { await loadMeta(); await loadEvents(); } catch (_) {}
}

loadMeta().then(loadEvents);
setInterval(refreshDataSilently, 15000);
</script>
</body></html>"""


def create_app() -> FastAPI:
    load_dotenv()
    app = FastAPI(title="ViagoScrap Web")
    db_path = os.getenv("DB_PATH", "data/viagoscrap.db")
    interval_min = int(os.getenv("SCRAPE_INTERVAL_MIN", "15"))
    runtime = {"interval_min": max(1, interval_min)}
    settings = Settings.from_env()
    scraper_debug = _env_bool("SCRAPER_DEBUG", default=False)
    scheduler = BackgroundScheduler()

    def schedule_scrape_job() -> None:
        scheduler.add_job(
            run_all_active,
            "interval",
            minutes=runtime["interval_min"],
            id="scheduled-scrape",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def run_all_active() -> list[dict[str, Any]]:
        results = []
        for event in active_events(db_path):
            results.append(scrape_event_once(db_path, event, settings, debug=scraper_debug))
        return results

    @app.on_event("startup")
    def startup() -> None:
        init_db(db_path)
        schedule_scrape_job()
        scheduler.start()

    @app.on_event("shutdown")
    def shutdown() -> None:
        if scheduler.running:
            scheduler.shutdown(wait=False)

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _build_dashboard_html()

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        notifications_enabled = bool(
            os.getenv("RESEND_API_KEY") and os.getenv("ALERT_FROM_EMAIL") and os.getenv("ALERT_TO_EMAIL")
        )
        return {
            "db_path": db_path,
            "scrape_interval_min": runtime["interval_min"],
            "headless": settings.headless,
            "scraper_debug": scraper_debug,
            "notifications_enabled": notifications_enabled,
        }

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/config/interval")
    def update_interval(payload: IntervalUpdate) -> dict[str, Any]:
        runtime["interval_min"] = payload.scrape_interval_min
        if scheduler.running:
            schedule_scrape_job()
        return {"ok": True, "scrape_interval_min": runtime["interval_min"]}

    @app.get("/api/events")
    def events() -> list[dict[str, Any]]:
        return list_events(db_path)

    @app.post("/api/events")
    def create_event(payload: EventCreate) -> dict[str, Any]:
        event_id = add_event(db_path, payload.name, payload.url, active=payload.active)
        event = get_event(db_path, event_id)
        if not event:
            raise HTTPException(status_code=500, detail="Event created but not found")
        return event

    @app.get("/api/subscribers")
    def subscribers(event_id: int | None = None) -> list[dict[str, Any]]:
        return list_subscribers(db_path, event_id=event_id)

    @app.post("/api/subscribers")
    def create_subscriber(payload: SubscriberCreate) -> dict[str, Any]:
        if payload.event_id is not None and not get_event(db_path, payload.event_id):
            raise HTTPException(status_code=404, detail="Event not found")
        subscriber_id = add_subscriber(db_path, payload.email, payload.event_id)
        created = [row for row in list_subscribers(db_path) if int(row["id"]) == subscriber_id]
        return created[0] if created else {"id": subscriber_id, "email": payload.email, "event_id": payload.event_id}

    @app.delete("/api/subscribers/{subscriber_id}")
    def delete_subscriber(subscriber_id: int) -> dict[str, Any]:
        deactivate_subscriber(db_path, subscriber_id)
        return {"ok": True}

    @app.post("/api/events/{event_id}/scrape")
    def scrape_one(event_id: int) -> dict[str, Any]:
        event = get_event(db_path, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return scrape_event_once(db_path, event, settings, debug=scraper_debug)

    @app.post("/api/scrape-all")
    def scrape_all() -> list[dict[str, Any]]:
        return run_all_active()

    @app.get("/api/events/{event_id}/history")
    def history(event_id: int, limit: int = Query(default=500, ge=1, le=5000)) -> list[dict[str, Any]]:
        event = get_event(db_path, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return event_history(db_path, event_id, limit=limit)

    @app.get("/api/events/{event_id}/chart")
    def chart(event_id: int) -> list[dict[str, Any]]:
        event = get_event(db_path, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return chart_points(db_path, event_id)

    @app.get("/api/runs")
    def runs(event_id: int | None = None, limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, Any]]:
        return list_runs(db_path, event_id=event_id, limit=limit)

    return app


def main() -> None:
    import uvicorn

    uvicorn.run("viagoscrap.webapp:create_app", host="127.0.0.1", port=8000, reload=False, factory=True)


if __name__ == "__main__":
    main()
