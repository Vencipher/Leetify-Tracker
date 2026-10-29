import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

LEETIFY_API_KEY = os.environ.get("LEETIFY_API_KEY")
SCOREBOARD_WEBHOOK = os.environ.get("SCOREBOARD_WEBHOOK")

STATE_FILE = "player_totals.json"

BASE_URL = "https://api-public.cs-prod.leetify.com"

RECENT_COUNT         = 10
MAX_SEEN_PER_PLAYER  = 200
SCOREBOARD_KEEP_DAYS = 2
SECOND_PASS_DELAY    = 10
MAX_WORKERS          = 4

MODE_LABELS = {"standard": "Total Points", "wingman": "Wingman Points"}
MODE_KEYS   = {"standard": "total",        "wingman": "wingman_total"}

PLAYER_INFO = {
    "76561198190033377": {"name": "Tudor",                          "webhook": os.environ.get("TUDOR_WEBHOOK")},
    "76561198435523362": {"name": "Siddoru",                        "webhook": os.environ.get("SIDDORU_WEBHOOK")},
    "76561199033222316": {"name": "Bendeac Adevaratu",              "webhook": os.environ.get("PUYA_WEBHOOK")},
    "76561198771342370": {"name": "Robi",                           "webhook": os.environ.get("ROBI_WEBHOOK")},
    "76561199236732682": {"name": "Andre1",                         "webhook": os.environ.get("ANDRE1_WEBHOOK")},
    "76561199226839952": {"name": "Radu",                           "webhook": os.environ.get("DIDDY_WEBHOOK")},
    "76561198983778721": {"name": "Nebunulajokuri777",              "webhook": os.environ.get("NEBUNULAJOKURI_WEBHOOK")},
    "76561198838107739": {"name": "ULTRADARKSHADOWPROMEGAKILLER777","webhook": os.environ.get("ULTRA_WEBHOOK")},
}

TIER_IMAGES = {
    "Luca Peter level":  "https://i.postimg.cc/QCx3P5bY/poop-emoji-poo-emoji.jpg",
    "Trash":             "https://i.postimg.cc/pX4wQ3gk/Toter-64Gallon-Two-Wheel-Can-Green-25564-Main.png",
    "Could be better":   "https://i.postimg.cc/gJ17yZ7w/it-could-be-better-james-pumphrey.gif",
    "On par":            "https://i.postimg.cc/DZpjvXhM/7a52a122-2ebc-4ef2-9199-2d59707e477b.png",
    "Nice":              "https://i.postimg.cc/kg7py9T5/nice-smack.gif",
    "Great":             "https://i.postimg.cc/6QyzHQnQ/good-job.gif",
    "Excellent":         "https://i.postimg.cc/rsFDJDRN/magnificent-golden-crown-with-precious-gems-191095-82978.png",
    "Gaben taking notes":"https://i.postimg.cc/CKTd2PfK/gabe-newell-portrait-v0-n-FT0PHHDTTBGzv6md-HXr-Go-Kc-Cn-Kaujg-Zzr0z2MG-k7M.png",
}

TIER_COLORS = {
    "Luca Peter level":  "1;31",
    "Trash":             "31",
    "Could be better":   "33",
    "On par":            "1;33",
    "Nice":              "1;32",
    "Great":             "32",
    "Excellent":         "4;32",
    "Gaben taking notes":"43;1;30",
}


def get_tier(rating):
    try:
        val = float(rating) * 100
    except (TypeError, ValueError):
        return "On par", TIER_IMAGES["On par"], TIER_COLORS["On par"]
    if val <= -5:
        label = "Luca Peter level"
    elif val <= -2.5:
        label = "Trash"
    elif val <= -1:
        label = "Could be better"
    elif val <= 1:
        label = "On par"
    elif val <= 2.5:
        label = "Nice"
    elif val <= 5:
        label = "Great"
    elif val <= 10:
        label = "Excellent"
    else:
        label = "Gaben taking notes"
    return label, TIER_IMAGES[label], TIER_COLORS[label]


