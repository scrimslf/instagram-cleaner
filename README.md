# Instagram Non-Follower Cleaner

A small, careful command-line tool that **removes the Instagram accounts that
follow you but that you don't follow back** ("remove follower"), with a limit
you choose and human-like delays to reduce the risk of being blocked.

> ⚠️ **Read this first.** Automating actions violates Instagram's Terms of
> Service. Even with every precaution here, a **temporary block or a permanent
> suspension is possible**. Use it on your own account, at your own risk, and
> go slow. If Instagram shows a security "challenge" or a "please wait a few
> minutes" message, **stop for a few days**.

## Features

- 🧪 **Dry-run by default** — see exactly who *would* be removed before anything happens.
- 🔢 **Pick how many** — `--limit` accepts **0 to 1000**. **100 is the recommended
  safe ceiling**; going higher prints a warning and asks for confirmation.
- 🔐 **2FA handled for you** — if two-factor auth is on, the tool asks for your
  6-digit code in the terminal. Security challenges (SMS/email codes) are handled too.
- ♻️ **Session reuse** — you only log in (and do 2FA) once; later runs are instant.
- ⏸️ **Human-like pacing** — randomized delays and periodic long pauses.
- 📌 **Resumable** — it remembers who was already removed and respects a daily count.
- ✅ **Whitelist** — accounts you never want removed.
- 🔒 **No secrets on disk** — your password is entered hidden (`getpass`) and never
  written to a file (unless *you* choose to put it in `config.json`, which is git-ignored).

## Graphical interface (easiest)

Prefer clicking to typing commands? After installing (below), run:

```bash
python gui.py
```

A small native window opens: fill in your username/password, pick how many to
remove (0–1000), leave **Execute** unticked for a safe simulation, and press
**Start**. If Instagram asks for a 2FA code, a popup appears. A **Stop** button
lets you halt at any time. The GUI uses **Tkinter**, which ships with Python —
no extra install, no browser, barely any RAM.

## Requirements

- Python **3.10+** (tested on 3.14)
- An Instagram account
- For the GUI on Linux only: Tkinter may need `sudo apt install python3-tk`
  (it's already included in the official Windows/macOS Python installers)

## Install

**Windows (PowerShell):**
```powershell
cd instagram-cleaner
.\setup.ps1
```

**macOS / Linux:**
```bash
cd instagram-cleaner
bash setup.sh
```

Or manually:
```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Everything is a dry-run until you add `--execute`.

**1. See who would be removed (safe, changes nothing):**
```bash
python clean_followers.py
```
You'll be asked for your username and password (password is hidden). If 2FA is
on, enter the 6-digit code when prompted. A session is then saved so you won't
be asked again.

**2. Actually remove, choosing how many:**
```bash
python clean_followers.py --limit 40 --execute
```

**3. Recompute the follower/following lists (e.g. after a few days):**
```bash
python clean_followers.py --refresh
```

### Options

| Flag | Meaning |
|------|---------|
| `--limit N` | How many to remove this run. **0–1000**, default 40. Over **100** triggers a warning. |
| `--execute` | Actually remove. Without it, it's a dry-run. |
| `--dry-run` | Force dry-run even if `config.json` enables execution. |
| `--refresh` | Recompute followers/following from Instagram (ignores the cache). |
| `--yes` | Skip confirmation prompts (use with care). |

### Choosing a safe number

- **0–50** — safest, good for the first days.
- **~100** — the practical ceiling. This is the risk boundary; staying at or
  below it is strongly recommended.
- **101–1000** — allowed, but each step up raises the odds of a temporary block
  or suspension. The tool warns and asks you to confirm.

**Run at most once a day**, ideally from your usual device and home network. A
brand-new IP or an unusual location makes Instagram far more likely to block the
login.

## Configuration (optional)

You don't need a config file — the tool asks for what it needs. But you can copy
`config.example.json` to `config.json` (git-ignored) to set defaults:

| Key | Role |
|-----|------|
| `username` / `password` | Skip the prompts. Leave `password` out to keep being asked (recommended). |
| `daily_limit` | Default for `--limit`. |
| `min_delay_seconds` / `max_delay_seconds` | Random delay between actions. |
| `long_pause_every` | Take a long pause every N actions. |
| `long_pause_min_seconds` / `long_pause_max_seconds` | Length of the long pause. |
| `whitelist` | Usernames or IDs to **never** remove. |
| `dry_run` | `true` = simulate (still overridable by `--execute`/`--dry-run`). |

## Generated files (never commit these)

- `session.json` — your saved login session.
- `state.json` — progress: who was removed, today's counter.
- `targets_cache.json` — the computed target list.
- `config.json` — your settings (may contain your password).

All of the above are in `.gitignore`.

## Troubleshooting

- **"Two-factor authentication required"** — enter the 6-digit code from your
  authenticator app (or SMS) when prompted. If you use SMS and never receive it,
  your 2FA phone number may be outdated: fix it in the Instagram app
  (Settings → Accounts Center → Password and security → Two-factor
  authentication), ideally switching to an **authenticator app**.
- **"Security challenge"** — open the Instagram app, approve the login, wait, retry.
- **"Please wait a few minutes"** — you're being rate-limited. Stop for the day.
- **Install fails building `pydantic-core`** — you're on a Python version too new
  for the pinned deps. This project uses `instagrapi>=2.18` + `pydantic>=2.9`
  specifically to avoid that.

## Mobile app (Android)

An experimental Kivy-based Android app lives in [`mobile/`](mobile/). The source
is ready to build into an APK (via Docker); see `mobile/README.md`. It runs the
same logic on your phone, so it uses your phone's residential IP.

Honest notes on feasibility:

- **Android (.apk): feasible.** The logic can be wrapped with
  [Kivy](https://kivy.org) + `buildozer` (or BeeWare) so `instagrapi` runs
  **on the phone itself**. That's actually ideal here: the phone's residential
  IP is far less likely to be blocked than a cloud server IP.
- **iOS: hard.** The App Store will almost certainly reject an app that
  automates Instagram (it breaks Instagram's ToS). Realistic options are a
  personal sideload via a developer certificate or TestFlight only.
- **Avoid a cloud backend that logs in for users.** Logging in from a data
  center IP is exactly what gets connections blocked. Keep the login on the
  user's own device/network.

The core (`clean_followers.run(...)` with pluggable `log` / `ask_code` /
`should_stop` callbacks) is already UI-agnostic, so a Kivy front-end can reuse
it directly.

## Disclaimer

This project is provided "as is" under the MIT License, with no warranty. It is
not affiliated with, endorsed by, or connected to Instagram or Meta. You are
solely responsible for how you use it and for any consequences to your account.
