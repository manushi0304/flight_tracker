# Flight Price Tracker

Unattended BOM/DEL/BLR → SYD one-way economy price tracker. Checks every date
from `TRACK_START_DATE` to `TRACK_END_DATE` once a day, sends an instant
Telegram alert on a ≥₹1,000 price drop, and a Monday Telegram digest of the
cheapest fare per route each week.

This project supports **two deployment modes**:

| Mode | Cost | Where jobs run |
|---|---|---|
| **A. GitHub Actions (recommended — $0)** | Free | GitHub's servers, on a cron schedule, no server of yours needed |
| B. VPS + APScheduler | ~$5/mo (VPS) | Your own always-on box, via `scheduler.py` |

**Mode A is what makes this free**, and is documented first below. Mode B
(the original always-on FastAPI+APScheduler service) is still included
further down if you ever want to self-host instead.

To hit **$0 total**, also leave `ANTHROPIC_API_KEY` blank — `claude_formatter.py`
detects a missing key and skips the API call entirely, falling back to the
built-in plain-text templates. Every other piece (Telegram, GitHub
Actions, SQLite, `fast-flights`) is free regardless.

## How it works

- **Daily job** (every day, 06:00 IST): scrapes Google Flights via
  `fast-flights` for every route × date, compares each price to the last
  stored price for that exact route+date, sends an instant Telegram alert on
  a qualifying drop, and saves every successful reading to SQLite.
- **Weekly job** (Mondays only, 08:00 IST): reads the last 7 days of
  saved prices, finds the cheapest fare per route, and sends one Telegram
  digest message — regardless of whether any alerts fired that week.
- In **Mode A**, these are two GitHub Actions workflows
  (`.github/workflows/daily.yml` and `weekly.yml`) triggered by `cron:`
  schedules. The daily workflow commits the updated `flights.db` back to
  your repo at the end of each run, so history persists between runs even
  though each run starts on a fresh throwaway machine.
- In **Mode B**, both jobs are wired into APScheduler inside a FastAPI app
  (`scheduler.py`), which is a long-running process you deploy yourself.

## 1. Things YOU need to do (cannot be automated)

1. **Create a Telegram bot**:
   - Open Telegram, search for **@BotFather**, start a chat, send `/newbot`.
   - Follow the prompts (choose a name and a username ending in `bot`).
   - BotFather replies with a token like `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxx`
     — copy this into `.env` as `TELEGRAM_BOT_TOKEN`. This never expires and
     costs nothing.
2. **Get your chat ID**:
   - Send any message (e.g. "hi") to your new bot from your own Telegram account.
   - In a browser, visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
     (replace `<YOUR_TOKEN>` with your real token).
   - Find `"chat":{"id": ...}` in the JSON response — that number is your
     chat ID. Copy it into `.env` as `TELEGRAM_CHAT_ID`.
3. **(Optional, costs money) Anthropic API key** — only needed if you want
   Claude to write nicer-sounding alert text. For the free path, skip this:
   leave `ANTHROPIC_API_KEY` blank and the app uses built-in templates instead.
4. **Create a GitHub repo** (public or private — both are free; private just
   keeps your repo listing off your public profile) and push this project to it.
5. **Add repo secrets** — Settings → Secrets and variables → Actions → New
   repository secret. Add: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
   Skip `ANTHROPIC_API_KEY` to stay free.
6. **Confirm you're comfortable with the scraping caveat**: `fast-flights`
   scrapes Google Flights' HTML. Google can change that markup at any time,
   which will break fetches until the library is updated upstream. The code
   here fails soft (logs + skips that route/date) instead of crashing, but
   nobody can guarantee 100% uptime against an unofficial scraper.

## 2A. Mode A setup — GitHub Actions (free, recommended)

This is the whole setup, no server required:

1. Push this project (including the `.github/workflows/` folder) to a GitHub repo.
2. Add the two Telegram secrets as described above (`TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`). Leave `ANTHROPIC_API_KEY` unset for $0 cost.
3. Commit an initial empty `flights.db` so the first daily run has something
   to `git add`/commit back to (optional — the workflow's `git add` step
   handles it fine either way, but committing a placeholder avoids the very
   first diff looking odd):
   ```bash
   python -c "from database import init_db; init_db()"
   git add flights.db && git commit -m "Initialize empty fare database" && git push
   ```
4. Go to the repo's **Actions** tab. You should see "Daily Fare Check" and
   "Weekly Digest" workflows listed. Click into either and use **Run workflow**
   to trigger it manually right now — this is the easiest way to confirm
   Telegram delivery works before waiting for the real schedule.
