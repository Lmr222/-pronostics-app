# Pronostics — Analyse statistique quotidienne

Application qui analyse chaque jour les matchs d'une sélection de championnats de football,
calcule des probabilités statistiques réelles (modèle de Poisson basé sur les données de forme,
buts marqués/encaissés, classement) et publie jusqu'à 5 pronostics dont la probabilité estimée
dépasse 75%.

⚠️ **Important** : les probabilités affichées sont des estimations statistiques, pas des
garanties. Aucun système ne peut prédire le sport avec certitude. Ne misez que ce que vous
pouvez vous permettre de perdre.

---

## 1. Installation

```bash
# Se placer dans le dossier du projet
cd pronostics_app

# Installer les dépendances
pip install -r requirements.txt --break-system-packages
# (ou dans un environnement virtuel : python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt)
```

## 2. Créer un compte et obtenir ton token (gratuit)

1. Va sur https://www.football-data.org/client/register
2. Inscris-toi (gratuit, pas de carte bancaire)
3. Ton token (clé API) est affiché après inscription, et dans ton espace client
4. Copie `.env.example` vers `.env` :
   ```bash
   cp .env.example .env
   ```
5. Ouvre `.env` et remplace `colle_ton_token_ici` par ton vrai token.
6. **Ne partage jamais ce fichier `.env`** (ne le mets pas sur GitHub public, ne l'envoie à
   personne). Il contient ta clé secrète.

**Pourquoi football-data.org et pas API-Football ?** Le plan gratuit d'API-Football
n'inclut pas la saison en cours (seulement des saisons archivées 2022-2024), ce qui le
rend inutilisable pour un usage quotidien en temps réel. football-data.org, en
revanche, inclut gratuitement et à vie 12 grandes compétitions (Premier League, La Liga,
Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga, Championship, Serie A Brésil,
Champions League) avec les données de la saison actuelle.

## 3. Vérifier que le token fonctionne

```bash
python3 -c "
from api_client import get_matches_by_date
from datetime import datetime
today = datetime.utcnow().strftime('%Y-%m-%d')
data = get_matches_by_date('PL', today)  # PL = Premier League
print(data)
"
```
Si tu vois une réponse JSON avec une liste de matchs (ou vide si pas de matchs aujourd'hui),
la connexion fonctionne. Si tu vois une erreur 403, vérifie ton token dans `.env`.

## 4. Générer les pronostics manuellement (test)

```bash
python3 daily_job.py
```
Cela va :
- vérifier les résultats des pronostics précédents (s'il y en a)
- scanner les championnats configurés dans `config.py`
- calculer les probabilités et sauvegarder les meilleurs matchs du jour

## 5. Lancer le site web (dashboard)

```bash
python3 app.py
```
Puis ouvre `http://localhost:5000` dans ton navigateur.
- Avant 9h30 : affiche le bilan de la veille
- Après 9h30 : affiche les pronostics du jour
- `/historique` : historique complet + taux de réussite réel

## 6. Automatiser la publication quotidienne à 9h30

Dans un **second terminal**, en parallèle du site web, lance :
```bash
python3 scheduler.py
```
Laisse ce process tourner en continu (il exécute `daily_job.py` automatiquement tous les
jours à 9h30). Pour le garder actif même après fermeture du terminal :
```bash
nohup python3 scheduler.py > scheduler.log 2>&1 &
```

---

## Limite importante : rate limit gratuit

Le plan gratuit de football-data.org autorise **10 requêtes par minute**, sans limite
quotidienne stricte annoncée, et couvre **12 grandes compétitions** avec les données de
la saison en cours (déjà configurées dans `config.py`, modifiable dans `COMPETITIONS`).
L'application espace automatiquement ses appels pour respecter cette limite
(`MIN_SECONDS_BETWEEN_CALLS` dans `config.py`) et met les données en cache pour éviter
les appels redondants (classements en cache 20h, matchs du jour 6h).

Pour couvrir davantage de compétitions (championnats plus petits, deuxièmes divisions
d'autres pays, etc.), il faut un plan payant chez football-data.org ou un autre
fournisseur comme API-Football.

## Modifier la liste des compétitions suivies

Dans `config.py`, modifie la liste `COMPETITIONS`. La liste des codes disponibles sur le
plan gratuit se trouve sur https://www.football-data.org/coverage

## Déploiement en ligne (optionnel, gratuit)

Pour que l'app soit accessible en dehors de ton PC :
- **Render.com** (plan gratuit) : héberge `app.py` (web service) + `scheduler.py`
  (background worker) séparément
- **Railway.app** (plan gratuit avec limites) : même principe
- Pense à configurer la variable d'environnement `RAPIDAPI_KEY` dans les paramètres de
  la plateforme (jamais en dur dans le code envoyé en ligne)

## Structure du projet

```
pronostics_app/
├── config.py         # Paramètres (clé API, championnats, seuils)
├── database.py       # Base SQLite (picks, cache, historique)
├── api_client.py      # Appels à API-Football avec cache + gestion de quota
├── scoring.py         # Moteur statistique (modèle de Poisson)
├── daily_job.py        # Orchestration quotidienne
├── scheduler.py        # Planificateur (exécution auto à 9h30)
├── app.py              # Serveur web (dashboard)
├── templates/           # Pages HTML
├── requirements.txt
└── .env.example
```