def colored_tier(label, color_code):
    return f"```ansi\n\u001b[{color_code}m\u001b[1m{label}\u001b[0m\n```"


def now_utc():
    return datetime.now(timezone.utc)


def load_state():
    if not os.path.exists(STATE_FILE):
        print(f"No {STATE_FILE} found - starting fresh. Make sure the workflow commits this file!")
        return {"players": {}, "scoreboards": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        sys.exit(f"ERROR: could not read {STATE_FILE} ({e}). Stopping so totals aren't overwritten.")
    state.setdefault("players", {})
    state.setdefault("scoreboards", {})
    for pdata in state["players"].values():
        pdata.setdefault("total", 0.0)
        pdata.setdefault("wingman_total", 0.0)
    return state


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def prune_scoreboards(state):
    cutoff = now_utc() - timedelta(days=SCOREBOARD_KEEP_DAYS)
    for match_id in list(state["scoreboards"]):
        try:
            created = datetime.fromisoformat(state["scoreboards"][match_id]["created"])
        except (KeyError, ValueError):
            created = cutoff - timedelta(seconds=1)
        if created < cutoff:
            del state["scoreboards"][match_id]


def to_points(rating):
    return round(float(rating) * 100, 1) + 0.0


def rating_points(match):
    try:
        return to_points(match.get("leetify_rating"))
    except (TypeError, ValueError):
        return None


def fmt_points(pts):
    return f"{round(pts, 1) + 0.0:+.1f}"


def fmt_rating(rating):
    try:
        return fmt_points(to_points(rating))
    except (TypeError, ValueError):
        return "N/A"


def fmt_pct(val):
    try:
        return f"{float(val) * 100:.0f}%"
    except (TypeError, ValueError):
        return "N/A"


def outcome_emoji(outcome):
    return {"win": "✅", "loss": "❌", "tie": "➖"}.get(outcome, "❓")


def get_headers():
    return {"_leetify_key": LEETIFY_API_KEY}


def player_tag(steam_id):
    return PLAYER_INFO.get(steam_id, {}).get("name", steam_id)


def leetify_get(url, params=None, retries=2):
    response = None
    for attempt in range(retries + 1):
        response = requests.get(url, headers=get_headers(), params=params, timeout=15)
        if response.status_code != 429:
            return response
        time.sleep(2 * (attempt + 1))
    return response


def fetch_recent_matches(steam_id, count=RECENT_COUNT):
    tag = player_tag(steam_id)
    url = f"{BASE_URL}/v3/profile"
    try:
        response = leetify_get(url, params={"steam64_id": steam_id})
        print(f"  → [{tag}] HTTP {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                print(f"  → [{tag}] API error: {data['error']}")
                return None
            return data.get("recent_matches", [])[:count]
        elif response.status_code == 404:
            print(f"  → [{tag}] Player not found. They must sign up at leetify.com first.")
        elif response.status_code == 401:
            print(f"  → [{tag}] Invalid API key.")
        else:
            print(f"  → [{tag}] Unexpected: {response.text[:200]}")
    except Exception as e:
        print(f"  → [{tag}] Error ({type(e).__name__}): {e}")
    return None


def fetch_match_details(game_id):
    url = f"{BASE_URL}/v2/matches/{game_id}"
    try:
        response = leetify_get(url)
        print(f"  → Match details {game_id[:8]}... HTTP {response.status_code}")
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  → Failed to fetch match details: {response.text[:200]}")
    except Exception as e:
        print(f"  → Error fetching match details ({type(e).__name__}): {e}")
    return None


def fetch_profiles(steam_ids):
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(fetch_recent_matches, steam_ids))
    return dict(zip(steam_ids, results))


def prefetch_details(match_ids, cache):
    missing = [m for m in match_ids if m not in cache]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for match_id, details in zip(missing, pool.map(fetch_match_details, missing)):
            if details is not None:
                cache[match_id] = details


def get_player_stats_from_match(match_details, steam_id):
    if not match_details:
        return None
    for player in match_details.get("stats", []):
        if player.get("steam64_id") == steam_id:
            return player
    return None


def oldest_first(matches):
    if matches and all(m.get("finished_at") for m in matches):
        return sorted(matches, key=lambda m: m["finished_at"])
    return list(reversed(matches))


def detect_mode(match, details):
    sources = [str(match.get("data_source") or "").lower()]
    if details:
        sources.append(str(details.get("data_source") or "").lower())
    if any("wingman" in s for s in sources):
        return "wingman"
    if details:
        players = len(details.get("stats") or [])
        if 0 < players <= 4:
            return "wingman"
        if players > 4:
            return "standard"
    return None


def discord_request(method, url, payload, params=None, retries=2):
    for _ in range(retries + 1):
        try:
            response = requests.request(method, url, json=payload, params=params, timeout=10)
        except requests.RequestException as e:
            print(f"  → Discord request error ({type(e).__name__}): {e}")
            return None
        if response.status_code == 429:
            try:
                wait = float(response.json().get("retry_after", 1))
            except (ValueError, AttributeError):
                wait = 1.0
            print(f"  → Rate limited, waiting {wait:.1f}s")
            time.sleep(min(wait, 10))
            continue
        return response
    return None


def send_individual_webhook(webhook_url, player_name, steam_id, match, match_details, total, points_label):
    if not webhook_url:
        return

    map_name  = match.get("map_name", "Unknown")
    rating    = match.get("leetify_rating")
    outcome   = match.get("outcome", "unknown")
    score     = match.get("score", [])
    score_str = f"{score[0]}-{score[1]}" if len(score) == 2 else "N/A"
    color     = 5763719 if outcome == "win" else (15548997 if outcome == "loss" else 16776960)

    tier_label, tier_image, tier_color = get_tier(rating)
    tier_value = colored_tier(tier_label, tier_color)
    ps = get_player_stats_from_match(match_details, steam_id)

    separator = {"name": "\u200b", "value": "\u200b", "inline": False}
    points_field = {"name": points_label, "value": f"**{fmt_points(total)}**", "inline": False}

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
            {"name": "Kills",              "value": str(kills),                                         "inline": True},
            {"name": "Deaths",             "value": str(deaths),                                        "inline": True},
            {"name": "Assists",            "value": str(assists),                                       "inline": True},
            {"name": "K/D",               "value": f"{kd:.2f}" if kd is not None else "N/A",           "inline": True},
            {"name": "HS%",               "value": hs_pct,                                              "inline": True},
            {"name": "ADR",               "value": f"{adr:.1f}" if adr is not None else "N/A",         "inline": True},
            {"name": "Rating",            "value": f"**{fmt_rating(rating)}**",                        "inline": True},
            {"name": "CT Rating",         "value": fmt_rating(ct_rating),                              "inline": True},
            {"name": "T Rating",          "value": fmt_rating(t_rating),                               "inline": True},
            {"name": "Accuracy",          "value": fmt_pct(accuracy),                                  "inline": True},
            {"name": "Reaction Time",     "value": f"{reaction * 1000:.0f}ms" if reaction else "N/A", "inline": True},
            {"name": "MVPs",              "value": str(mvps),                                          "inline": True},
            {"name": "Util on Death",     "value": f"${util_death:.0f}" if util_death is not None else "N/A", "inline": True},
            {"name": "Flash Assists",     "value": f"{fl_assists} ({fl_thrown} thrown)",               "inline": True},
            {"name": "Smokes / Molotovs", "value": f"{smokes} / {molotovs}",                          "inline": True},
            {"name": "Trade Kill%",       "value": fmt_pct(trade_kill),                                "inline": True},
            {"name": "Traded Death%",     "value": fmt_pct(traded_dead),                               "inline": True},
            {"name": "Multi-kills",       "value": multi_str,                                          "inline": True},
            separator,
            {"name": "Match Skill Level", "value": tier_value,                                         "inline": False},
            points_field,
        ]
    else:
        fields = [
            {"name": "Leetify Rating", "value": f"**{fmt_rating(rating)}**", "inline": True},
            {"name": "Score",          "value": score_str,                    "inline": True},
            {"name": "Result",         "value": outcome.capitalize(),          "inline": True},
            separator,
            {"name": "Match Skill Level", "value": tier_value,               "inline": False},
            points_field,
        ]

    embed = {
        "title":     f"{outcome_emoji(outcome)} {outcome.capitalize()} on {map_name} — {score_str}",
        "color":     color,
        "fields":    fields,
        "thumbnail": {"url": tier_image},
        "footer":    {"text": "Data provided by Leetify"},
    }

    result = discord_request("POST", webhook_url, {"embeds": [embed]})
    if result is None or result.status_code not in (200, 204):
        code = "no response" if result is None else f"HTTP {result.status_code}"
        print(f"  → Webhook failed for {player_name}: {code} (match is still counted)")


