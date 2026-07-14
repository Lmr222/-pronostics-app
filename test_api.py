from api_client import _request
from datetime import datetime, timedelta

today = datetime.utcnow().strftime("%Y-%m-%d")
in_10_days = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")

data = _request(
    "competitions/BSA/matches",
    {"dateFrom": today, "dateTo": in_10_days},
    "test_bsa",
    cache_hours=0
)
print(data)