"""
clean_followers.py
------------------
Clean up your Instagram relationships in a careful, semi-automated way. Three modes:

  - remove-followers   : remove followers you do NOT follow back  (they stop following you)
  - unfollow-nonmutual : unfollow accounts you follow that don't follow you back
  - unfollow-all       : unfollow everyone you currently follow

Built-in safety:
 - dry-run by default (nothing changes unless you pass --execute)
 - per-run limit you choose from 0 to 1000 (100 is the recommended safe ceiling)
 - randomized human-like delays + regular long pauses
 - session reuse (no re-login / re-2FA on every run)
 - resumable state: an account already processed is never processed twice
 - interactive two-factor auth (2FA) and security-challenge handling

Quick start (command line):
    python clean_followers.py                                  # dry-run, remove-followers
    python clean_followers.py --mode unfollow-nonmutual        # dry-run, unfollow non-mutuals
    python clean_followers.py --limit 40 --execute             # actually act on up to 40
    python clean_followers.py --refresh                        # recompute the lists

Prefer a window? Run:  python gui.py

WARNING: automating actions violates Instagram's Terms of Service. Even with
these precautions a temporary block or suspension is possible. Go slow. If you
hit a security "challenge" or a "please wait" message, STOP for a few days.
"""

import argparse
import getpass
import json
import os
import random
import sys
import time
from datetime import date

try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        ClientError,
        LoginRequired,
        PleaseWaitFewMinutes,
        ChallengeRequired,
        TwoFactorRequired,
    )
except ImportError:
    sys.exit(
        "The 'instagrapi' package is not installed.\n"
        "Run:  pip install -r requirements.txt"
    )

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
SESSION_PATH = os.path.join(HERE, "session.json")
STATE_PATH = os.path.join(HERE, "state.json")

# Recommended safety ceiling. You can go higher (up to MAX_LIMIT) but the risk
# of a temporary block from Instagram increases sharply.
SAFE_LIMIT = 100
MAX_LIMIT = 1000

# Action modes
MODE_REMOVE_FOLLOWERS = "remove-followers"
MODE_UNFOLLOW_NONMUTUAL = "unfollow-nonmutual"
MODE_UNFOLLOW_ALL = "unfollow-all"
MODES = (MODE_REMOVE_FOLLOWERS, MODE_UNFOLLOW_NONMUTUAL, MODE_UNFOLLOW_ALL)
MODE_LABELS = {
    MODE_REMOVE_FOLLOWERS: "Remove followers I don't follow back",
    MODE_UNFOLLOW_NONMUTUAL: "Unfollow accounts that don't follow me back",
    MODE_UNFOLLOW_ALL: "Unfollow everyone I follow",
}

