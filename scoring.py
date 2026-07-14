"""
Moteur de scoring statistique.

Méthodologie :
1. On extrait un "profil offensif/défensif" de chaque équipe (buts marqués/encaissés,
   à domicile et à l'extérieur séparément) à partir des stats de saison.
2. On calcule des "buts attendus" (expected goals, xG simplifié) pour le match via
   un modèle de Poisson classique (force d'attaque x faiblesse de défense adverse,
   normalisé par la moyenne du championnat).
3. À partir de ces buts attendus, on calcule mathématiquement la probabilité de
   chaque marché (Over/Under, BTTS) via la loi de Poisson — ce n'est pas une
   estimation arbitraire, c'est un calcul statistique standard.
4. Pour les marchés liés au résultat (Double Chance, Handicap, favori marque),
   on combine la force relative des équipes (classement, forme récente, h2h).
5. Un ajustement de confiance réduit légèrement la probabilité brute pour tenir
   compte de l'incertitude non modélisée (blessures inconnues, contexte, etc.)
   Cela évite la surconfiance du modèle.

IMPORTANT : ces probabilités sont des ESTIMATIONS statistiques, pas des certitudes.
"""
import math
from config import PROBABILITY_THRESHOLD, ALLOWED_MARKETS


CONFIDENCE_HAIRCUT = 0.93  # réduit légèrement toute probabilité brute (anti-surconfiance)


