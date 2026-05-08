import os
import requests
from datetime import datetime, timezone, timedelta

LEETIFY_API_KEY = os.environ.get("LEETIFY_API_KEY")
SCOREBOARD_WEBHOOK = os.environ.get("SCOREBOARD_WEBHOOK")

PLAYER_INFO = {
    "76561198190033377": {"name": "Tudor", "webhook": os.environ.get("TUDOR_WEBHOOK")},
    "76561198435523362": {"name": "Siddoru", "webhook": os.environ.get("SIDDORU_WEBHOOK")},
    "76561199033222316": {"name": "Puya", "webhook": os.environ.get("PUYA_WEBHOOK")},
    "76561198771342370": {"name": "Robi", "webhook": os.environ.get("ROBI_WEBHOOK")},
    "76561199236732682": {"name": "Andre1", "webhook": os.environ.get("ANDRE1_WEBHOOK")},
    "76561199226839952": {"name": "Diddyplayscs2_6741", "webhook": os.environ.get("DIDDY_WEBHOOK")},
    "76561198983778721": {"name": "Nebunulajokuri777", "webhook": os.environ.get("NEBUNULAJOKURI_WEBHOOK")},
    "76561198838107739": {"name": "ULTRADARKSHADOWPROMEGAKILLER777", "webhook": os.environ.get("ULTRA_WEBHOOK")}
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

def send_individual_webhook(webhook_url, match):
    if not webhook_url: 
        return
        
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

def send_scoreboard_webhook(match_id, map_name, players):
    if not SCOREBOARD_WEBHOOK: 
        return
    
    players.sort(key=lambda x: x.get('rating', -99), reverse=True)
    
    description_lines = []
    for i, p in enumerate(players, 1):
        rating = p['rating']
        rating_str = f"+{rating}" if isinstance(rating, (int, float)) and rating > 0 else str(rating)
        description_lines.append(f"**{i}. {p['name']}**: {rating_str} Rating ({p['kills']}K / {p['deaths']}D)")
        
    embed = {
        "title": f"🏆 Match Scoreboard: {map_name}",
        "description": "\n".join(description_lines),
        "color": 3447003,
        "footer": {"text": f"Match ID: {match_id}"}
    }
    
    requests.post(SCOREBOARD_WEBHOOK, json={"embeds": [embed]})

def main():
    time_limit = datetime.now(timezone.utc) - timedelta(minutes=20)
    
    grouped_matches = {}
    
    for steam_id, info in PLAYER_INFO.items():
        latest_match = fetch_latest_match(steam_id)
        if not latest_match:
            continue
            
        finished_at_str = latest_match.get("gameFinishedAt")
        if finished_at_str:
            if finished_at_str.endswith('Z'):
                finished_at_str = finished_at_str[:-1] + '+00:00'
            
            finished_at = datetime.fromisoformat(finished_at_str)
            
            if finished_at > time_limit:
                send_individual_webhook(info["webhook"], latest_match)
                
                match_id = latest_match.get("matchId")
                if match_id:
                    if match_id not in grouped_matches:
                        grouped_matches[match_id] = {
                            "map_name": latest_match.get("mapName", "Unknown"),
                            "players": []
                        }
                    
                    grouped_matches[match_id]["players"].append({
                        "name": info["name"],
                        "rating": latest_match.get("leetifyRating", 0),
                        "kills": latest_match.get("kills", 0),
                        "deaths": latest_match.get("deaths", 0)
                    })
                    
    for match_id, match_data in grouped_matches.items():
        if len(match_data["players"]) >= 1: 
            send_scoreboard_webhook(match_id, match_data["map_name"], match_data["players"])

if __name__ == "__main__":
    main()
