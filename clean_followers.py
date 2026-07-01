"""
clean_followers.py
------------------
Remove ("remove follower") the Instagram accounts that follow YOU but that you
do NOT follow back, in a careful, semi-automated way.

Built-in safety:
 - dry-run by default (nothing is removed unless you pass --execute)
 - per-run limit you choose from 0 to 1000 (100 is the recommended safe ceiling)
 - randomized human-like delays + regular long pauses
 - session reuse (no re-login / re-2FA on every run)
 - resumable state: an account already removed is never processed twice
 - interactive two-factor auth (2FA) and security-challenge handling

Quick start (command line):
    python clean_followers.py                 # dry-run, shows who WOULD be removed
    python clean_followers.py --limit 40 --execute   # actually remove up to 40
    python clean_followers.py --refresh       # recompute the followers/following lists

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
CACHE_PATH = os.path.join(HERE, "targets_cache.json")

# Recommended safety ceiling. You can go higher (up to MAX_LIMIT) but the risk
# of a temporary block from Instagram increases sharply.
SAFE_LIMIT = 100
MAX_LIMIT = 1000


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
    """Return the per-run removal limit (0..MAX_LIMIT), warning past SAFE_LIMIT."""
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
            "remove too many followers in a short time. Higher = riskier.\n"
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
def login(cfg, ask_code=None, log=print):
    """Log in, reusing a saved session when possible.

    ask_code(prompt_text) -> str is called when Instagram needs a verification
    code (2FA or a security challenge). Defaults to reading from the terminal,
    but the GUI passes a dialog-based version.
    """
    ask = ask_code or _terminal_ask
    cl = Client()
    cl.delay_range = [1, 3]  # natural delay between internal API calls
    cl.challenge_code_handler = lambda username, choice: ask(
        f"Instagram sent a security code to your {choice}. Enter it: "
    )

    # 1) Reuse a saved session if we have one.
    if os.path.exists(SESSION_PATH):
        try:
            cl.load_settings(SESSION_PATH)
            cl.login(cfg["username"], cfg["password"])
            cl.get_timeline_feed()  # cheap call to confirm the session is alive
            log("Reused existing session.")
            return cl
        except (LoginRequired, ClientError):
            log("Saved session expired, logging in again...")
            cl = Client()
            cl.delay_range = [1, 3]
            cl.challenge_code_handler = lambda username, choice: ask(
                f"Instagram sent a security code to your {choice}. Enter it: "
            )

    # 2) Fresh login (handles 2FA and challenges).
    try:
        try:
            cl.login(cfg["username"], cfg["password"])
        except TwoFactorRequired:
            log("Two-factor authentication is enabled; asking for the code.")
            code = ask("Two-factor code (6 digits from your app or SMS): ")
            cl.login(cfg["username"], cfg["password"], verification_code=code)
    except ChallengeRequired:
        raise RuntimeError(
            "Instagram raised a security challenge it could not resolve here. "
            "Open the Instagram app, approve/verify the login, then try again."
        )
    except ClientError as e:
        raise RuntimeError(f"Login failed: {e}")

    cl.dump_settings(SESSION_PATH)
    log("Logged in successfully, session saved (no 2FA needed next time).")
    return cl


# --------------------------------------------------------------------------- #
# Target computation
# --------------------------------------------------------------------------- #
def build_targets(cl, cfg, refresh, log=print):
    """Return the list of accounts that follow you but that you don't follow back."""
    if not refresh and os.path.exists(CACHE_PATH):
        log("Loaded target list from cache (use Refresh to recompute).")
        return load_json(CACHE_PATH)

    log("Fetching your followers... (can take a while on a large account)")
    followers = cl.user_followers(cl.user_id, amount=0)
    log(f"   {len(followers)} followers.")

    log("Fetching who you follow...")
    following = cl.user_following(cl.user_id, amount=0)
    log(f"   {len(following)} following.")

    whitelist = set(str(x).lower() for x in cfg.get("whitelist", []))
    following_ids = set(following.keys())

    targets = []
    for uid, user in followers.items():
        if uid in following_ids:
            continue  # you follow them back -> keep
        if uid in whitelist or (user.username or "").lower() in whitelist:
            continue  # protected by whitelist
        targets.append({"pk": uid, "username": user.username})

    save_json(CACHE_PATH, targets)
    log(f"=> {len(targets)} followers you don't follow back (potential targets).")
    return targets


# --------------------------------------------------------------------------- #
# State (daily progress / resume)
# --------------------------------------------------------------------------- #
def get_today_state():
    state = load_json(STATE_PATH, default={}) or {}
    today = date.today().isoformat()
    if state.get("date") != today:
        state["date"] = today
        state["removed_today"] = 0
    state.setdefault("removed_ids", [])
    return state


# --------------------------------------------------------------------------- #
# Core run (shared by the CLI and the GUI)
# --------------------------------------------------------------------------- #
def run(cfg, limit, dry, refresh=False, ask_code=None, log=print,
        should_stop=None, confirm_batch=None):
    """Log in, compute targets, and remove up to `limit` this run.

    log(str), ask_code(prompt)->str, should_stop()->bool and
    confirm_batch(count)->bool let a GUI (or the CLI) plug in its own behaviour.
    """
    should_stop = should_stop or (lambda: False)

    cl = login(cfg, ask_code=ask_code, log=log)
    targets = build_targets(cl, cfg, refresh, log=log)

    state = get_today_state()
    already = set(state["removed_ids"])
    remaining = [t for t in targets if t["pk"] not in already]

    left_today = max(0, limit - state["removed_today"])
    batch = remaining[:left_today]

    log(
        f"\n{'[DRY-RUN] ' if dry else ''}"
        f"{len(batch)} removals planned this run "
        f"(limit {limit}, already removed today {state['removed_today']}, "
        f"{len(remaining)} still to process)."
    )

    if not batch:
        log("Nothing to do. Either the limit is reached or there are no targets.")
        return

    if not dry and confirm_batch and not confirm_batch(len(batch)):
        log("Aborted before removing anything.")
        return

    long_every = int(cfg.get("long_pause_every", 15))

    for i, t in enumerate(batch, start=1):
        if should_stop():
            log("Stopped by user.")
            break

        label = f"[{i}/{len(batch)}] @{t['username']} ({t['pk']})"
        try:
            if dry:
                log(f"{label}  -> (dry-run, nothing removed)")
            else:
                cl.user_remove_follower(t["pk"])
                log(f"{label}  -> removed")
                state["removed_ids"].append(t["pk"])
                state["removed_today"] += 1
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
        f"\nDone. Removed today: {state['removed_today']}. "
        f"Still to process: {max(0, len(remaining) - len(batch))}."
    )
    if dry:
        log("This was a DRY-RUN. Add --execute (CLI) or tick 'Execute' (GUI) to act.")


# --------------------------------------------------------------------------- #
# Command-line entry point
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="Remove Instagram followers you don't follow back."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help=f"How many to remove this run (0-{MAX_LIMIT}). "
             f"{SAFE_LIMIT} is the recommended safe ceiling.",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually remove followers. Without this flag it's a dry-run.",
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
    args = parser.parse_args()

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
        return input(f"Remove {count} follower(s) now? [y/N] ").strip().lower() in ("y", "yes")

    try:
        run(cfg, limit, dry, refresh=args.refresh, confirm_batch=confirm_batch)
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