5. That's it. From here on:
   - "Daily Fare Check" runs automatically every day at 06:00 IST (`cron: "30 0 * * *"` in UTC).
   - "Weekly Digest" runs automatically every Monday at 08:00 IST (`cron: "30 2 * * 1"` in UTC).
   - Each daily run commits the updated `flights.db` back to your repo, so
     price history accumulates across runs even though every run starts on
     a fresh GitHub-hosted machine.

**Free tier limits to know:** GitHub Actions gives public repos unlimited
free minutes, and private repos 2,000 free minutes/month. This job's daily
run takes roughly 10–15 minutes (126 scrapes × ~3–5s delay each), so monthly
usage is around 300–450 minutes — comfortably inside the free private-repo
quota, and irrelevant if your repo is public.

**Note on cron timing:** GitHub Actions schedules run on a best-effort basis
and can be delayed by several minutes (rarely longer) during periods of high
platform load. This doesn't matter for a once-a-day fare check.

## 2B. Mode B setup — self-hosted VPS (optional, ~$5/mo)

```bash
git clone <your-repo> flight-tracker && cd flight-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your real values from section 1
```

Test the two jobs manually before trusting the schedule:

```bash
python daily_job.py      # should fetch fares, save to flights.db, alert if applicable
python weekly_job.py     # should send a digest (even with sparse data)
```

Run the full service (scheduler + health API):

```bash
uvicorn scheduler:app --host 0.0.0.0 --port 8000
```

Check it's alive and see next scheduled run times:

```bash
curl http://localhost:8000/health
```

Trigger a job on demand without waiting for the cron time (useful for testing):

```bash
curl -X POST http://localhost:8000/trigger/daily
curl -X POST http://localhost:8000/trigger/weekly
```

## 3. Environment variables

See `.env.example` for the full list with comments. Key ones:

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token for your bot, from @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal Telegram chat ID (where alerts are sent) |
| `ANTHROPIC_API_KEY` | Claude API key, used only for message formatting |
| `PRICE_DROP_THRESHOLD_INR` | Minimum ₹ drop to trigger an instant alert (default 1000) |
| `TRACK_START_DATE` / `TRACK_END_DATE` | Date range tracked, inclusive |
| `ROUTES` | `ORIGIN:DEST` pairs, comma-separated |
| `REQUEST_DELAY_SECONDS` | Delay between each Google Flights scrape (avoid blocks) |
| `DAILY_JOB_HOUR/MINUTE`, `WEEKLY_JOB_HOUR/MINUTE` | Schedule times, Asia/Kolkata |

## 4. Deploying to a VPS (recommended path)

```bash
# on the VPS, as root
adduser --system --group flighttracker
mkdir -p /opt/flight-tracker
# copy your project files into /opt/flight-tracker (scp / git clone / rsync)
cd /opt/flight-tracker
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in real values
chown -R flighttracker:flighttracker /opt/flight-tracker

cp flight-tracker.service /etc/systemd/system/flight-tracker.service
systemctl daemon-reload
systemctl enable --now flight-tracker
systemctl status flight-tracker
journalctl -u flight-tracker -f   # tail logs
```

The provided `flight-tracker.service` runs `uvicorn scheduler:app`, restarts
automatically on crash, and starts on boot. No cron needed — APScheduler
handles the daily/weekly timing internally as long as the process stays up.

## 5. Notes & known limitations

- **Currency**: the fetcher requests INR from Google Flights via
  `get_flights_from_filter(..., currency="INR")`. If your installed
  `fast-flights` version is older and doesn't support that kwarg, it
  auto-retries without it — in that case prices may come back in USD.
  Verify your first run's numbers look sane in INR; adjust `CURRENCY` env
  var or upgrade the library if needed.
- **Scraping load**: ~42 dates × 3 routes = 126 requests/day, each with a
  jittered delay (`REQUEST_DELAY_SECONDS`, default 3s) to reduce block risk.
  Expect the daily job to take roughly 8–15 minutes end to end.
- **Data model**: every fetch appends a new row (`fares` table is
  append-only history), so you always have a full price timeline per
  route+date, not just the latest value.
- **First run**: the very first check for each route+date has nothing to
  compare against, so it can never trigger a "drop" alert — it just
  establishes the baseline. That's expected.
- **Claude's role is intentionally narrow and fully optional**: it only turns
  already-computed numbers into Telegram-friendly sentences. If
  `ANTHROPIC_API_KEY` is unset, `claude_formatter.py` never calls the API at
  all and uses the plain-text template — this is what keeps the whole
  project at $0. If a key IS set and the API call fails or errors for any
  reason, it also falls back to the template, so you never miss an alert
  because of an LLM outage either way.
- **Telegram is free indefinitely** for personal use — no trial expiry,
  no message limits, no card required, ever.