def register_scoreboard_entry(state, match_id, map_name, mode, steam_id, name, pts, total):
    sb = state["scoreboards"].setdefault(match_id, {
        "map": map_name,
        "mode": mode,
        "message_id": None,
        "created": now_utc().isoformat(),
        "players": {},
    })
    sb["players"][steam_id] = {"name": name, "rating": pts, "total": total}


def build_scoreboard_embed(match_id, sb):
    label = MODE_LABELS.get(sb.get("mode", "standard"), MODE_LABELS["standard"])
    players = sorted(sb["players"].values(), key=lambda p: p["rating"], reverse=True)
    lines = [
        f"**{i}. {p['name']}**: {fmt_points(p['rating'])} Rating | "
        f"{label}: {fmt_points(p['total'])}"
        for i, p in enumerate(players, 1)
    ]
    return {
        "title":       f"🏆 Match Scoreboard: {sb['map']}",
        "description": "\n".join(lines),
        "color":       3447003,
        "footer":      {"text": f"Match ID: {match_id} • Data provided by Leetify"},
    }


def sync_scoreboard(state, match_id):
    sb = state["scoreboards"].get(match_id)
    if not sb or not SCOREBOARD_WEBHOOK:
        return
    if len(sb["players"]) < 2:
        print(f"  → Scoreboard for {match_id[:8]}... waiting for a 2nd tracked player")
        return

    payload = {"embeds": [build_scoreboard_embed(match_id, sb)]}

    if sb.get("message_id"):
        result = discord_request("PATCH", f"{SCOREBOARD_WEBHOOK}/messages/{sb['message_id']}", payload)
        if result is not None and result.status_code == 200:
            print(f"  → Scoreboard for {match_id[:8]}... updated")
            return
        if result is not None and result.status_code == 404:
            sb["message_id"] = None
        else:
            code = "no response" if result is None else f"HTTP {result.status_code}"
            print(f"  → Scoreboard edit failed: {code}")
            return

    result = discord_request("POST", SCOREBOARD_WEBHOOK, payload, params={"wait": "true"})
    if result is not None and result.status_code in (200, 204):
        try:
            sb["message_id"] = result.json().get("id")
        except ValueError:
            sb["message_id"] = None
        print(f"  → Scoreboard for {match_id[:8]}... posted")
    else:
        code = "no response" if result is None else f"HTTP {result.status_code}"
        print(f"  → Scoreboard webhook failed: {code}")


