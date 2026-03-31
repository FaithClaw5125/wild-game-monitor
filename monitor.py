#!/usr/bin/env python3
"""
Minnesota Wild game monitor.
Polls the NHL API for live game data and sends Telegram updates
for score changes, penalties, period changes, and final score.
"""

import urllib.request
import json
import time
import os
import sys
import subprocess
import threading
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN        = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID          = os.environ.get("TELEGRAM_CHAT_ID", "")
GAME_ID          = os.environ.get("WILD_GAME_ID", "")
POLL_SECS        = int(os.environ.get("POLL_SECS", "30"))
STATE_FILE       = os.path.join(os.path.dirname(__file__), f"state-{GAME_ID}.json")
SONOS_IP         = os.environ.get("SONOS_IP", "")
FREEBIRD_URI     = "spotify:track:5EWPGh7jbTNO2wakv8LjUI"        # Free Bird - Lynyrd Skynyrd
FREEBIRD_SEEK_TIME = "0:04:45"  # guitar solo starts here
FREEBIRD_PLAY_SECS = 20         # play for 20 seconds then stop
# ─────────────────────────────────────────────────────────────────────────────


def send_telegram(text: str):
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as e:
        print(f"Telegram error: {e}")


def play_freebird():
    """Kick off Free Bird in a background thread so the monitor keeps polling."""
    t = threading.Thread(target=_freebird_worker, daemon=True)
    t.start()


def _freebird_worker():
    """Play Free Bird starting at 4:45 (the guitar solo) for 20 seconds, then stop."""
    try:
        # Capture current state
        status = subprocess.run(
            ["sonos", "status", "--ip", SONOS_IP],
            capture_output=True, text=True, timeout=10
        )
        was_playing = "PLAYING" in status.stdout
        vol_line = [l for l in status.stdout.splitlines() if l.startswith("Volume:")]
        prev_vol = int(vol_line[0].split()[1]) if vol_line else None

        # Bump volume a bit for the celebration (cap at 40)
        cel_vol = min((prev_vol or 20) + 10, 40)
        subprocess.run(["sonos", "volume", "set", str(cel_vol), "--ip", SONOS_IP],
                       capture_output=True, timeout=10)

        # Play Free Bird from the beginning, fast-forward by waiting, then cut at the solo
        subprocess.run(
            ["sonos", "play", "spotify", "Free Bird Lynyrd Skynyrd",
             "--ip", SONOS_IP],
            capture_output=True, timeout=15
        )
        # Wait a moment for the track to load, then seek via UPnP SOAP
        time.sleep(3)
        seek_body = f'''<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:Seek xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Unit>REL_TIME</Unit><Target>{FREEBIRD_SEEK_TIME}</Target></u:Seek></s:Body></s:Envelope>'''
        subprocess.run([
            "curl", "-s", "-X", "POST",
            f"http://{SONOS_IP}:1400/MediaRenderer/AVTransport/Control",
            "-H", 'Content-Type: text/xml; charset="utf-8"',
            "-H", 'SOAPAction: "urn:schemas-upnp-org:service:AVTransport:1#Seek"',
            "-d", seek_body
        ], capture_output=True, timeout=10)
        print(f"🎸 Seeked to {FREEBIRD_SEEK_TIME} — SOLO! Playing for {FREEBIRD_PLAY_SECS}s")
        time.sleep(FREEBIRD_PLAY_SECS)

        # Stop and restore volume
        subprocess.run(["sonos", "stop", "--ip", SONOS_IP], capture_output=True, timeout=10)
        if prev_vol is not None:
            subprocess.run(["sonos", "volume", "set", str(prev_vol), "--ip", SONOS_IP],
                           capture_output=True, timeout=10)
        print("🎸 Free Bird done, volume restored.")
    except Exception as e:
        print(f"Sonos error: {e}")


def fetch_game(game_id: str) -> dict:
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "last_event_id": 0,
        "away_score": 0,
        "home_score": 0,
        "period": 0,
        "game_state": "",
        "started": False,
        "finished": False,
    }


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def period_label(n: int, period_type: str = "REG") -> str:
    if period_type == "OT":
        return "OT"
    if period_type == "SO":
        return "Shootout"
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"P{n}")


def team_label(data: dict, team_id: int) -> str:
    if data.get("homeTeam", {}).get("id") == team_id:
        return data["homeTeam"].get("abbrev", "HOME")
    return data.get("awayTeam", {}).get("abbrev", "AWAY")


