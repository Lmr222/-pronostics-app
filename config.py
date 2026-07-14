"""
Configuration centrale de l'application.
Charge la clé API et les paramètres depuis le fichier .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Clé API (football-data.org - gratuit, inclut la saison en cours) ---
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", os.getenv("RAPIDAPI_KEY", ""))
API_BASE_URL = "https://api.football-data.org/v4"

if not FOOTBALL_DATA_TOKEN:
    print("⚠️  ATTENTION : FOOTBALL_DATA_TOKEN n'est pas définie. Renseigne-la dans .env.")

# --- Base de données ---
DB_PATH = os.getenv("DB_PATH", "pronostics.db")

# --- Fuseau horaire ---
TIMEZONE = os.getenv("TIMEZONE", "Africa/Bamako")  # UTC, pas de DST

# --- Heure de publication quotidienne ---
PUBLISH_HOUR = 9
PUBLISH_MINUTE = 30

# --- Seuil minimum de probabilité pour qu'un match soit retenu ---
PROBABILITY_THRESHOLD = 0.75  # 75%

# --- Nombre maximum de pronostics par jour ---
MAX_PICKS_PER_DAY = 5

# --- Respect du rate limit football-data.org (10 requêtes/minute sur le plan gratuit) ---
MIN_SECONDS_BETWEEN_CALLS = 6.5  # marge de sécurité (~9 appels/minute max)

# --- Compétitions suivies (les 12 disponibles gratuitement, à vie, sur football-data.org) ---
COMPETITIONS = [
    {"code": "PL", "name": "Premier League (Angleterre)"},
    {"code": "PD", "name": "La Liga (Espagne)"},
    {"code": "BL1", "name": "Bundesliga (Allemagne)"},
    {"code": "SA", "name": "Serie A (Italie)"},
    {"code": "FL1", "name": "Ligue 1 (France)"},
    {"code": "DED", "name": "Eredivisie (Pays-Bas)"},
    {"code": "PPL", "name": "Primeira Liga (Portugal)"},
    {"code": "ELC", "name": "Championship (Angleterre, D2)"},
    {"code": "BSA", "name": "Série A (Brésil)"},
    {"code": "CL", "name": "Ligue des Champions"},
]

# --- Marchés autorisés, dans l'ordre de priorité (du plus stable au moins stable) ---
ALLOWED_MARKETS = [
    "double_chance",
    "asian_handicap_plus_0_5",
    "over_1_5",
    "under_4_5",
    "btts_yes",
    "favorite_scores",
]

