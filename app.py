"""
Dashboard web (Flask).

- Avant 9h30 (heure Bamako) : affiche le bilan de la veille.
- Après 9h30 : affiche les pronostics du jour.
- Page /historique : tout l'historique + taux de réussite réel.
- Route /api/run-daily-job : déclenche l'analyse quotidienne (appelée par un
  service externe de type cron-job.org, protégée par un token secret).
"""
import os
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, jsonify

from config import TIMEZONE, PUBLISH_HOUR, PUBLISH_MINUTE
import database

app = Flask(__name__)
database.init_db()

CRON_SECRET = os.getenv("CRON_SECRET", "")

_job_running = False


def now_local():
    return datetime.now(ZoneInfo(TIMEZONE))


@app.route("/")
def index():
    local_now = now_local()
    today_str = local_now.strftime("%Y-%m-%d")
    yesterday_str = (local_now - timedelta(days=1)).strftime("%Y-%m-%d")

    publish_time_passed = (
        local_now.hour > PUBLISH_HOUR or
        (local_now.hour == PUBLISH_HOUR and local_now.minute >= PUBLISH_MINUTE)
    )

    if publish_time_passed:
        picks = database.get_picks_for_date(today_str)
        display_date = today_str
        mode = "today"
    else:
        picks = database.get_picks_for_date(yesterday_str)
        display_date = yesterday_str
        mode = "yesterday_recap"

    stats_7 = database.get_performance_stats(days=7)
    stats_30 = database.get_performance_stats(days=30)

    return render_template(
        "index.html",
        picks=picks,
        display_date=display_date,
        mode=mode,
        stats_7=stats_7,
        stats_30=stats_30,
        now=local_now.strftime("%d/%m/%Y %H:%M"),
    )


@app.route("/historique")
def historique():
    history = database.get_history(limit_days=60)
    stats_30 = database.get_performance_stats(days=30)
    stats_90 = database.get_performance_stats(days=90)

    grouped = {}
    for pick in history:
        grouped.setdefault(pick["pick_date"], []).append(pick)

    return render_template(
        "history.html",
        grouped=grouped,
        stats_30=stats_30,
        stats_90=stats_90,
    )


def _run_job_background():
    global _job_running
    try:
        from daily_job import run_daily_job
        run_daily_job()
    finally:
        _job_running = False


@app.route("/api/run-daily-job")
def api_run_daily_job():
    """Déclenché quotidiennement par un service externe (cron-job.org).
    Protégé par un token secret passé en paramètre : ?token=..."""
    global _job_running

    token = request.args.get("token", "")
    if not CRON_SECRET or token != CRON_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    if _job_running:
        return jsonify({"status": "already_running"}), 200

    _job_running = True
    thread = threading.Thread(target=_run_job_background, daemon=True)
    thread.start()

    return jsonify({"status": "started"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
