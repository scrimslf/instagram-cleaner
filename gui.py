"""
gui.py
------
A tiny, dependency-free window for clean_followers.py, built on Tkinter (part of
the Python standard library). It uses almost no resources: no browser, no web
server, just a native window.

Run:  python gui.py
"""

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

import clean_followers as core

APP_TITLE = "Instagram Non-Follower Cleaner"


class App:
    def __init__(self, root):
        self.root = root
        self.worker = None
        self.stop_event = threading.Event()

        root.title(APP_TITLE)
        root.minsize(560, 480)

        pad = {"padx": 8, "pady": 4}
        form = ttk.Frame(root)
        form.pack(fill="x", **pad)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Username").grid(row=0, column=0, sticky="w", **pad)
        self.username = ttk.Entry(form)
        self.username.grid(row=0, column=1, columnspan=3, sticky="ew", **pad)

        ttk.Label(form, text="Password").grid(row=1, column=0, sticky="w", **pad)
        self.password = ttk.Entry(form, show="*")
        self.password.grid(row=1, column=1, columnspan=3, sticky="ew", **pad)

        ttk.Label(form, text="How many (0-1000)").grid(row=2, column=0, sticky="w", **pad)
        self.limit = tk.IntVar(value=40)
        self.spin = ttk.Spinbox(form, from_=0, to=core.MAX_LIMIT, textvariable=self.limit, width=8)
        self.spin.grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(
            form,
            text=f"(100 = risk ceiling; higher is riskier)",
            foreground="#a15c00",
        ).grid(row=2, column=2, columnspan=2, sticky="w", **pad)

        self.execute = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form, text="Execute for real (unticked = simulation / dry-run)",
            variable=self.execute,
        ).grid(row=3, column=0, columnspan=4, sticky="w", **pad)

        self.refresh = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form, text="Refresh follower/following lists (slower)",
            variable=self.refresh,
        ).grid(row=4, column=0, columnspan=4, sticky="w", **pad)

        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.start_btn = ttk.Button(btns, text="Start", command=self.on_start)
        self.start_btn.pack(side="left", **pad)
        self.stop_btn = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left", **pad)

        self.console = scrolledtext.ScrolledText(root, height=18, state="disabled", wrap="word")
        self.console.pack(fill="both", expand=True, **pad)

        self.log(
            "Ready. Nothing is removed until you tick 'Execute'.\n"
            "Automating Instagram breaks its Terms of Service - use at your own risk.\n"
        )

    # -- thread-safe helpers ------------------------------------------------- #
    def log(self, msg):
        def _append():
            self.console.configure(state="normal")
            self.console.insert("end", str(msg) + "\n")
            self.console.see("end")
            self.console.configure(state="disabled")
        self.root.after(0, _append)

    def ask_code(self, prompt):
        """Called from the worker thread; show the dialog on the main thread."""
        holder = {}
        done = threading.Event()

        def _ask():
            holder["v"] = simpledialog.askstring(
                "Verification code", prompt, parent=self.root
            )
            done.set()

        self.root.after(0, _ask)
        done.wait()
        return (holder.get("v") or "").strip()

    def confirm_batch(self, count):
        holder = {}
        done = threading.Event()

        def _ask():
            holder["v"] = messagebox.askyesno(
                "Confirm", f"Remove {count} follower(s) now?", parent=self.root
            )
            done.set()

        self.root.after(0, _ask)
        done.wait()
        return bool(holder.get("v"))

    # -- buttons ------------------------------------------------------------- #
    def on_start(self):
        username = self.username.get().strip()
        password = self.password.get()
        if not username or not password:
            messagebox.showerror(APP_TITLE, "Enter your username and password.")
            return

        try:
            limit = int(self.limit.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_TITLE, "The number must be a whole number 0-1000.")
            return
        if limit < 0 or limit > core.MAX_LIMIT:
            messagebox.showerror(APP_TITLE, f"The number must be between 0 and {core.MAX_LIMIT}.")
            return

        execute = self.execute.get()
        if limit > core.SAFE_LIMIT:
            if not messagebox.askyesno(
                APP_TITLE,
                f"You chose {limit}, above the safe ceiling of {core.SAFE_LIMIT}.\n"
                "Instagram often blocks accounts that remove too many followers "
                "quickly. Higher = riskier.\n\nProceed anyway?",
            ):
                return
        if execute:
            if not messagebox.askyesno(
                APP_TITLE,
                f"EXECUTE mode: up to {limit} follower(s) will actually be removed.\n\n"
                "Continue?",
            ):
                return

        cfg = {"username": username, "password": password}
        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.worker = threading.Thread(
            target=self._run, args=(cfg, limit, not execute, self.refresh.get()), daemon=True
        )
        self.worker.start()

    def on_stop(self):
        self.stop_event.set()
        self.log("Stopping after the current step...")
        self.stop_btn.configure(state="disabled")

    def _run(self, cfg, limit, dry, refresh):
        try:
            core.run(
                cfg, limit, dry, refresh=refresh,
                ask_code=self.ask_code,
                log=self.log,
                should_stop=self.stop_event.is_set,
                confirm_batch=self.confirm_batch,
            )
        except Exception as e:  # keep the window alive on any failure
            self.log(f"ERROR: {e}")
        finally:
            self.root.after(0, self._finish)

    def _finish(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
