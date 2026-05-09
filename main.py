import os
import requests

LEETIFY_API_KEY = os.environ.get("LEETIFY_API_KEY")
SCOREBOARD_WEBHOOK = os.environ.get("SCOREBOARD_WEBHOOK")
SEEN_MATCHES_FILE = "seen_matches.txt"

BASE_URL = "https://api-public.cs-prod.leetify.com"

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

def load_seen_matches():
    if not os.path.exists(SEEN_MATCHES_FILE):
        return set()
    with open(SEEN_MATCHES_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())

def save_seen_match(match_id):
    with open(SEEN_MATCHES_FILE, "a") as f:
        f.write(f"{match_id}\n")

def fetch_latest_match(steam_id):
    """
    Fetch the most recent match for a player using the Leetify v3 API.
    NOTE: As of January 2026, Leetify only returns data for registered users.
    All tracked players must have a Leetify account.
    API docs: https://api-public-docs.cs-prod.leetify.com/
    """
    url = f"{BASE_URL}/v3/profile/matches"
    headers = {"_leetify_key": LEETIFY_API_KEY}
    params = {"steamId": steam_id}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            matches = response.json()
            if matches and len(matches) > 0:
                return matches[0]
        elif response.status_code == 404:
            print(f"  → 404: Player {steam_id} may not have a Leetify account, or their profile is hidden.")
            print(f"     All players must sign up at https://leetify.com to be trackable.")
        else:
            print(f"  → HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"  → API error: {e}")
    return None

def find_player_stats(match, steam_id):
    """
    The v3 API returns stats for all players in a match.
    We need to find the stats for our specific player.
    """
    stats_list = match.get("stats", [])
    for stat in stats_list:
        if str(stat.get("steamId", "")) == str(steam_id):
            return stat
    # Fallback: if stats is a single object (old format), return it directly
    if not stats_list and "kills" in match:
        return match
    return {}

def format_rating(rating):
    """Leetify rating is typically a float like 0.234. Display as e.g. +23.4"""
    try:
        val = float(rating)
        display = round(val * 100, 1)
        return f"+{display}" if val > 0 else str(display)
    except (TypeError, ValueError):
        return str(rating)

def send_individual_webhook(webhook_url, player_name, match, steam_id):
    if not webhook_url:
        return

    map_name = match.get("mapName") or match.get("map_name", "Unknown")
    stats = find_player_stats(match, steam_id)

    rating = stats.get("leetifyRating") or stats.get("leetify_rating", "N/A")
    kills = stats.get("kills") or stats.get("totalKills") or stats.get("total_kills", 0)
    deaths = stats.get("deaths", 0)

    rating_str = format_rating(rating) if rating != "N/A" else "N/A"

    embed = {
        "title": f"New Match on {map_name}",
        "color": 15277667,
        "fields": [
            {"name": "Leetify Rating", "value": f"**{rating_str}**", "inline": True},
            {"name": "K/D", "value": f"{kills} / {deaths}", "inline": True}
        ],
        "thumbnail": {"url": "https://leetify.com/assets/images/logo/logo-leetify.png"},
        "footer": {"text": f"Data provided by Leetify"}
    }

    result = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
    if result.status_code not in (200, 204):
        print(f"  → Webhook failed for {player_name}: HTTP {result.status_code}")

def send_scoreboard_webhook(match_id, map_name, players):
    if not SCOREBOARD_WEBHOOK:
        return
    if len(players) < 2:
        print(f"  → Skipping scoreboard for {match_id} (only {len(players)} player tracked)")
        return

    players.sort(key=lambda x: float(x.get("rating", -99) or -99), reverse=True)

    description_lines = []
    for i, p in enumerate(players, 1):
        rating_str = format_rating(p["rating"]) if p["rating"] is not None else "N/A"
        description_lines.append(
            f"**{i}. {p['name']}**: {rating_str} Rating ({p['kills']}K / {p['deaths']}D)"
        )

    embed = {
        "title": f"🏆 Match Scoreboard: {map_name}",
        "description": "\n".join(description_lines),
        "color": 3447003,
        "footer": {"text": f"Match ID: {match_id} • Data provided by Leetify"}
    }

    result = requests.post(SCOREBOARD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    if result.status_code not in (200, 204):
        print(f"  → Scoreboard webhook failed: HTTP {result.status_code}")

def main():
    seen_matches = load_seen_matches()
    grouped_matches = {}
    new_match_ids = set()

    for steam_id, info in PLAYER_INFO.items():
        print(f"Checking matches for {info['name']} ({steam_id})...")
        latest_match = fetch_latest_match(steam_id)
        if not latest_match:
            print(f"  → No match data returned for {info['name']}")
            continue

        # Try both camelCase and snake_case field names across API versions
        match_id = latest_match.get("matchId") or latest_match.get("id")
        if not match_id:
            print(f"  → Could not find match ID in response for {info['name']}")
            continue

        if match_id in seen_matches:
            print(f"  → Already seen latest match for {info['name']} ({match_id})")
            continue

        print(f"  → NEW match found for {info['name']} ({match_id})")
        new_match_ids.add(match_id)

        send_individual_webhook(info["webhook"], info["name"], latest_match, steam_id)

        map_name = latest_match.get("mapName") or latest_match.get("map_name", "Unknown")
        stats = find_player_stats(latest_match, steam_id)
        rating = stats.get("leetifyRating") or stats.get("leetify_rating")
        kills = stats.get("kills") or stats.get("totalKills") or stats.get("total_kills", 0)
        deaths = stats.get("deaths", 0)

        if match_id not in grouped_matches:
            grouped_matches[match_id] = {"map_name": map_name, "players": []}

        grouped_matches[match_id]["players"].append({
            "name": info["name"],
            "rating": rating,
            "kills": kills,
            "deaths": deaths
        })

    for match_id, match_data in grouped_matches.items():
        send_scoreboard_webhook(match_id, match_data["map_name"], match_data["players"])

    for match_id in new_match_ids:
        save_seen_match(match_id)
        print(f"Saved {match_id} to seen_matches.txt")

    if not new_match_ids:
        print("No new matches found this run.")

if __name__ == "__main__":
    main()
