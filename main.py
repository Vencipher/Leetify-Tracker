import os
import requests

LEETIFY_API_KEY = os.environ.get("LEETIFY_API_KEY")
SCOREBOARD_WEBHOOK = os.environ.get("SCOREBOARD_WEBHOOK")
SEEN_MATCHES_FILE = "seen_matches.txt"

BASE_URL = "https://api-public.cs-prod.leetify.com"

PLAYER_INFO = {
    "76561198190033377": {"name": "Tudor",                          "webhook": os.environ.get("TUDOR_WEBHOOK")},
    "76561198435523362": {"name": "Siddoru",                        "webhook": os.environ.get("SIDDORU_WEBHOOK")},
    "76561199033222316": {"name": "Puya",                           "webhook": os.environ.get("PUYA_WEBHOOK")},
    "76561198771342370": {"name": "Robi",                           "webhook": os.environ.get("ROBI_WEBHOOK")},
    "76561199236732682": {"name": "Andre1",                         "webhook": os.environ.get("ANDRE1_WEBHOOK")},
    "76561199226839952": {"name": "Diddyplayscs2_6741",             "webhook": os.environ.get("DIDDY_WEBHOOK")},
    "76561198983778721": {"name": "Nebunulajokuri777",              "webhook": os.environ.get("NEBUNULAJOKURI_WEBHOOK")},
    "76561198838107739": {"name": "ULTRADARKSHADOWPROMEGAKILLER777","webhook": os.environ.get("ULTRA_WEBHOOK")},
}


def load_seen_matches():
    if not os.path.exists(SEEN_MATCHES_FILE):
        return set()
    with open(SEEN_MATCHES_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())


def save_seen_match(match_id):
    with open(SEEN_MATCHES_FILE, "a") as f:
        f.write(f"{match_id}\n")


def get_headers():
    return {"_leetify_key": LEETIFY_API_KEY}


