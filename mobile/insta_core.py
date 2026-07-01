"""
insta_core.py
-------------
Reusable Instagram cleanup logic for the mobile (Kivy) app. It mirrors the
desktop clean_followers.py core but drops the terminal/argparse bits and takes a
writable data directory (Android app storage).

On Android we use instagrapi 1.x + pydantic v1 (pure Python), because pydantic v2
ships a Rust extension that python-for-android cannot build.
"""

import json
import os
import random
import time
from datetime import date

# instagrapi is imported lazily (see _load_instagrapi) so that importing this
# module never fails at app startup on Android — any import problem then shows
# up as a normal error message when the user taps Connect, not a black screen.
Client = None
ClientError = LoginRequired = PleaseWaitFewMinutes = ChallengeRequired = \
    TwoFactorRequired = Exception


def _load_instagrapi():
    global Client, ClientError, LoginRequired
    global PleaseWaitFewMinutes, ChallengeRequired, TwoFactorRequired
    from instagrapi import Client as _Client
    from instagrapi.exceptions import (
        ClientError as _ClientError,
        LoginRequired as _LoginRequired,
        PleaseWaitFewMinutes as _PleaseWaitFewMinutes,
        ChallengeRequired as _ChallengeRequired,
        TwoFactorRequired as _TwoFactorRequired,
    )
    Client = _Client
    ClientError = _ClientError
    LoginRequired = _LoginRequired
    PleaseWaitFewMinutes = _PleaseWaitFewMinutes
    ChallengeRequired = _ChallengeRequired
    TwoFactorRequired = _TwoFactorRequired

SAFE_LIMIT = 100
MAX_LIMIT = 1000

MODE_REMOVE_FOLLOWERS = "remove-followers"
MODE_UNFOLLOW_NONMUTUAL = "unfollow-nonmutual"
MODE_UNFOLLOW_ALL = "unfollow-all"
MODES = (MODE_REMOVE_FOLLOWERS, MODE_UNFOLLOW_NONMUTUAL, MODE_UNFOLLOW_ALL)
MODE_LABELS = {
    MODE_REMOVE_FOLLOWERS: "Remove followers I don't follow back",
    MODE_UNFOLLOW_NONMUTUAL: "Unfollow accounts that don't follow me back",
    MODE_UNFOLLOW_ALL: "Unfollow everyone I follow",
}

SPEED_SAFE = "Safe (recommended)"
SPEED_MEDIUM = "Medium"
SPEED_FAST = "Fast (risky)"
SPEED_DEFAULT = SPEED_SAFE
SPEED_PRESETS = {
    SPEED_SAFE: dict(min_delay=25, max_delay=70, long_every=15, long_min=240, long_max=600),
    SPEED_MEDIUM: dict(min_delay=8, max_delay=20, long_every=25, long_min=90, long_max=180),
    SPEED_FAST: dict(min_delay=2, max_delay=6, long_every=40, long_min=45, long_max=90),
}