def main():
    state = load_state()

    if state.get("finished"):
        print("Game already finished. Exiting.")
        sys.exit(0)

    print(f"Monitoring game {GAME_ID}... (poll every {POLL_SECS}s)")

    while True:
        try:
            data = fetch_game(GAME_ID)
        except Exception as e:
            print(f"Fetch error: {e}")
            time.sleep(POLL_SECS)
            continue

        game_state = data.get("gameState", "")
        away        = data.get("awayTeam", {})
        home        = data.get("homeTeam", {})
        away_score  = away.get("score", 0)
        home_score  = home.get("score", 0)
        away_abbrev = away.get("abbrev", "AWAY")
        home_abbrev = home.get("abbrev", "HOME")
        period_desc = data.get("periodDescriptor", {})
        period_num  = period_desc.get("number", 0)
        period_type = period_desc.get("periodType", "REG")
        plays       = data.get("plays", [])

        # ── Game start ────────────────────────────────────────────────────────
        if game_state in ("LIVE", "CRIT") and not state["started"]:
            state["started"] = True
            send_telegram(
                f"🏒 <b>Wild game is underway!</b>\n"
                f"{away_abbrev} @ {home_abbrev}\n"
                f"Starting 1st period"
            )
            print("Game started.")

        # ── Period change ─────────────────────────────────────────────────────
        if state["started"] and period_num != state["period"] and period_num > 0:
            state["period"] = period_num
            lbl = period_label(period_num, period_type)
            if period_type in ("OT", "SO"):
                send_telegram(
                    f"⏱ <b>{lbl} starting!</b>\n"
                    f"{away_abbrev} {away_score} – {home_score} {home_abbrev}"
                )
            elif period_num > 1:
                prev_lbl = period_label(period_num - 1)
                send_telegram(
                    f"🔔 <b>End of {prev_lbl} period</b>\n"
                    f"{away_abbrev} {away_score} – {home_score} {home_abbrev}\n"
                    f"Starting {lbl} period"
                )
            print(f"Period {period_num} ({period_type})")

        # ── Process new play-by-play events ───────────────────────────────────
        for play in plays:
            event_id   = play.get("eventId", 0)
            event_type = play.get("typeDescKey", "")

            if event_id <= state["last_event_id"]:
                continue

            state["last_event_id"] = event_id

            # Score change
            if event_type == "goal":
                details     = play.get("details", {})
                scoring_tid = details.get("eventOwnerTeamId")
                scorer_name = details.get("scoringPlayerName", "Unknown")
                assist1     = details.get("assist1PlayerName", "")
                assist2     = details.get("assist2PlayerName", "")
                team_abbrev = team_label(data, scoring_tid)
                assists_str = ""
                if assist1 and assist2:
                    assists_str = f"\nAssists: {assist1}, {assist2}"
                elif assist1:
                    assists_str = f"\nAssist: {assist1}"
                period_str  = period_label(
                    play.get("periodDescriptor", {}).get("number", period_num),
                    play.get("periodDescriptor", {}).get("periodType", period_type)
                )
                time_str    = play.get("timeInPeriod", "")
                send_telegram(
                    f"🚨 <b>GOAL – {team_abbrev}!</b>\n"
                    f"{scorer_name}{assists_str}\n"
                    f"{period_str} · {time_str}\n"
                    f"<b>{away_abbrev} {away_score} – {home_score} {home_abbrev}</b>"
                )
                print(f"Goal: {team_abbrev} — {away_abbrev} {away_score} {home_abbrev} {home_score}")
                # 🎸 Wild goal celebration!
                if team_abbrev == "MIN":
                    play_freebird()

            # Penalty
            elif event_type == "penalty":
                details      = play.get("details", {})
                penalized    = details.get("committedByPlayerName", "Unknown")
                pen_type     = details.get("descKey", "penalty")
                duration_min = details.get("duration", 2)
                team_id      = details.get("eventOwnerTeamId")
                team_abbrev  = team_label(data, team_id)
                period_str   = period_label(
                    play.get("periodDescriptor", {}).get("number", period_num),
                    play.get("periodDescriptor", {}).get("periodType", period_type)
                )
                time_str = play.get("timeInPeriod", "")
                send_telegram(
                    f"⚠️ <b>PENALTY – {team_abbrev}</b>\n"
                    f"{penalized} · {pen_type.replace('-', ' ').title()} · {duration_min} min\n"
                    f"{period_str} · {time_str}"
                )
                print(f"Penalty: {team_abbrev} — {penalized}")

        # ── Score change catch-all (in case goal event was missed) ────────────
        if state["started"]:
            if away_score != state["away_score"] or home_score != state["home_score"]:
                state["away_score"] = away_score
                state["home_score"] = home_score

        # ── Game over ─────────────────────────────────────────────────────────
        if game_state in ("OFF", "FINAL") and state["started"] and not state["finished"]:
            state["finished"] = True
            winner = home_abbrev if home_score > away_score else away_abbrev
            period_str = period_label(period_num, period_type)
            ot_str = f" ({period_str})" if period_type in ("OT", "SO") or period_num > 3 else ""
            wild_result = "WIN 🎉" if (
                (home_abbrev == "MIN" and home_score > away_score) or
                (away_abbrev == "MIN" and away_score > home_score)
            ) else "LOSS 😔"
            send_telegram(
                f"🏁 <b>FINAL{ot_str} – Wild {wild_result}</b>\n"
                f"{away_abbrev} {away_score} – {home_score} {home_abbrev}"
            )
            save_state(state)
            print("Game over. Exiting.")
            sys.exit(0)

        save_state(state)

        if game_state not in ("LIVE", "CRIT", "PRE"):
            print(f"Game state: {game_state} — waiting...")

        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
