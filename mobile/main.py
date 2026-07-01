"""
main.py - KivyMD (Material Design) mobile front-end for the Instagram cleaner.

Entry point that python-for-android / buildozer packages into the .apk.
All Instagram logic lives in insta_core.py; this file is just the UI.

Login on mobile: paste a browser 'sessionid' (most reliable), or use
username/password with an interactive 2FA dialog. Actions run on the phone, so
they use the phone's residential IP.
"""

import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar

import insta_core as core


def storage_dir():
    """Writable directory for session/state (Android app storage, else local)."""
    try:
        from android.storage import app_storage_path  # type: ignore
        return app_storage_path()
    except Exception:
        import os
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def card(title):
    c = MDCard(orientation="vertical", padding=dp(14), spacing=dp(10),
               size_hint_y=None, adaptive_height=True, radius=[dp(16)],
               elevation=2, md_bg_color=(0.13, 0.13, 0.16, 1))
    c.add_widget(MDLabel(text=title, bold=True, font_style="H6",
                         adaptive_height=True))
    return c


class InstaCleanerApp(MDApp):
    def build(self):
        try:
            return self._build_ui()
        except Exception:
            # Never show a silent black screen: surface the error on screen.
            import traceback
            from kivy.uix.label import Label
            from kivy.uix.scrollview import ScrollView as _SV
            lbl = Label(text="Startup error:\n\n" + traceback.format_exc(),
                        halign="left", valign="top", color=(1, 0.5, 0.5, 1),
                        size_hint_y=None, padding=(dp(10), dp(10)))
            lbl.bind(width=lambda *_: setattr(lbl, "text_size", (lbl.width, None)))
            lbl.bind(texture_size=lambda *_: setattr(lbl, "height", lbl.texture_size[1]))
            sv = _SV()
            sv.add_widget(lbl)
            return sv

    def _build_ui(self):
        self.title = "Instagram Cleaner"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.accent_palette = "Pink"

        self.core = core.Core(storage_dir())
        self.stop_event = threading.Event()
        self.connected = False
        self._dialog = None

        root = MDBoxLayout(orientation="vertical")
        root.add_widget(MDTopAppBar(title="Instagram Cleaner",
                                    elevation=3, pos_hint={"top": 1}))

        scroll = ScrollView()
        content = MDBoxLayout(orientation="vertical", padding=dp(12),
                              spacing=dp(12), size_hint_y=None, adaptive_height=True)
        scroll.add_widget(content)
        root.add_widget(scroll)

        # --- status card ---------------------------------------------------
        status = card("Status")
        self.status_lbl = MDLabel(text="[color=e05561]● Not connected[/color]",
                                  markup=True, adaptive_height=True)
        self.counter_lbl = MDLabel(text="Followers: —   Following: —",
                                   theme_text_color="Secondary", adaptive_height=True)
        status.add_widget(self.status_lbl)
        status.add_widget(self.counter_lbl)
        content.add_widget(status)

        # --- login card ----------------------------------------------------
        login = card("1) Connect")
        self.username = MDTextField(hint_text="Username", mode="rectangle")
        self.password = MDTextField(hint_text="Password", password=True, mode="rectangle")
        self.sessionid = MDTextField(hint_text="or paste browser session id",
                                     password=True, mode="rectangle")
        login.add_widget(self.username)
        login.add_widget(self.password)
        login.add_widget(self.sessionid)
        row = MDBoxLayout(adaptive_height=True, spacing=dp(8), size_hint_y=None)
        row.add_widget(MDFlatButton(text="Open Instagram", on_release=self.open_instagram))
        row.add_widget(MDFlatButton(text="How?", on_release=self.show_help))
        login.add_widget(row)
        login.add_widget(MDRaisedButton(text="Connect", pos_hint={"center_x": 0.5},
                                        on_release=self.on_connect))
        content.add_widget(login)

        # --- action card ---------------------------------------------------
        action = card("2) Choose what to do")

        self.mode_key = core.MODE_REMOVE_FOLLOWERS
        self.mode_btn = MDRaisedButton(text=core.MODE_LABELS[self.mode_key],
                                       on_release=lambda *_: self.mode_menu.open())
        self.mode_menu = MDDropdownMenu(caller=self.mode_btn, width_mult=5, items=[
            {"text": core.MODE_LABELS[m], "viewclass": "OneLineListItem",
             "on_release": (lambda m=m: self._pick_mode(m))} for m in core.MODES])
        action.add_widget(self.mode_btn)

        self.speed_val = core.SPEED_DEFAULT
        self.speed_btn = MDRaisedButton(text="Speed: " + self.speed_val,
                                        on_release=lambda *_: self.speed_menu.open())
        self.speed_menu = MDDropdownMenu(caller=self.speed_btn, width_mult=4, items=[
            {"text": s, "viewclass": "OneLineListItem",
             "on_release": (lambda s=s: self._pick_speed(s))} for s in core.SPEED_PRESETS])
        action.add_widget(self.speed_btn)

        self.limit = MDTextField(hint_text="Max per run (0-1000)", text="40",
                                 input_filter="int", mode="rectangle")
        action.add_widget(self.limit)

        exec_row = MDBoxLayout(adaptive_height=True, size_hint_y=None, spacing=dp(8))
        exec_row.add_widget(MDLabel(text="Execute for real (off = simulation)",
                                    adaptive_height=True))
        self.execute = MDSwitch(active=False)
        exec_row.add_widget(self.execute)
        action.add_widget(exec_row)

        ref_row = MDBoxLayout(adaptive_height=True, size_hint_y=None, spacing=dp(8))
        ref_row.add_widget(MDLabel(text="Refresh lists (slower)", adaptive_height=True))
        self.refresh = MDSwitch(active=False)
        ref_row.add_widget(self.refresh)
        action.add_widget(ref_row)

        btns = MDBoxLayout(adaptive_height=True, size_hint_y=None, spacing=dp(8))
        self.start_btn = MDRaisedButton(text="Start", disabled=True, on_release=self.on_start)
        self.stop_btn = MDFlatButton(text="Stop", disabled=True,
                                     on_release=lambda *_: self.stop_event.set())
        btns.add_widget(self.start_btn)
        btns.add_widget(self.stop_btn)
        action.add_widget(btns)
        content.add_widget(action)

        # --- console card --------------------------------------------------
        cons = card("Log")
        self.console = MDLabel(text="", adaptive_height=True, theme_text_color="Secondary")
        cons_scroll = ScrollView(size_hint_y=None, height=dp(180))
        cons_scroll.add_widget(self.console)
        cons.add_widget(cons_scroll)
        content.add_widget(cons)

        self.log("Connect first, then choose an action. Nothing changes until "
                 "'Execute for real' is ON. Automating Instagram breaks its ToS.")
        return root

    # -- thread-safe UI helpers ---------------------------------------------
    def log(self, msg):
        def _a(*_):
            self.console.text += str(msg) + "\n"
        Clock.schedule_once(_a)

    def set_status(self, text, ok):
        color = "3fb950" if ok else "e05561"
        Clock.schedule_once(lambda *_: setattr(
            self.status_lbl, "text", f"[color={color}]● {text}[/color]"))

    def set_counters(self, f, g):
        f = "—" if f is None else f
        g = "—" if g is None else g
        Clock.schedule_once(lambda *_: setattr(
            self.counter_lbl, "text", f"Followers: {f}   Following: {g}"))

    def _pick_mode(self, m):
        self.mode_key = m
        self.mode_btn.text = core.MODE_LABELS[m]
        self.mode_menu.dismiss()

    def _pick_speed(self, s):
        self.speed_val = s
        self.speed_btn.text = "Speed: " + s
        self.speed_menu.dismiss()

    def _ask_dialog(self, title, prompt, numeric=True):
        holder, done = {}, threading.Event()

        def build(*_):
            field = MDTextField(hint_text=prompt,
                                input_filter="int" if numeric else None)
            box = MDBoxLayout(orientation="vertical", adaptive_height=True,
                              size_hint_y=None, padding=dp(4))
            box.add_widget(field)

            def ok(*_):
                holder["v"] = field.text.strip()
                self._dialog.dismiss()
                done.set()

            self._dialog = MDDialog(title=title, type="custom", content_cls=box,
                                    buttons=[MDRaisedButton(text="OK", on_release=ok)])
            self._dialog.open()

        Clock.schedule_once(build)
        done.wait()
        return holder.get("v", "")

    def ask_code(self, prompt):
        return self._ask_dialog("Verification", prompt, numeric=True)

    def confirm(self, count):
        holder, done = {}, threading.Event()

        def build(*_):
            def yes(*_):
                holder["v"] = True
                self._dialog.dismiss()
                done.set()

            def no(*_):
                holder["v"] = False
                self._dialog.dismiss()
                done.set()

            self._dialog = MDDialog(
                title="Confirm", text=f"Act on {count} account(s) now?",
                buttons=[MDFlatButton(text="Cancel", on_release=no),
                         MDRaisedButton(text="Yes", on_release=yes)])
            self._dialog.open()

        Clock.schedule_once(build)
        done.wait()
        return holder.get("v", False)

    # -- login / actions ----------------------------------------------------
    def open_instagram(self, *_):
        import webbrowser
        webbrowser.open("https://www.instagram.com/accounts/login/")

    def show_help(self, *_):
        self._dialog = MDDialog(
            title="Log in with your browser",
            text=("Log into instagram.com in your phone browser, open the page's "
                  "cookies (sessionid), copy its value, and paste it in the "
                  "'session id' field. Your session stays only on this phone."),
            buttons=[MDFlatButton(text="OK", on_release=lambda *_: self._dialog.dismiss())])
        self._dialog.open()

    def on_connect(self, *_):
        u, p, s = self.username.text.strip(), self.password.text, self.sessionid.text.strip()
        if not s and not (u and p):
            self.log("Enter username+password, or paste a session id.")
            return
        self.start_btn.disabled = True

        def work():
            try:
                info = self.core.connect(username=u, password=p, sessionid=s,
                                         ask_code=self.ask_code, log=self.log)
                self.connected = True
                self.set_status("Connected as @%s" % info["username"], True)
                self.set_counters(info.get("followers"), info.get("following"))
                Clock.schedule_once(lambda *_: setattr(self.start_btn, "disabled", False))
            except Exception as e:
                self.connected = False
                self.set_status("Not connected", False)
                self.set_counters(None, None)
                self.log("ERROR: %s" % e)

        threading.Thread(target=work, daemon=True).start()

    def on_start(self, *_):
        if not self.connected:
            self.log("Connect first.")
            return
        try:
            limit = int(self.limit.text or "0")
        except ValueError:
            self.log("Invalid number.")
            return
        limit = max(0, min(core.MAX_LIMIT, limit))
        if limit > core.SAFE_LIMIT:
            self.log("WARNING: %d is above the safe ceiling of %d - higher block risk."
                     % (limit, core.SAFE_LIMIT))
        self.stop_event.clear()
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        dry = not self.execute.active
        mode, speed, refresh = self.mode_key, self.speed_val, self.refresh.active

        def work():
            try:
                self.core.run(mode, limit, dry, speed=speed, refresh=refresh,
                              log=self.log, should_stop=self.stop_event.is_set,
                              confirm=self.confirm)
            except Exception as e:
                self.log("ERROR: %s" % e)
            finally:
                Clock.schedule_once(lambda *_: (setattr(self.start_btn, "disabled", False),
                                                setattr(self.stop_btn, "disabled", True)))

        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    InstaCleanerApp().run()