class Core:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.session_path = os.path.join(data_dir, "session.json")
        self.state_path = os.path.join(data_dir, "state.json")
        self.cl = None

    # -- json helpers ---------------------------------------------------- #
    def _load(self, path, default=None):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default

    def _save(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # -- login ----------------------------------------------------------- #
    def connect(self, username="", password="", sessionid="", ask_code=None, log=print):
        _load_instagrapi()
        ask = ask_code or (lambda p: "")
        cl = Client()
        cl.delay_range = [1, 3]
        cl.challenge_code_handler = lambda u, choice: ask(
            "Instagram sent a security code to your %s. Enter it:" % choice)

        if os.path.exists(self.session_path):
            try:
                cl.load_settings(self.session_path)
                cl.get_timeline_feed()
                log("Reused existing session.")
                self.cl = cl
                return self._status(cl, username)
            except Exception:
                log("Saved session invalid, logging in again...")
                cl = Client()
                cl.delay_range = [1, 3]

        sessionid = (sessionid or "").strip()
        if sessionid:
            cl.login_by_sessionid(sessionid)
            cl.dump_settings(self.session_path)
            log("Logged in using the session id.")
            self.cl = cl
            return self._status(cl, username)

        if not username or not password:
            raise RuntimeError("Enter a username and password, or a session id.")
        try:
            cl.login(username, password)
        except TwoFactorRequired:
            code = ask("Two-factor code (6 digits):")
            cl.login(username, password, verification_code=code)
        cl.dump_settings(self.session_path)
        log("Logged in, session saved.")
        self.cl = cl
        return self._status(cl, username)

    def _status(self, cl, username):
        uname = (username or "").strip() or getattr(cl, "username", "") or ""
        try:
            me = cl.user_info(cl.user_id)
            return {"username": uname or me.username,
                    "followers": int(me.follower_count),
                    "following": int(me.following_count)}
        except Exception:
            return {"username": uname or "your account", "followers": None, "following": None}

    # -- targets --------------------------------------------------------- #
    def compute_targets(self, mode, refresh=False, log=print):
        cl = self.cl
        path = os.path.join(self.data_dir, "targets_%s.json" % mode)
        if not refresh and os.path.exists(path):
            log("Loaded targets from cache.")
            return self._load(path)

        log("Fetching followers...")
        followers = cl.user_followers(cl.user_id, amount=0)
        log("   %d followers." % len(followers))
        log("Fetching following...")
        following = cl.user_following(cl.user_id, amount=0)
        log("   %d following." % len(following))

        fset, gset = set(followers), set(following)
        if mode == MODE_REMOVE_FOLLOWERS:
            items = [(u, i) for u, i in followers.items() if u not in gset]
        elif mode == MODE_UNFOLLOW_NONMUTUAL:
            items = [(u, i) for u, i in following.items() if u not in fset]
        else:
            items = list(following.items())

        targets = [{"pk": u, "username": info.username} for u, info in items]
        self._save(path, targets)
        log("=> %d account(s) match." % len(targets))
        return targets

    # -- state ----------------------------------------------------------- #
    def _today_state(self):
        state = self._load(self.state_path, default={}) or {}
        today = date.today().isoformat()
        if state.get("date") != today:
            state["date"] = today
            state["actions_today"] = 0
        state.setdefault("actions_today", 0)
        state.setdefault("processed", {})
        return state

    # -- run ------------------------------------------------------------- #
    def run(self, mode, limit, dry, speed=SPEED_DEFAULT, refresh=False,
            log=print, should_stop=None, confirm=None):
        should_stop = should_stop or (lambda: False)
        preset = SPEED_PRESETS.get(speed, SPEED_PRESETS[SPEED_DEFAULT])
        verb = "unfollowed" if mode != MODE_REMOVE_FOLLOWERS else "removed"

        targets = self.compute_targets(mode, refresh, log=log)
        state = self._today_state()
        done = set(state["processed"].get(mode, []))
        remaining = [t for t in targets if t["pk"] not in done]
        left = max(0, limit - state["actions_today"])
        batch = remaining[:left]

        log("\n%s%d action(s) planned (limit %d, done today %d)." % (
            "[DRY-RUN] " if dry else "", len(batch), limit, state["actions_today"]))
        if not batch:
            log("Nothing to do.")
            return
        if not dry and confirm and not confirm(len(batch)):
            log("Aborted.")
            return

        for i, t in enumerate(batch, start=1):
            if should_stop():
                log("Stopped.")
                break
            label = "[%d/%d] @%s" % (i, len(batch), t["username"])
            try:
                if dry:
                    log("%s -> (dry-run)" % label)
                else:
                    if mode == MODE_REMOVE_FOLLOWERS:
                        self.cl.user_remove_follower(t["pk"])
                    else:
                        self.cl.user_unfollow(t["pk"])
                    log("%s -> %s" % (label, verb))
                    state["processed"].setdefault(mode, []).append(t["pk"])
                    state["actions_today"] += 1
                    self._save(self.state_path, state)
            except PleaseWaitFewMinutes:
                log("Instagram asked to wait. Stopping for today.")
                break
            except ChallengeRequired:
                log("Security challenge. STOP for a few days.")
                break
            except ClientError as e:
                log("%s -> error (skipped): %s" % (label, e))

            if i < len(batch) and not should_stop():
                if i % preset["long_every"] == 0:
                    self._sleep(random.uniform(preset["long_min"], preset["long_max"]), log, should_stop)
                else:
                    self._sleep(random.uniform(preset["min_delay"], preset["max_delay"]), log, should_stop)

        log("\nDone. %s today: %d." % (verb.capitalize(), state["actions_today"]))

    def _sleep(self, seconds, log, should_stop):
        log("   ...waiting %.0fs" % seconds)
        end = time.time() + seconds
        while time.time() < end:
            if should_stop and should_stop():
                return
            time.sleep(min(0.5, max(0.0, end - time.time())))
