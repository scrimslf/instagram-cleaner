"""
gui.py
------
A tiny, dependency-free window for clean_followers.py, built on Tkinter (part of
the Python standard library). It uses almost no resources: no browser engine, no
web server, just a native window.

Flow: connect first (see your follower counts), then choose what to do.

Run:  python gui.py
"""

import os
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

import clean_followers as core

APP_TITLE = "Instagram Cleaner"

SESSIONID_HELP = (
    "Two ways to log in with your browser session:\n\n"
    "AUTOMATIC (easiest):\n"
    "  1. Log into instagram.com in your browser (Brave/Chrome/Firefox/Edge).\n"
    "  2. Click 'Import from browser' - it reads the session for you.\n\n"
    "MANUAL (if automatic fails):\n"
    "  1. Click 'Open Instagram' and log in.\n"
    "  2. Press F12 -> Application tab -> Cookies -> https://www.instagram.com\n"
    "  3. Copy the value of the 'sessionid' cookie and paste it here.\n\n"
    "Your session id grants access to your account. It stays only on this\n"
    "computer (session.json) and is never uploaded anywhere."
)


class App:
    def __init__(self, root):
        self.root = root
        self.worker = None
        self.stop_event = threading.Event()
        self.client = None          # set once connected
        self.connected = False

        root.title(APP_TITLE)
        root.minsize(640, 620)

        pad = {"padx": 8, "pady": 4}

        # --- status bar (connection + follower counter) -------------------- #
        status = ttk.Frame(root)
        status.pack(fill="x", padx=8, pady=(8, 0))
        self.status_dot = tk.Label(status, text="●", fg="#c0392b")
        self.status_dot.pack(side="left")
        self.status_var = tk.StringVar(value="Not connected")
        ttk.Label(status, textvariable=self.status_var).pack(side="left", padx=6)
        self.counter_var = tk.StringVar(value="Followers: —   Following: —")
        ttk.Label(status, textvariable=self.counter_var,
                  font=("", 10, "bold")).pack(side="right", padx=6)

        # --- login box ----------------------------------------------------- #
        login = ttk.LabelFrame(root, text="1) Connect")
        login.pack(fill="x", padx=8, pady=6)
        login.columnconfigure(1, weight=1)

        ttk.Label(login, text="Username").grid(row=0, column=0, sticky="w", **pad)
        self.username = ttk.Entry(login)
        self.username.grid(row=0, column=1, columnspan=3, sticky="ew", **pad)

        ttk.Label(login, text="Password").grid(row=1, column=0, sticky="w", **pad)
        self.password = ttk.Entry(login, show="*")
        self.password.grid(row=1, column=1, columnspan=3, sticky="ew", **pad)

        ttk.Label(login, text="— or browser login (more reliable) —",
                  foreground="#555").grid(row=2, column=0, columnspan=4, sticky="w", **pad)

        ttk.Label(login, text="Session ID").grid(row=3, column=0, sticky="w", **pad)
        self.sessionid = ttk.Entry(login, show="*")
        self.sessionid.grid(row=3, column=1, columnspan=3, sticky="ew", **pad)

        row = ttk.Frame(login)
        row.grid(row=4, column=1, columnspan=3, sticky="w", **pad)
        ttk.Button(row, text="Import from browser", command=self.on_import).pack(side="left")
        ttk.Button(row, text="Open Instagram", command=self.open_instagram).pack(side="left", padx=6)
        ttk.Button(row, text="How?", command=self.show_sessionid_help).pack(side="left")

        self.connect_btn = ttk.Button(login, text="Connect", command=self.on_connect)
        self.connect_btn.grid(row=5, column=1, sticky="w", **pad)

        # --- action box ---------------------------------------------------- #
        action = ttk.LabelFrame(root, text="2) Choose what to do")
        action.pack(fill="x", padx=8, pady=6)
        action.columnconfigure(1, weight=1)

        ttk.Label(action, text="Action").grid(row=0, column=0, sticky="w", **pad)
        self.mode_label = tk.StringVar(value=core.MODE_LABELS[core.MODE_REMOVE_FOLLOWERS])
        ttk.Combobox(action, textvariable=self.mode_label, state="readonly",
                     values=[core.MODE_LABELS[m] for m in core.MODES]
                     ).grid(row=0, column=1, columnspan=3, sticky="ew", **pad)

        ttk.Label(action, text="Speed").grid(row=1, column=0, sticky="w", **pad)
        self.speed_label = tk.StringVar(value=core.SPEED_DEFAULT)
        ttk.Combobox(action, textvariable=self.speed_label, state="readonly",
                     values=list(core.SPEED_PRESETS.keys()), width=18
                     ).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(action, text="(faster = higher block risk)", foreground="#a15c00"
                  ).grid(row=1, column=2, columnspan=2, sticky="w", **pad)

        ttk.Label(action, text="How many (0-1000)").grid(row=2, column=0, sticky="w", **pad)
        self.limit = tk.IntVar(value=40)
        ttk.Spinbox(action, from_=0, to=core.MAX_LIMIT, textvariable=self.limit, width=8
                    ).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(action, text="(100 = risk ceiling; higher is riskier)", foreground="#a15c00"
                  ).grid(row=2, column=2, columnspan=2, sticky="w", **pad)

        self.execute = tk.BooleanVar(value=False)
        ttk.Checkbutton(action, text="Execute for real (unticked = simulation / dry-run)",
                        variable=self.execute).grid(row=3, column=0, columnspan=4, sticky="w", **pad)

        self.refresh = tk.BooleanVar(value=False)
        ttk.Checkbutton(action, text="Refresh follower/following lists (slower)",
                        variable=self.refresh).grid(row=4, column=0, columnspan=4, sticky="w", **pad)

        btns = ttk.Frame(action)
        btns.grid(row=5, column=0, columnspan=4, sticky="w", **pad)
        self.start_btn = ttk.Button(btns, text="Start", command=self.on_start, state="disabled")
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        # --- console ------------------------------------------------------- #
        self.console = scrolledtext.ScrolledText(root, height=14, state="disabled", wrap="word")
        self.console.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.log(
            "Step 1: connect (see your follower counts). Step 2: pick an action.\n"
            "Nothing changes until you tick 'Execute'. Automating Instagram breaks "
            "its Terms of Service - use at your own risk.\n"
        )

    # -- thread-safe helpers ------------------------------------------------- #
    def log(self, msg):
        def _append():
            self.console.configure(state="normal")
            self.console.insert("end", str(msg) + "\n")
            self.console.see("end")
            self.console.configure(state="disabled")
        self.root.after(0, _append)

    def set_status(self, text, connected):
        def _set():
            self.status_var.set(text)
            self.status_dot.configure(fg="#27ae60" if connected else "#c0392b")
        self.root.after(0, _set)

    def set_counters(self, followers, following):
        f = "—" if followers is None else followers
        g = "—" if following is None else following
        txt = f"Followers: {f}   Following: {g}"
        self.root.after(0, lambda: self.counter_var.set(txt))

    def ask_code(self, prompt):
        holder, done = {}, threading.Event()

        def _ask():
            holder["v"] = simpledialog.askstring("Verification code", prompt, parent=self.root)
            done.set()

        self.root.after(0, _ask)
        done.wait()
        return (holder.get("v") or "").strip()

    def confirm_batch(self, count):
        holder, done = {}, threading.Event()

        def _ask():
            holder["v"] = messagebox.askyesno(
                "Confirm", f"Act on {count} account(s) now?", parent=self.root)
            done.set()

        self.root.after(0, _ask)
        done.wait()
        return bool(holder.get("v"))

    # -- login helpers ------------------------------------------------------- #
    def open_instagram(self):
        webbrowser.open("https://www.instagram.com/accounts/login/")

    def show_sessionid_help(self):
        messagebox.showinfo("Log in with your browser", SESSIONID_HELP)

    def on_import(self):
        self.connect_btn.configure(state="disabled")
        self.log("Reading the Instagram session from your browser...")

        def work():
            try:
                sid, browser = core.sessionid_from_browser()
            except Exception as e:
                self.log(f"Import failed: {e}")
                sid, browser = None, None
            if sid:
                def fill():
                    self.sessionid.delete(0, "end")
                    self.sessionid.insert(0, sid)
                self.root.after(0, fill)
                self.log(f"Session imported from {browser}. Now click Connect.")
            else:
                self.log("No Instagram session found. Either you're not logged into "
                         "instagram.com in a supported browser, or your browser (recent "
                         "Brave/Chrome) encrypts cookies in a way that can't be read. "
                         "Easiest fix: paste the session id manually (click 'How?'), or "
                         "log into Instagram in Firefox.")
            self.root.after(0, lambda: self.connect_btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    # -- connect ------------------------------------------------------------- #
    def _collect_cfg(self):
        cfg = {}
        u, p, s = self.username.get().strip(), self.password.get(), self.sessionid.get().strip()
        if s:
            cfg["sessionid"] = s
        if u:
            cfg["username"] = u
        if p:
            cfg["password"] = p
        return cfg

    def on_connect(self):
        cfg = self._collect_cfg()
        has_session = os.path.exists(core.SESSION_PATH)
        if ("sessionid" not in cfg and not (cfg.get("username") and cfg.get("password"))
                and not has_session):
            messagebox.showerror(
                APP_TITLE,
                "To connect: enter username AND password, or import/paste a Session ID.")
            return

        self.connect_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")

        def work():
            try:
                cl, info = core.connect(
                    cfg, ask_code=self.ask_code, log=self.log, on_status=self.set_status)
                self.client = cl
                self.connected = True
                self.set_counters(info.get("followers"), info.get("following"))
                self.log("Connected. You can now choose an action and press Start.")
                self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            except Exception as e:
                self.connected = False
                self.client = None
                self.set_counters(None, None)
                self.log(f"ERROR: {e}")
            finally:
                self.root.after(0, lambda: self.connect_btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    # -- run ----------------------------------------------------------------- #
    def _selected_mode(self):
        for m, lbl in core.MODE_LABELS.items():
            if lbl == self.mode_label.get():
                return m
        return core.MODE_REMOVE_FOLLOWERS

    def on_start(self):
        if not self.connected or self.client is None:
            messagebox.showerror(APP_TITLE, "Connect first (step 1).")
            return
        try:
            limit = int(self.limit.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_TITLE, "The number must be a whole number 0-1000.")
            return
        if limit < 0 or limit > core.MAX_LIMIT:
            messagebox.showerror(APP_TITLE, f"The number must be between 0 and {core.MAX_LIMIT}.")
            return

        mode = self._selected_mode()
        speed = self.speed_label.get()
        execute = self.execute.get()

        if limit > core.SAFE_LIMIT:
            if not messagebox.askyesno(
                APP_TITLE,
                f"You chose {limit}, above the safe ceiling of {core.SAFE_LIMIT}.\n"
                "Instagram often blocks accounts that act too much, too fast. "
                "Higher = riskier.\n\nProceed anyway?"):
                return
        if execute and speed == core.SPEED_FAST:
            if not messagebox.askyesno(
                APP_TITLE,
                "Fast speed uses very short delays and is the most likely to get "
                "you temporarily blocked.\n\nUse it anyway?"):
                return
        if execute:
            if not messagebox.askyesno(
                APP_TITLE,
                f"EXECUTE mode\nAction: {core.MODE_LABELS[mode]}\nSpeed: {speed}\n"
                f"Up to {limit} account(s) will actually be affected.\n\nContinue?"):
                return

        run_cfg = dict(core.SPEED_PRESETS[speed])  # delay settings for this run
        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.connect_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.worker = threading.Thread(
            target=self._run,
            args=(run_cfg, limit, not execute, mode, self.refresh.get()),
            daemon=True)
        self.worker.start()

    def on_stop(self):
        self.stop_event.set()
        self.log("Stopping after the current step...")
        self.stop_btn.configure(state="disabled")

    def _run(self, run_cfg, limit, dry, mode, refresh):
        try:
            core.run_actions(
                self.client, run_cfg, limit, dry, mode=mode, refresh=refresh,
                log=self.log, should_stop=self.stop_event.is_set,
                confirm_batch=self.confirm_batch)
        except Exception as e:
            self.log(f"ERROR: {e}")
        finally:
            self.root.after(0, self._finish)

    def _finish(self):
        self.start_btn.configure(state="normal")
        self.connect_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
