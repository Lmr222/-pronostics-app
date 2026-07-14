"""
Gestion de la base de données SQLite.
Stocke : les pronostics du jour, l'historique complet, le cache de données API
(pour économiser le quota quotidien), et les résultats réels pour le suivi de performance.
"""
import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pick_date TEXT NOT NULL,
                fixture_id INTEGER NOT NULL,
                league_name TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                kickoff_utc TEXT NOT NULL,
                market TEXT NOT NULL,
                market_label TEXT NOT NULL,
                odds REAL,
                probability REAL NOT NULL,
                justification TEXT,
                result TEXT DEFAULT 'pending',   -- 'pending' | 'won' | 'lost' | 'void'
                actual_score TEXT,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                cached_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                usage_date TEXT PRIMARY KEY,
                calls_made INTEGER NOT NULL DEFAULT 0
            )
        """)


# ---------- Gestion du quota d'appels API ----------

def get_calls_made_today() -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_db() as conn:
        row = conn.execute(
            "SELECT calls_made FROM api_usage WHERE usage_date = ?", (today,)
        ).fetchone()
        return row["calls_made"] if row else 0


def increment_api_calls(n: int = 1):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_db() as conn:
        conn.execute("""
            INSERT INTO api_usage (usage_date, calls_made) VALUES (?, ?)
            ON CONFLICT(usage_date) DO UPDATE SET calls_made = calls_made + ?
        """, (today, n, n))


# ---------- Cache générique (réduit les appels API redondants) ----------

def cache_get(key: str, max_age_hours: int = 20):
    with get_db() as conn:
        row = conn.execute(
            "SELECT payload, cached_at FROM api_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        cached_at = datetime.fromisoformat(row["cached_at"])
        if datetime.utcnow() - cached_at > timedelta(hours=max_age_hours):
            return None
        return json.loads(row["payload"])


def cache_set(key: str, payload):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO api_cache (cache_key, payload, cached_at) VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET payload = ?, cached_at = ?
        """, (key, json.dumps(payload), datetime.utcnow().isoformat(),
              json.dumps(payload), datetime.utcnow().isoformat()))


# ---------- Pronostics ----------

def save_pick(pick: dict):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO picks (
                pick_date, fixture_id, league_name, home_team, away_team,
                kickoff_utc, market, market_label, odds, probability,
                justification, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pick["pick_date"], pick["fixture_id"], pick["league_name"],
            pick["home_team"], pick["away_team"], pick["kickoff_utc"],
            pick["market"], pick["market_label"], pick.get("odds"),
            pick["probability"], pick.get("justification", ""),
            datetime.utcnow().isoformat()
        ))


def get_picks_for_date(pick_date: str):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM picks WHERE pick_date = ? ORDER BY probability DESC",
            (pick_date,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_pick_result(pick_id: int, result: str, actual_score: str = None):
    with get_db() as conn:
        conn.execute(
            "UPDATE picks SET result = ?, actual_score = ? WHERE id = ?",
            (result, actual_score, pick_id)
        )


def get_pending_picks_older_than(pick_date: str):
    """Récupère les pronostics passés dont le résultat n'a pas encore été vérifié."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM picks WHERE result = 'pending' AND pick_date <= ?",
            (pick_date,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_performance_stats(days: int = 30):
    """Calcule le taux de réussite réel sur les N derniers jours (transparence totale)."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute("""
            SELECT result, COUNT(*) as n FROM picks
            WHERE pick_date >= ? AND result != 'pending'
            GROUP BY result
        """, (cutoff,)).fetchall()

    stats = {"won": 0, "lost": 0, "void": 0}
    for r in rows:
        stats[r["result"]] = r["n"]

    total_decided = stats["won"] + stats["lost"]
    win_rate = (stats["won"] / total_decided * 100) if total_decided else None

    return {
        "won": stats["won"],
        "lost": stats["lost"],
        "void": stats["void"],
        "total_decided": total_decided,
        "win_rate": round(win_rate, 1) if win_rate is not None else None,
    }


def get_history(limit_days: int = 30):
    cutoff = (datetime.utcnow() - timedelta(days=limit_days)).strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM picks WHERE pick_date >= ?
            ORDER BY pick_date DESC, probability DESC
        """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]
