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

def get_headers():
    return {"_leetify_key": LEETIFY_API_KEY}

def fetch_latest_match(steam_id):
    """
    GET /v3/profile?steam64_id={steam_id}
    Returns profile with recent_matches array.
    Each match has: id, map_name, leetify_rating, outcome, score, finished_at
    NOTE: All tracked players must have a Leetify account at leetify.com
    """
    url = f"{BASE_URL}/v3/profile"
    params = {"steam64_id": steam_id}

    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=15)
        print(f"  → HTTP {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                print(f"  → API error: {data['error']}")
                return None
            recent = data.get("recent_matches", [])
            if recent:
                return recent[0]
            else:
                print(f"  → No recent matches in profile.")
                return None
        elif response.status_code == 404:
            print(f"  → Player not found. They must sign up at leetify.com first.")
        elif response.status_code == 401:
            print(f"  → Invalid API key.")
        else:
            print(f"  → Unexpected: {response.text[:200]}")

    except Exception as e:
        print(f"  → Error ({type(e).__name__}): {e}")

    return None

def format_rating(rating):
    """leetify_rating is a float like -0.0014. Display as e.g. -0.14"""
    try:
        val = float(rating)
        display = round(val * 100, 1)
        return f"+{display}" if val >= 0 else str(display)
    except (TypeError, ValueError):
        return "N/A"

def outcome_emoji(outcome):
    return {"win": "✅", "loss": "❌", "tie": "➖"}.get(outcome, "❓")

def send_individual_webhook(webhook_url, player_name, match):
    if not webhook_url:
        return

    map_name = match.get("map_name", "Unknown")
    rating = match.get("leetify_rating")
    outcome = match.get("outcome", "unknown")
    score = match.get("score", [])
    score_str = f"{score[0]}-{score[1]}" if len(score) == 2 else "N/A"

    embed = {
        "title": f"{outcome_emoji(outcome)} New Match on {map_name}",
        "color": 5763719 if outcome == "win" else (15548997 if outcome == "loss" else 16776960),
        "fields": [
            {"name": "Leetify Rating", "value": f"**{format_rating(rating)}**", "inline": True},
            {"name": "Score", "value": score_str, "inline": True},
            {"name": "Result", "value": outcome.capitalize(), "inline": True},
        ],
        "thumbnail": {"url": "https://leetify.com/assets/images/logo/logo-leetify.png"},
        "footer": {"text": "Data provided by Leetify"}
    }

    result = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
    if result.status_code not in (200, 204):
        print(f"  → Webhook failed for {player_name}: HTTP {result.status_code}")

def send_scoreboard_webhook(match_id, map_name, players):
    if not SCOREBOARD_WEBHOOK:
        return
    if len(players) < 2:
        print(f"  → Skipping scoreboard (only {len(players)} tracked player in this match)")
        return

    players.sort(key=lambda x: float(x.get("rating") or -99), reverse=True)

    description_lines = []
    for i, p in enumerate(players, 1):
        description_lines.append(
            f"**{i}. {p['name']}**: {format_rating(p['rating'])} Rating"
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
        print(f"\nChecking {info['name']} ({steam_id})...")
        latest_match = fetch_latest_match(steam_id)

        if not latest_match:
            print(f"  → Skipping.")
            continue

        match_id = latest_match.get("id")
        if not match_id:
            print(f"  → No match ID found. Keys: {list(latest_match.keys())}")
            continue

        if match_id in seen_matches:
            print(f"  → Already seen ({match_id[:8]}...), nothing new.")
            continue

        print(f"  → NEW match: {match_id[:8]}... on {latest_match.get('map_name')}")
        new_match_ids.add(match_id)
        send_individual_webhook(info["webhook"], info["name"], latest_match)

        map_name = latest_match.get("map_name", "Unknown")
        if match_id not in grouped_matches:
            grouped_matches[match_id] = {"map_name": map_name, "players": []}

        grouped_matches[match_id]["players"].append({
            "name": info["name"],
            "rating": latest_match.get("leetify_rating"),
        })

    print()
    for match_id, match_data in grouped_matches.items():
        send_scoreboard_webhook(match_id, match_data["map_name"], match_data["players"])

    for match_id in new_match_ids:
        save_seen_match(match_id)
        print(f"Saved {match_id[:8]}... to seen_matches.txt")

    if not new_match_ids:
        print("No new matches found this run.")

if __name__ == "__main__":
    main()
