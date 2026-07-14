"""
Job quotidien exécuté à 9h30 (heure configurée dans config.py).

Étapes :
1. Vérifie les résultats des pronostics publiés les jours précédents (mise à jour won/lost).
2. Récupère TOUS les matchs du jour en un seul appel API (toutes compétitions confondues).
3. Filtre sur les compétitions suivies (config.COMPETITIONS).
4. Récupère le classement de chaque compétition concernée (1 appel par compétition).
5. Calcule la probabilité de chaque match via le moteur de scoring.
6. Garde les meilleurs matchs (max 5) qui dépassent le seuil de confiance.
7. Sauvegarde en base.
"""
from datetime import datetime, timedelta

from config import COMPETITIONS, MAX_PICKS_PER_DAY
import api_client
from api_client import QuotaExceededError
import database
from scoring import evaluate_match, extract_team_profile

FOLLOWED_CODES = {c["code"] for c in COMPETITIONS}
CODE_TO_NAME = {c["code"]: c["name"] for c in COMPETITIONS}


def verify_past_results(today_str: str):
    """Vérifie les résultats des pronostics en attente et met à jour won/lost."""
    pending = database.get_pending_picks_older_than(today_str)
    updated = 0
    for pick in pending:
        try:
            data = api_client.get_match_result(pick["fixture_id"])
            status = data.get("status")
            if status not in ("FINISHED",):
                continue

            score = data.get("score", {}).get("fullTime", {})
            home_goals = score.get("home")
            away_goals = score.get("away")
            if home_goals is None or away_goals is None:
                continue

            score_str = f"{home_goals}-{away_goals}"
            won = _check_market_result(pick["market"], pick["market_label"], home_goals, away_goals, pick)
            database.update_pick_result(pick["id"], "won" if won else "lost", score_str)
            updated += 1
        except QuotaExceededError as e:
            print(str(e))
            break
        except Exception as e:
            print(f"Erreur vérification pick {pick['id']}: {e}")
    print(f"{updated} résultat(s) mis à jour.")


def _check_market_result(market, market_label, home_goals, away_goals, pick):
    total = home_goals + away_goals
    if market == "over_1_5":
        return total > 1.5
    if market == "under_4_5":
        return total < 4.5
    if market == "btts_yes":
        return home_goals > 0 and away_goals > 0
    if market == "double_chance":
        if "1X" in market_label:
            return home_goals >= away_goals
        else:
            return away_goals >= home_goals
    if market == "asian_handicap_plus_0_5":
        if "extérieur" in market_label:
            return away_goals >= home_goals
        else:
            return home_goals >= away_goals
    if market == "favorite_scores":
        team_name = market_label.split(" marque")[0]
        if team_name == pick["home_team"]:
            return home_goals > 0
        else:
            return away_goals > 0
    return False


def _flatten_standings(standings_data):
    """Retourne {team_id: entry} depuis la réponse /competitions/{code}/standings."""
    table = {}
    try:
        for group in standings_data.get("standings", []):
            if group.get("type") != "TOTAL":
                continue
            for entry in group.get("table", []):
                table[entry["team"]["id"]] = entry
    except (KeyError, TypeError):
        pass
    return table


def generate_today_picks():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    candidates = []
    relevant_matches = []

    # Le plan gratuit exige une requête par compétition (l'appel global renvoie vide)
    for comp in COMPETITIONS:
        code = comp["code"]
        try:
            matches_data = api_client.get_matches_for_competition(code, today, today)
        except QuotaExceededError as e:
            print(str(e))
            break
        except Exception as e:
            print(f"Erreur récupération matchs {code}: {e}")
            continue

        day_matches = [
            m for m in matches_data.get("matches", [])
            if m.get("status") in ("SCHEDULED", "TIMED")
        ]
        relevant_matches.extend(day_matches)

        if not day_matches:
            continue

        try:
            standings_data = api_client.get_standings(code)
            standings_table = _flatten_standings(standings_data)
        except QuotaExceededError as e:
            print(str(e))
            break
        except Exception as e:
            print(f"Erreur classement {code}: {e}")
            continue

        for m in day_matches:
            try:
                home_id = m["homeTeam"]["id"]
                away_id = m["awayTeam"]["id"]
                home_name = m["homeTeam"]["name"]
                away_name = m["awayTeam"]["name"]
                match_id = m["id"]
                kickoff = m["utcDate"]

                home_entry = standings_table.get(home_id)
                away_entry = standings_table.get(away_id)

                if not home_entry or not away_entry:
                    continue

                home_profile = extract_team_profile(home_entry)
                away_profile = extract_team_profile(away_entry)

                if home_profile["played"] < 5 or away_profile["played"] < 5:
                    continue

                gap = away_entry.get("position", 10) - home_entry.get("position", 10)

                fixture_info = {"home_team": home_name, "away_team": away_name}
                result = evaluate_match(fixture_info, home_profile, away_profile, standings_gap=gap)

                if result:
                    candidates.append({
                        "pick_date": today,
                        "fixture_id": match_id,
                        "league_name": CODE_TO_NAME.get(code, code),
                        "home_team": home_name,
                        "away_team": away_name,
                        "kickoff_utc": kickoff,
                        **result,
                    })
            except Exception as e:
                print(f"Erreur analyse match {m.get('id')}: {e}")
                continue

    candidates.sort(key=lambda c: c["probability"], reverse=True)
    top_picks = candidates[:MAX_PICKS_PER_DAY]

    for pick in top_picks:
        database.save_pick(pick)

    print(f"{len(top_picks)} pronostic(s) publié(s) pour le {today} "
          f"(sur {len(candidates)} matchs ayant dépassé le seuil, "
          f"{len(relevant_matches)} matchs analysés au total).")
    return top_picks


def run_daily_job():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    print(f"=== Job quotidien {today} ===")
    print("1. Vérification des résultats passés...")
    verify_past_results(today)
    print("2. Génération des pronostics du jour...")
    generate_today_picks()
    print("=== Terminé ===")


if __name__ == "__main__":
    database.init_db()
    run_daily_job()
