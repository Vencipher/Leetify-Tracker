import os
import requests
from datetime import datetime, timezone, timedelta

LEETIFY_API_KEY = os.environ.get("LEETIFY_API_KEY")

PLAYERS = {
    "76561198190033377": os.environ.get("TUDOR_WEBHOOK"),
    "76561198435523362": os.environ.get("SIDDORU_WEBHOOK"),
    "76561199033222316": os.environ.get("PUYA_WEBHOOK"),
    "76561198771342370": os.environ.get("ROBI_WEBHOOK"),
    "76561199236732682": os.environ.get("ANDRE1_WEBHOOK"),
    "76561199226839952": os.environ.get("DIDDY_WEBHOOK"),
    "76561198983778721": os.environ.get("NEBUNULAJOKURI_WEBHOOK"),
    "76561198838107739": os.environ.get("ULTRA_WEBHOOK")
}

def fetch_latest_match(steam_id):
    url = f"https://api-public.cs-prod.leetify.com/api/v1/players/{steam_id}/matches"
    headers = {"_leetify_key": LEETIFY_API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            matches = response.json()
            if matches and len(matches) > 0:
                return matches[0]
    except Exception:
        pass
    return None

def send_to_discord(webhook_url, match):
    map_name = match.get("mapName", "Unknown")
    rating = match.get("leetifyRating", "N/A")
    kills = match.get("kills", 0)
    deaths = match.get("deaths", 0)
    
    embed = {
        "title": f"New Match on {map_name}",
        "color": 15277667,
        "fields": [
            {"name": "Leetify Rating", "value": f"**{rating}**", "inline": True},
            {"name": "K/D", "value": f"{kills} / {deaths}", "inline": True}
        ],
        "thumbnail": {"url": "https://leetify.com/assets/images/logo/logo-leetify.png"}
    }
    
    requests.post(webhook_url, json={"embeds": [embed]})

def main():
    time_limit = datetime.now(timezone.utc) - timedelta(minutes=20)
    
    for steam_id, webhook in PLAYERS.items():
        if not webhook or not steam_id or steam_id.startswith("STEAM_ID_"):
            continue
            
        latest_match = fetch_latest_match(steam_id)
        if not latest_match:
            continue
            
        finished_at_str = latest_match.get("gameFinishedAt")
        if finished_at_str:
            if finished_at_str.endswith('Z'):
                finished_at_str = finished_at_str[:-1] + '+00:00'
            
            finished_at = datetime.fromisoformat(finished_at_str)
            
            if finished_at > time_limit:
                send_to_discord(webhook, latest_match)

if __name__ == "__main__":
    main()
