"""
Planificateur : lance daily_job.run_daily_job() automatiquement chaque jour à l'heure configurée.
À lancer en tâche de fond, séparément du serveur web (app.py).

Utilisation :
    python scheduler.py
Laisse tourner ce process en continu (ex. avec un service systemd, ou `nohup python scheduler.py &`).
"""
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import TIMEZONE, PUBLISH_HOUR, PUBLISH_MINUTE
import database
from daily_job import run_daily_job

database.init_db()

scheduler = BlockingScheduler(timezone=TIMEZONE)

scheduler.add_job(
    run_daily_job,
    trigger=CronTrigger(hour=PUBLISH_HOUR, minute=PUBLISH_MINUTE),
    id="daily_pronostics_job",
    name="Génération quotidienne des pronostics",
    misfire_grace_time=3600,
)

if __name__ == "__main__":
    print(f"Planificateur démarré. Prochaine exécution : tous les jours à {PUBLISH_HOUR:02d}:{PUBLISH_MINUTE:02d} ({TIMEZONE}).")
    print("Ctrl+C pour arrêter.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Planificateur arrêté.")
