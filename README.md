# Wild Game Monitor 🏒

Live Minnesota Wild game monitor that sends Telegram alerts and plays **Free Bird** on Sonos for every Wild goal.

## Features

- 🚨 **Goals** — scorer, assists, time, period, live score
- ⚠️ **Penalties** — player, type, duration
- 🔔 **Period changes** — end of period score updates
- ⏱️ **OT/Shootout** alerts
- 🏁 **Final score** with win/loss
- 🎸 **Free Bird** plays on Sonos at the 4:45 guitar solo for every Wild goal (20 seconds)

## Setup

1. Install [sonoscli](https://sonoscli.sh)
2. Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

3. Run:

```bash
source .env  # or set env vars however you prefer
python3 monitor.py
```

## Environment Variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/user ID |
| `WILD_GAME_ID` | NHL game ID (from the NHL API) |
| `SONOS_IP` | IP address of your Sonos speaker |
| `POLL_SECS` | Poll interval in seconds (default: 30) |

## Finding Game IDs

Game IDs can be found from the NHL API:
```
https://api-web.nhle.com/v1/club-schedule-season/MIN/now
```