def candidate_ids(state, steam_id, recent):
    pdata = state["players"].get(steam_id)
    if pdata is None or not recent:
        return []
    seen = set(pdata["seen"])
    return [
        m["id"] for m in recent
        if m.get("id") and m["id"] not in seen and rating_points(m) is not None
    ]


def process_player(steam_id, info, recent, state, details_cache, touched):
    if recent is None:
        print("  → Skipping.")
        return 0

    pdata = state["players"].get(steam_id)

    if pdata is None:
        pdata = {
            "total": 0.0,
            "wingman_total": 0.0,
            "since": now_utc().strftime("%Y-%m-%d"),
            "seen":  [m["id"] for m in oldest_first(recent) if m.get("id")],
        }
        state["players"][steam_id] = pdata
        save_state(state)
        print(f"  → Started tracking {info['name']}: {len(pdata['seen'])} existing matches ignored.")
        return 0

    seen = set(pdata["seen"])
    new_count = 0

    for match in oldest_first(recent):
        match_id = match.get("id")
        if not match_id:
            print(f"  → No match ID found. Keys: {list(match.keys())}")
            continue
        if match_id in seen:
            continue

        pts = rating_points(match)
        if pts is None:
            print(f"  → Match {match_id[:8]}... has no rating yet, will retry next run.")
            continue

        details = details_cache.get(match_id)
        mode = detect_mode(match, details)
        if mode is None:
            print(f"  → Match {match_id[:8]}... mode unknown (match details unavailable), will retry next run.")
            continue

        players_in_match = len(details.get("stats") or []) if details else "?"
        print(
            f"  → NEW {mode} match: {match_id[:8]}... on {match.get('map_name')} "
            f"(data_source={match.get('data_source')}, rank_type={match.get('rank_type')}, players={players_in_match})"
        )

        key = MODE_KEYS[mode]
        new_total = round(pdata.get(key, 0.0) + pts, 1) + 0.0

        send_individual_webhook(
            info["webhook"], info["name"], steam_id,
            match, details, new_total, MODE_LABELS[mode]
        )

        pdata[key] = new_total
        pdata["seen"].append(match_id)
        pdata["seen"] = pdata["seen"][-MAX_SEEN_PER_PLAYER:]
        seen.add(match_id)
        register_scoreboard_entry(
            state, match_id, match.get("map_name", "Unknown"), mode,
            steam_id, info["name"], pts, new_total
        )
        touched.add(match_id)
        save_state(state)
        new_count += 1

    return new_count