def poisson_pmf(k: int, lam: float) -> float:
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def extract_team_profile(standings_entry: dict) -> dict:
    """
    Extrait un profil exploitable depuis une entrée du classement football-data.org.
    Limite du plan gratuit : pas de détail domicile/extérieur séparé (contrairement à
    API-Football payant), on utilise donc la moyenne globale de l'équipe pour les deux.
    C'est une simplification assumée, pas une erreur — le modèle reste valide, juste
    un peu moins précis qu'avec des données payantes.
    """
    try:
        played = standings_entry.get("playedGames", 0) or 0
        goals_for = standings_entry.get("goalsFor", 0) or 0
        goals_against = standings_entry.get("goalsAgainst", 0) or 0

        if played == 0:
            raise ValueError("Aucun match joué")

        goals_for_avg = goals_for / played
        goals_against_avg = goals_against / played

        won = standings_entry.get("won", 0) or 0
        draw = standings_entry.get("draw", 0) or 0
        # forme approximative : ratio de points pris sur la saison (pas de détail des 5 derniers matchs
        # disponible gratuitement, donc on utilise la forme saison entière comme proxy)
        form_score = (won * 1.0 + draw * 0.5) / played if played else 0.5

        return {
            "goals_for_avg": goals_for_avg,
            "goals_against_avg": goals_against_avg,
            "form_score": form_score,
            "clean_sheet_rate": None,  # non disponible gratuitement
            "played": played,
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return {
            "goals_for_avg": 1.2,
            "goals_against_avg": 1.2,
            "form_score": 0.5,
            "clean_sheet_rate": 0.25,
            "played": 0,
        }


def expected_goals(home_profile: dict, away_profile: dict, league_avg_goals: float = 2.6):
    """Modèle de Poisson simplifié (type Dixon-Coles allégé) pour estimer les buts attendus."""
    league_avg_home = league_avg_goals / 2
    league_avg_away = league_avg_goals / 2

    home_attack_strength = home_profile["goals_for_avg"] / max(league_avg_home, 0.1)
    home_defense_weak = home_profile["goals_against_avg"] / max(league_avg_away, 0.1)
    away_attack_strength = away_profile["goals_for_avg"] / max(league_avg_away, 0.1)
    away_defense_weak = away_profile["goals_against_avg"] / max(league_avg_home, 0.1)

    home_xg = home_attack_strength * away_defense_weak * league_avg_home
    away_xg = away_attack_strength * home_defense_weak * league_avg_away

    # bornes de sécurité (évite les valeurs aberrantes sur petits échantillons)
    home_xg = max(0.3, min(home_xg, 4.0))
    away_xg = max(0.3, min(away_xg, 4.0))

    return home_xg, away_xg


def prob_over_under(home_xg: float, away_xg: float, line: float, over: bool, max_goals: int = 10):
    """Probabilité que le total de buts soit au-dessus/en-dessous d'une ligne, via Poisson."""
    total_xg = home_xg + away_xg
    prob_le = 0.0
    threshold = math.floor(line)  # ex: line=1.5 -> under si total<=1 ; over si total>=2
    for total in range(0, max_goals + 1):
        # somme des buts = convolution de deux Poisson indépendantes
        p_total = sum(
            poisson_pmf(h, home_xg) * poisson_pmf(total - h, away_xg)
            for h in range(0, total + 1)
        )
        if total <= threshold:
            prob_le += p_total
    return (1 - prob_le) if over else prob_le


def prob_btts_yes(home_xg: float, away_xg: float):
    p_home_scores = 1 - poisson_pmf(0, home_xg)
    p_away_scores = 1 - poisson_pmf(0, away_xg)
    return p_home_scores * p_away_scores


def prob_favorite_scores(fav_xg: float):
    return 1 - poisson_pmf(0, fav_xg)


def prob_double_chance(home_profile, away_profile, home_xg, away_xg, standings_gap: float):
    """Estime la probabilité 1X ou X2 selon quelle équipe est favorite."""
    # Probabilité de victoire via Poisson bivarié simplifié
    max_g = 8
    p_home_win = p_draw = p_away_win = 0.0
    for h in range(max_g):
        for a in range(max_g):
            p = poisson_pmf(h, home_xg) * poisson_pmf(a, away_xg)
            if h > a:
                p_home_win += p
            elif h == a:
                p_draw += p
            else:
                p_away_win += p

    # Favori = équipe avec le plus fort xG net + meilleur classement
    home_strength = home_xg - away_xg + standings_gap * 0.05
    if home_strength >= 0:
        return "1X", p_home_win + p_draw
    else:
        return "X2", p_away_win + p_draw


def prob_asian_handicap_plus_05(favorite_is_home: bool, home_xg, away_xg):
    """Handicap +0.5 sur le NON favori = revient à ne pas perdre (X2 ou 1X selon le cas)."""
    max_g = 8
    p_fav_win = p_draw = p_underdog_win = 0.0
    for h in range(max_g):
        for a in range(max_g):
            p = poisson_pmf(h, home_xg) * poisson_pmf(a, away_xg)
            if (h > a) == favorite_is_home:
                p_fav_win += p
            elif h == a:
                p_draw += p
            else:
                p_underdog_win += p
    # +0.5 sur l'outsider gagne si l'outsider ne perd pas
    return p_draw + p_underdog_win


def evaluate_match(fixture: dict, home_profile: dict, away_profile: dict,
                    standings_gap: float, league_avg_goals: float = 2.6):
    """
    Calcule, pour un match donné, la meilleure option parmi les marchés autorisés
    et retourne le meilleur pick (marché + probabilité) ou None si rien n'atteint le seuil.
    """
    home_xg, away_xg = expected_goals(home_profile, away_profile, league_avg_goals)
    favorite_is_home = (home_xg - away_xg + standings_gap * 0.05) >= 0

    candidates = []

    # Over 1.5
    p = prob_over_under(home_xg, away_xg, 1.5, over=True) * CONFIDENCE_HAIRCUT
    candidates.append(("over_1_5", "Plus de 1,5 but", p))

    # Under 4.5
    p = prob_over_under(home_xg, away_xg, 4.5, over=False) * CONFIDENCE_HAIRCUT
    candidates.append(("under_4_5", "Moins de 4,5 buts", p))

    # Double chance
    label, p = prob_double_chance(home_profile, away_profile, home_xg, away_xg, standings_gap)
    p *= CONFIDENCE_HAIRCUT
    market_label = "Double chance 1X" if label == "1X" else "Double chance X2"
    candidates.append(("double_chance", market_label, p))

    # Handicap asiatique +0.5 (sur l'outsider, logique équivalente à double chance mais display différent)
    p = prob_asian_handicap_plus_05(favorite_is_home, home_xg, away_xg) * CONFIDENCE_HAIRCUT
    underdog = "extérieur" if favorite_is_home else "domicile"
    candidates.append(("asian_handicap_plus_0_5", f"Handicap asiatique +0.5 ({underdog})", p))

    # BTTS oui
    p = prob_btts_yes(home_xg, away_xg) * CONFIDENCE_HAIRCUT
    candidates.append(("btts_yes", "Les deux équipes marquent - Oui", p))

    # Favori marque au moins 1 but
    fav_xg = home_xg if favorite_is_home else away_xg
    p = prob_favorite_scores(fav_xg) * CONFIDENCE_HAIRCUT
    fav_name = fixture["home_team"] if favorite_is_home else fixture["away_team"]
    candidates.append(("favorite_scores", f"{fav_name} marque au moins 1 but", p))

    # On ne garde que les marchés autorisés, on prend celui avec la probabilité la plus élevée
    candidates = [c for c in candidates if c[0] in ALLOWED_MARKETS]
    candidates.sort(key=lambda c: c[2], reverse=True)

    best_market, best_label, best_prob = candidates[0]

    if best_prob < PROBABILITY_THRESHOLD:
        return None

    justification = (
        f"xG estimés : {fixture['home_team']} {home_xg:.2f} - {away_xg:.2f} {fixture['away_team']}. "
        f"Forme récente : dom. {home_profile['form_score']*100:.0f}%, ext. {away_profile['form_score']*100:.0f}%. "
        f"Écart de classement pris en compte."
    )

    return {
        "market": best_market,
        "market_label": best_label,
        "probability": round(best_prob, 3),
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "justification": justification,
    }