def fetch_recent_matches(steam_id, count=5):
    url = f"{BASE_URL}/v3/profile"
    params = {"steam64_id": steam_id}
    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=15)
        print(f"  → HTTP {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                print(f"  → API error: {data['error']}")
                return []
            return data.get("recent_matches", [])[:count]
        elif response.status_code == 404:
            print("  → Player not found. They must sign up at leetify.com first.")
        elif response.status_code == 401:
            print("  → Invalid API key.")
        else:
            print(f"  → Unexpected: {response.text[:200]}")
    except Exception as e:
        print(f"  → Error ({type(e).__name__}): {e}")
    return []


def fetch_match_details(game_id):
    url = f"{BASE_URL}/v2/matches/{game_id}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        print(f"  → Match details HTTP {response.status_code}")
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  → Failed to fetch match details: {response.text[:200]}")
    except Exception as e:
        print(f"  → Error fetching match details ({type(e).__name__}): {e}")
    return None


def get_player_stats_from_match(match_details, steam_id):
    if not match_details:
        return None
    for player in match_details.get("stats", []):
        if player.get("steam64_id") == steam_id:
            return player
    return None


def fmt_rating(rating):
    try:
        val = float(rating)
        display = round(val * 100, 1)
        return f"+{display}" if val >= 0 else str(display)
    except (TypeError, ValueError):
        return "N/A"


def fmt_pct(val):
    try:
        return f"{float(val) * 100:.0f}%"
    except (TypeError, ValueError):
        return "N/A"


def outcome_emoji(outcome):
    return {"win": "✅", "loss": "❌", "tie": "➖"}.get(outcome, "❓")


def send_individual_webhook(webhook_url, player_name, steam_id, match, match_details=None):
    if not webhook_url:
        return

    map_name  = match.get("map_name", "Unknown")
    rating    = match.get("leetify_rating")
    outcome   = match.get("outcome", "unknown")
    score     = match.get("score", [])
    score_str = f"{score[0]}-{score[1]}" if len(score) == 2 else "N/A"
    color     = 5763719 if outcome == "win" else (15548997 if outcome == "loss" else 16776960)

    ps = get_player_stats_from_match(match_details, steam_id)

    if ps:
        kills       = ps.get("total_kills", 0)
        deaths      = ps.get("total_deaths", 0)
        assists     = ps.get("total_assists", 0)
        kd          = ps.get("kd_ratio")
        hs_kills    = ps.get("total_hs_kills", 0)
        hs_pct      = f"{hs_kills / kills * 100:.0f}%" if kills > 0 else "N/A"
        adr         = ps.get("dpr")
        ct_rating   = ps.get("ct_leetify_rating")
        t_rating    = ps.get("t_leetify_rating")
        accuracy    = ps.get("accuracy_enemy_spotted")
        reaction    = ps.get("reaction_time")
        util_death  = ps.get("utility_on_death_avg")
        fl_assists  = ps.get("flash_assist", 0)
        fl_thrown   = ps.get("flashbang_thrown", 0)
        smokes      = ps.get("smoke_thrown", 0)
        molotovs    = ps.get("molotov_thrown", 0)
        trade_kill  = ps.get("trade_kills_success_percentage")
        traded_dead = ps.get("traded_deaths_success_percentage")
        multi2k     = ps.get("multi2k", 0)
        multi3k     = ps.get("multi3k", 0)
        multi4k     = ps.get("multi4k", 0)
        multi5k     = ps.get("multi5k", 0)
        mvps        = ps.get("mvps", 0)

        multi_str = " | ".join(
            f"{lbl}×{n}"
            for lbl, n in [("2K", multi2k), ("3K", multi3k), ("4K", multi4k), ("5K", multi5k)]
            if n
        ) or "—"

        fields = [
            {"name": "Kills",             "value": str(kills),                                          "inline": True},
            {"name": "Deaths",            "value": str(deaths),                                         "inline": True},
            {"name": "Assists",           "value": str(assists),                                         "inline": True},
            {"name": "K/D",              "value": f"{kd:.2f}" if kd is not None else "N/A",             "inline": True},
            {"name": "HS%",              "value": hs_pct,                                               "inline": True},
            {"name": "ADR",              "value": f"{adr:.1f}" if adr is not None else "N/A",           "inline": True},
            {"name": "Rating",           "value": f"**{fmt_rating(rating)}**",                          "inline": True},
            {"name": "CT Rating",        "value": fmt_rating(ct_rating),                                "inline": True},
            {"name": "T Rating",         "value": fmt_rating(t_rating),                                 "inline": True},
            {"name": "Accuracy",         "value": fmt_pct(accuracy),                                    "inline": True},
            {"name": "Reaction Time",    "value": f"{reaction * 1000:.0f}ms" if reaction else "N/A",   "inline": True},
            {"name": "MVPs",             "value": str(mvps),                                            "inline": True},
            {"name": "Util on Death",    "value": f"${util_death:.0f}" if util_death is not None else "N/A", "inline": True},
            {"name": "Flash Assists",    "value": f"{fl_assists} ({fl_thrown} thrown)",                 "inline": True},
            {"name": "Smokes / Molotovs","value": f"{smokes} / {molotovs}",                            "inline": True},
            {"name": "Trade Kill%",      "value": fmt_pct(trade_kill),                                  "inline": True},
            {"name": "Traded Death%",    "value": fmt_pct(traded_dead),                                 "inline": True},
            {"name": "Multi-kills",      "value": multi_str,                                            "inline": True},
        ]
    else:
        fields = [
            {"name": "Leetify Rating", "value": f"**{fmt_rating(rating)}**", "inline": True},
            {"name": "Score",          "value": score_str,                    "inline": True},
            {"name": "Result",         "value": outcome.capitalize(),          "inline": True},
        ]

    embed = {
        "title": f"{outcome_emoji(outcome)} {outcome.capitalize()} on {map_name} — {score_str}",
        "color": color,
        "fields": fields,
        "thumbnail": {"url": "https://leetify.com/assets/images/logo/logo-leetify.png"},
        "footer": {"text": "Data provided by Leetify"},
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

    lines = [
        f"**{i}. {p['name']}**: {fmt_rating(p['rating'])} Rating"
        for i, p in enumerate(players, 1)
    ]

    embed = {
        "title": f"🏆 Match Scoreboard: {map_name}",
        "description": "\n".join(lines),
        "color": 3447003,
        "footer": {"text": f"Match ID: {match_id} • Data provided by Leetify"},
    }

    result = requests.post(SCOREBOARD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    if result.status_code not in (200, 204):
        print(f"  → Scoreboard webhook failed: HTTP {result.status_code}")


def main():
    seen_matches        = load_seen_matches()
    grouped_matches     = {}
    new_match_ids       = set()
    sent_webhooks       = set()
    match_details_cache = {}

    for steam_id, info in PLAYER_INFO.items():
        print(f"\nChecking {info['name']} ({steam_id})...")
        recent = fetch_recent_matches(steam_id, count=5)

        if not recent:
            print("  → Skipping.")
            continue

        for match in recent:
            match_id = match.get("id")
            if not match_id:
                print(f"  → No match ID found. Keys: {list(match.keys())}")
                continue

            if match_id in seen_matches:
                print(f"  → Already seen ({match_id[:8]}...), skipping.")
                continue

            webhook_key = (steam_id, match_id)
            if webhook_key in sent_webhooks:
                continue

            print(f"  → NEW match: {match_id[:8]}... on {match.get('map_name')}")
            sent_webhooks.add(webhook_key)
            new_match_ids.add(match_id)

            if match_id not in match_details_cache:
                print(f"  → Fetching match details for {match_id[:8]}...")
                match_details_cache[match_id] = fetch_match_details(match_id)

            send_individual_webhook(
                info["webhook"], info["name"], steam_id,
                match, match_details_cache.get(match_id)
            )

            map_name = match.get("map_name", "Unknown")
            if match_id not in grouped_matches:
                grouped_matches[match_id] = {"map_name": map_name, "players": []}
            grouped_matches[match_id]["players"].append({
                "name":   info["name"],
                "rating": match.get("leetify_rating"),
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