def run_pass(targets, state, details_cache, touched):
    profiles = fetch_profiles([steam_id for steam_id, _ in targets])

    wanted = set()
    for steam_id, _ in targets:
        wanted.update(candidate_ids(state, steam_id, profiles.get(steam_id)))
    prefetch_details(wanted, details_cache)

    counts = {}
    for steam_id, info in targets:
        print(f"\nChecking {info['name']} ({steam_id})...")
        counts[steam_id] = process_player(
            steam_id, info, profiles.get(steam_id), state, details_cache, touched
        )
    return counts


def flush_scoreboards(state, touched):
    print()
    for match_id in touched:
        sync_scoreboard(state, match_id)
    save_state(state)
    touched.clear()


def main():
    state = load_state()
    prune_scoreboards(state)

    details_cache = {}
    touched       = set()
    targets       = list(PLAYER_INFO.items())

    counts    = run_pass(targets, state, details_cache, touched)
    total_new = sum(counts.values())
    flush_scoreboards(state, touched)

    missed = [(steam_id, info) for steam_id, info in targets if counts.get(steam_id, 0) == 0]
    if total_new and missed:
        print(f"Second pass for players with no new matches (waiting {SECOND_PASS_DELAY}s)...")
        time.sleep(SECOND_PASS_DELAY)
        second_counts = run_pass(missed, state, details_cache, touched)
        total_new += sum(second_counts.values())
        flush_scoreboards(state, touched)

    if not total_new:
        print("No new matches found this run.")


if __name__ == "__main__":
    main()