# Speed presets: faster = fewer/shorter pauses = higher block risk.
SPEED_SAFE = "Safe (recommended)"
SPEED_MEDIUM = "Medium"
SPEED_FAST = "Fast (risky)"
SPEED_DEFAULT = SPEED_SAFE
SPEED_PRESETS = {
    SPEED_SAFE: dict(min_delay_seconds=25, max_delay_seconds=70,
                     long_pause_every=15, long_pause_min_seconds=240,
                     long_pause_max_seconds=600),
    SPEED_MEDIUM: dict(min_delay_seconds=8, max_delay_seconds=20,
                       long_pause_every=25, long_pause_min_seconds=90,
                       long_pause_max_seconds=180),
    SPEED_FAST: dict(min_delay_seconds=2, max_delay_seconds=6,
                     long_pause_every=40, long_pause_min_seconds=45,
                     long_pause_max_seconds=90),
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cache_path_for(mode):
    return os.path.join(HERE, f"targets_cache_{mode}.json")


def interruptible_sleep(seconds, log=print, should_stop=None):
    """Sleep, but wake up quickly if should_stop() becomes true."""
    log(f"   ...waiting {seconds:0.0f}s")
    end = time.time() + seconds
    while time.time() < end:
        if should_stop and should_stop():
            return
        time.sleep(min(0.5, max(0.0, end - time.time())))


def _terminal_ask(prompt_text):
    return input(prompt_text).strip()


# --------------------------------------------------------------------------- #
# Configuration & credentials (command-line use)
# --------------------------------------------------------------------------- #
def load_config():
    """config.json is optional. Missing keys fall back to sensible defaults and
    credentials are asked interactively so nothing sensitive needs to be stored."""
    cfg = load_json(CONFIG_PATH, default={}) or {}

    # A browser session id is enough on its own; skip the credential prompts.
    if (cfg.get("sessionid") or "").strip():
        return cfg

    username = cfg.get("username") or ""
    if not username or username.startswith("YOUR_"):
        username = input("Instagram username: ").strip()
    cfg["username"] = username

    password = cfg.get("password") or ""
    if not password or password.startswith("YOUR_"):
        password = getpass.getpass("Instagram password (hidden): ")
    cfg["password"] = password

    return cfg


def resolve_limit(cli_limit, cfg, assume_yes):
    """Return the per-run action limit (0..MAX_LIMIT), warning past SAFE_LIMIT."""
    limit = cli_limit if cli_limit is not None else cfg.get("daily_limit", 40)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        sys.exit(f"Invalid limit: {limit!r}. Use a whole number 0-{MAX_LIMIT}.")

    if limit < 0 or limit > MAX_LIMIT:
        sys.exit(f"Limit must be between 0 and {MAX_LIMIT} (got {limit}).")

    if limit > SAFE_LIMIT:
        print(
            "\n" + "!" * 64 + "\n"
            f"WARNING: you set the limit to {limit}, above the recommended safe\n"
            f"ceiling of {SAFE_LIMIT}. Instagram commonly blocks accounts that\n"
            "act on too many relationships in a short time. Higher = riskier.\n"
            + "!" * 64
        )
        if not assume_yes and input(
            f"Really proceed with a limit of {limit}? [y/N] "
        ).strip().lower() not in ("y", "yes"):
            sys.exit("Aborted. Re-run with a limit of 100 or less to stay safe.")

    return limit


# --------------------------------------------------------------------------- #
# Login (session reuse + 2FA + security challenge)
# --------------------------------------------------------------------------- #
def _make_challenge_handler(ask):
    return lambda username, choice: ask(
        f"Instagram sent a security code to your {choice}. Enter it: "
    )


def _new_client(ask):
    cl = Client()
    cl.delay_range = [1, 3]  # natural delay between internal API calls
    cl.challenge_code_handler = _make_challenge_handler(ask)
    return cl


def login(cfg, ask_code=None, log=print):
    """Log in with whatever is available, most reliable first:

      1. a previously saved session file (cookies, no password needed);
      2. a browser 'session id' cookie (recommended: sidesteps 2FA here);
      3. username + password (+ interactive 2FA / security challenge).

    ask_code(prompt_text) -> str is called when Instagram needs a verification
    code. Defaults to the terminal; the GUI passes a dialog-based version.
    """
    ask = ask_code or _terminal_ask
    cl = _new_client(ask)

    sessionid = (cfg.get("sessionid") or "").strip()
    username = (cfg.get("username") or "").strip()
    password = cfg.get("password") or ""

    # 1) Reuse a saved session (validated purely from cookies).
    if os.path.exists(SESSION_PATH):
        try:
            cl.load_settings(SESSION_PATH)
            cl.get_timeline_feed()  # cheap call to confirm the session is alive
            log("Reused existing session.")
            return cl
        except Exception:
            log("Saved session invalid, logging in again...")
            cl = _new_client(ask)

    # 2) Log in with a browser session id (most reliable path).
    if sessionid:
        try:
            cl.login_by_sessionid(sessionid)
            cl.dump_settings(SESSION_PATH)
            log("Logged in using the browser session id.")
            return cl
        except Exception as e:
            raise RuntimeError(
                "Login with the session id failed (it may be expired or wrong).\n"
                "Log into instagram.com in your browser, copy a fresh 'sessionid' "
                f"cookie, and try again.\n[{e}]"
            )

    # 3) Username + password (+ interactive 2FA / challenge).
    if not username or not password:
        raise RuntimeError(
            "No credentials provided. Enter a username and password, or paste a "
            "browser session id."
        )
    try:
        try:
            cl.login(username, password)
        except TwoFactorRequired:
            log("Two-factor authentication is enabled; asking for the code.")
            code = ask("Two-factor code (6 digits from your app or SMS): ")
            cl.login(username, password, verification_code=code)
    except ChallengeRequired:
        raise RuntimeError(
            "Instagram raised a security challenge it could not resolve here.\n"
            "Easiest fix: use the 'browser session id' login method instead."
        )
    except ClientError as e:
        raise RuntimeError(f"Login failed: {e}")

    cl.dump_settings(SESSION_PATH)
    log("Logged in successfully, session saved (no 2FA needed next time).")
    return cl


def account_counts(cl):
    """Return (followers, following) for the logged-in account, or (None, None)."""
    try:
        me = cl.user_info(cl.user_id)
        return int(me.follower_count), int(me.following_count)
    except Exception:
        return None, None


def sessionid_from_browser(preferred=None):
    """Read the Instagram 'sessionid' cookie straight from an installed browser.

    Returns (sessionid, browser_name) or (None, None). Requires the optional
    'browser_cookie3' package; falls back gracefully if it's missing or the
    browser encrypts cookies in a way we can't read.
    """
    try:
        import browser_cookie3 as bc
    except ImportError:
        raise RuntimeError(
            "Automatic import needs the 'browser_cookie3' package.\n"
            "Install it with:  pip install browser_cookie3\n"
            "Or paste the session id manually."
        )

    candidates = [
        ("Brave", getattr(bc, "brave", None)),
        ("Chrome", getattr(bc, "chrome", None)),
        ("Edge", getattr(bc, "edge", None)),
        ("Firefox", getattr(bc, "firefox", None)),
        ("Opera", getattr(bc, "opera", None)),
    ]
    if preferred:
        candidates.sort(key=lambda c: c[0].lower() != preferred.lower())

    for name, fn in candidates:
        if not fn:
            continue
        try:
            jar = fn(domain_name="instagram.com")
            for cookie in jar:
                if cookie.name == "sessionid" and cookie.value:
                    return cookie.value, name
        except Exception:
            continue
    return None, None


# --------------------------------------------------------------------------- #
# Target computation
# --------------------------------------------------------------------------- #
def compute_targets(cl, cfg, mode, refresh, log=print):
    """Return the accounts to act on, depending on the chosen mode."""
    path = cache_path_for(mode)
    if not refresh and os.path.exists(path):
        log("Loaded target list from cache (use Refresh to recompute).")
        return load_json(path)

    log("Fetching your followers... (can take a while on a large account)")
    followers = cl.user_followers(cl.user_id, amount=0)
    log(f"   {len(followers)} followers.")

    log("Fetching who you follow...")
    following = cl.user_following(cl.user_id, amount=0)
    log(f"   {len(following)} following.")

    follower_ids = set(followers.keys())
    following_ids = set(following.keys())
    whitelist = set(str(x).lower() for x in cfg.get("whitelist", []))

    if mode == MODE_REMOVE_FOLLOWERS:
        items = [(uid, u) for uid, u in followers.items() if uid not in following_ids]
    elif mode == MODE_UNFOLLOW_NONMUTUAL:
        items = [(uid, u) for uid, u in following.items() if uid not in follower_ids]
    elif mode == MODE_UNFOLLOW_ALL:
        items = list(following.items())
    else:
        raise ValueError(f"Unknown mode: {mode}")

    targets = []
    for uid, user in items:
        if uid in whitelist or (user.username or "").lower() in whitelist:
            continue  # protected by whitelist
        targets.append({"pk": uid, "username": user.username})

    save_json(path, targets)
    log(f"=> {len(targets)} account(s) match '{MODE_LABELS[mode]}'.")
    return targets


def _apply_action(cl, mode, pk):
    if mode == MODE_REMOVE_FOLLOWERS:
        return cl.user_remove_follower(pk)
    return cl.user_unfollow(pk)


# --------------------------------------------------------------------------- #
# State (daily progress / resume), namespaced per mode
# --------------------------------------------------------------------------- #
def get_today_state():
    state = load_json(STATE_PATH, default={}) or {}
    today = date.today().isoformat()
    if state.get("date") != today:
        state["date"] = today
        state["actions_today"] = 0
    # migrate old field name if present
    state.setdefault("actions_today", state.get("removed_today", 0))
    state.setdefault("processed", {})
    return state


# --------------------------------------------------------------------------- #
# Core run (shared by the CLI and the GUI)
# --------------------------------------------------------------------------- #
def connect(cfg, ask_code=None, log=print, on_status=None):
    """Log in and report the account status. Returns (client, info dict).

    info = {"username": str, "followers": int|None, "following": int|None}.
    on_status(text, connected: bool) lets a GUI show a live connection status.
    """
    def status(text, connected=False):
        if on_status:
            on_status(text, connected)

    status("Connecting...", False)
    try:
        cl = login(cfg, ask_code=ask_code, log=log)
    except Exception:
        status("Not connected", False)
        raise

    uname = (cfg.get("username") or "").strip()
    if not uname:
        uname = getattr(cl, "username", "") or ""
    if not uname:
        try:
            uname = cl.account_info().username
        except Exception:
            uname = "your account"

    followers_n, following_n = account_counts(cl)
    if followers_n is not None:
        status(
            f"Connected as @{uname}  •  "
            f"{followers_n} followers / {following_n} following",
            True,
        )
        log(f"Account @{uname}: {followers_n} followers, {following_n} following.")
    else:
        status(f"Connected as @{uname}", True)

    return cl, {"username": uname, "followers": followers_n, "following": following_n}


def run_actions(cl, cfg, limit, dry, mode=MODE_REMOVE_FOLLOWERS, refresh=False,
                log=print, should_stop=None, confirm_batch=None):
    """Compute targets and act on up to `limit`, using an already-connected client."""
    should_stop = should_stop or (lambda: False)

    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")

    is_unfollow = mode != MODE_REMOVE_FOLLOWERS
    verb_past = "unfollowed" if is_unfollow else "removed"

    targets = compute_targets(cl, cfg, mode, refresh, log=log)

    state = get_today_state()
    done = set(state["processed"].get(mode, []))
    remaining = [t for t in targets if t["pk"] not in done]

    left_today = max(0, limit - state["actions_today"])
    batch = remaining[:left_today]

    log(
        f"\n{'[DRY-RUN] ' if dry else ''}"
        f"{len(batch)} action(s) planned this run "
        f"(mode: {MODE_LABELS[mode]}; limit {limit}; "
        f"already done today {state['actions_today']}; "
        f"{len(remaining)} still to process)."
    )

    if not batch:
        log("Nothing to do. Either the limit is reached or there are no targets.")
        return

    if not dry and confirm_batch and not confirm_batch(len(batch)):
        log("Aborted before making any change.")
        return

    long_every = int(cfg.get("long_pause_every", 15))

    for i, t in enumerate(batch, start=1):
        if should_stop():
            log("Stopped by user.")
            break

        label = f"[{i}/{len(batch)}] @{t['username']} ({t['pk']})"
        try:
            if dry:
                log(f"{label}  -> (dry-run, nothing changed)")
            else:
                _apply_action(cl, mode, t["pk"])
                log(f"{label}  -> {verb_past}")
                state["processed"].setdefault(mode, []).append(t["pk"])
                state["actions_today"] += 1
                save_json(STATE_PATH, state)
        except PleaseWaitFewMinutes:
            log("Instagram asked us to wait. Stopping for today.")
            break
        except ChallengeRequired:
            log("Security challenge triggered. STOP. Wait a few days before retrying.")
            break
        except ClientError as e:
            log(f"{label}  -> error (skipped): {e}")

        if i < len(batch) and not should_stop():
            if i % long_every == 0:
                log("   -- long safety pause --")
                interruptible_sleep(
                    random.uniform(cfg.get("long_pause_min_seconds", 240),
                                   cfg.get("long_pause_max_seconds", 600)),
                    log=log, should_stop=should_stop,
                )
            else:
                interruptible_sleep(
                    random.uniform(cfg.get("min_delay_seconds", 25),
                                   cfg.get("max_delay_seconds", 70)),
                    log=log, should_stop=should_stop,
                )

    log(
        f"\nDone. {verb_past.capitalize()} today: {state['actions_today']}. "
        f"Still to process: {max(0, len(remaining) - len(batch))}."
    )
    if dry:
        log("This was a DRY-RUN. Add --execute (CLI) or tick 'Execute' (GUI) to act.")


def run(cfg, limit, dry, mode=MODE_REMOVE_FOLLOWERS, refresh=False, ask_code=None,
        log=print, should_stop=None, confirm_batch=None, on_status=None):
    """Convenience wrapper: connect, then act. Used by the command line."""
    cl, _info = connect(cfg, ask_code=ask_code, log=log, on_status=on_status)
    run_actions(cl, cfg, limit, dry, mode=mode, refresh=refresh, log=log,
                should_stop=should_stop, confirm_batch=confirm_batch)


# --------------------------------------------------------------------------- #
# Command-line entry point
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="Clean up your Instagram followers / following."
    )
    parser.add_argument(
        "--mode", choices=MODES, default=MODE_REMOVE_FOLLOWERS,
        help="What to do (default: remove-followers).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help=f"How many to act on this run (0-{MAX_LIMIT}). "
             f"{SAFE_LIMIT} is the recommended safe ceiling.",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually act. Without this flag it's a dry-run.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Force dry-run even if the config enables execution.",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Recompute the followers/following lists from Instagram.",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip confirmation prompts (use with care).",
    )
    parser.add_argument(
        "--sessionid", default=None,
        help="Log in with a browser 'sessionid' cookie instead of a password.",
    )
    args = parser.parse_args()

    if args.sessionid:
        cfg = load_json(CONFIG_PATH, default={}) or {}
        cfg["sessionid"] = args.sessionid
    else:
        cfg = load_config()

    if args.dry_run:
        dry = True
    elif args.execute:
        dry = False
    else:
        dry = cfg.get("dry_run", True)

    limit = resolve_limit(args.limit, cfg, args.yes)

    def confirm_batch(count):
        if args.yes:
            return True
        return input(f"Act on {count} account(s) now? [y/N] ").strip().lower() in ("y", "yes")

    try:
        run(cfg, limit, dry, mode=args.mode, refresh=args.refresh, confirm_batch=confirm_batch)
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
