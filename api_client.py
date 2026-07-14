"""
Client pour football-data.org (gratuit en permanence, inclut la saison en cours).
Documentation : https://www.football-data.org/documentation/quickstart

Toute requête passe par ce module pour :
  1. vérifier le cache avant d'appeler l'API (économie de quota)
  2. respecter la limite de 10 requêtes/minute du plan gratuit (throttling automatique)
  3. logger les appels effectués
"""
import time
import requests
from config import FOOTBALL_DATA_TOKEN, API_BASE_URL, MIN_SECONDS_BETWEEN_CALLS
from database import cache_get, cache_set, increment_api_calls


class QuotaExceededError(Exception):
    """Levée en cas de blocage prolongé par l'API (429 répété)."""
    pass


HEADERS = {
    "X-Auth-Token": FOOTBALL_DATA_TOKEN,
}

_last_call_time = 0.0


def _throttle():
    """Attend le temps nécessaire pour respecter la limite de 10 req/min."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call_time = time.time()


def _request(endpoint: str, params: dict, cache_key: str, cache_hours: int = 20):
    """Appel générique avec cache + throttling automatique."""
    cached = cache_get(cache_key, max_age_hours=cache_hours)
    if cached is not None:
        return cached

    _throttle()

    url = f"{API_BASE_URL}/{endpoint}"
    resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
    increment_api_calls(1)

    if resp.status_code == 429:
        # Trop de requêtes malgré le throttling : on attend 60s et on retente une fois
        time.sleep(60)
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        increment_api_calls(1)
        if resp.status_code == 429:
            raise QuotaExceededError("Limite de requêtes atteinte (429) même après attente. Réessaie plus tard.")

    resp.raise_for_status()
    data = resp.json()
    cache_set(cache_key, data)
    return data


def get_matches_for_competition(competition_code: str, date_from: str, date_to: str):
    """Récupère les matchs d'UNE compétition précise sur une plage de dates.
    Sur le plan gratuit, l'endpoint global /matches renvoie une liste vide :
    il faut systématiquement préciser la compétition."""
    cache_key = f"matches:{competition_code}:{date_from}:{date_to}"
    return _request(
        f"competitions/{competition_code}/matches",
        {"dateFrom": date_from, "dateTo": date_to},
        cache_key,
        cache_hours=4,
    )


def get_team_matches(team_id: int, limit: int = 15):
    """Derniers matchs terminés d'une équipe (toutes compétitions). Sert à calculer
    la forme et les moyennes de buts. Mis en cache longtemps : évolue lentement."""
    cache_key = f"team_matches:{team_id}:{limit}"
    return _request(
        f"teams/{team_id}/matches",
        {"status": "FINISHED", "limit": limit},
        cache_key,
        cache_hours=20,
    )


def get_standings(competition_code: str):
    """Classement actuel d'une compétition."""
    cache_key = f"standings:{competition_code}"
    return _request(
        f"competitions/{competition_code}/standings",
        {},
        cache_key,
        cache_hours=20,
    )


def get_match_result(match_id: int):
    """Résultat final d'un match précis, pour vérifier les pronostics passés."""
    cache_key = f"match_result:{match_id}"
    return _request(
        f"matches/{match_id}",
        {},
        cache_key,
        cache_hours=999999,  # un match terminé ne change plus, cache permanent
    )
