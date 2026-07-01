"""
main.py - Kivy mobile front-end for the Instagram cleaner.

This is the entry point python-for-android / buildozer packages into the .apk.
It reuses insta_core.py for all the Instagram logic.

Login on mobile: paste a browser 'sessionid' (most reliable), or use
username/password with an interactive 2FA popup. Actions run on the phone, so
they use the phone's residential IP - which is the whole point.
"""

import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput

import insta_core as core


def storage_dir():
    """Writable directory for session/state (Android app storage, else local)."""
    try:
        from android.storage import app_storage_path  # type: ignore
        return app_storage_path()
    except Exception:
        import os
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), **kw)
        self.core = core.Core(storage_dir())
        self.stop_event = threading.Event()
        self.connected = False

        self.status = Label(text="[color=cc3333]Not connected[/color]", markup=True,
                            size_hint_y=None, height=dp(28))
        self.add_widget(self.status)

        self.username = TextInput(hint_text="Username", multiline=False,
                                  size_hint_y=None, height=dp(40))
        self.password = TextInput(hint_text="Password", password=True, multiline=False,
                                  size_hint_y=None, height=dp(40))
        self.sessionid = TextInput(hint_text="or paste browser session id", password=True,
                                   multiline=False, size_hint_y=None, height=dp(40))
        self.add_widget(self.username)
        self.add_widget(self.password)
        self.add_widget(self.sessionid)

        self.connect_btn = Button(text="Connect", size_hint_y=None, height=dp(44),
                                  on_release=lambda *_: self.on_connect())
        self.add_widget(self.connect_btn)

        self.mode = Spinner(text=core.MODE_LABELS[core.MODE_REMOVE_FOLLOWERS],
                            values=[core.MODE_LABELS[m] for m in core.MODES],
                            size_hint_y=None, height=dp(44))
        self.add_widget(self.mode)

        self.speed = Spinner(text=core.SPEED_DEFAULT, values=list(core.SPEED_PRESETS.keys()),
                             size_hint_y=None, height=dp(44))
        self.add_widget(self.speed)

        self.limit = TextInput(text="40", input_filter="int", multiline=False,
                               hint_text="How many (0-1000)", size_hint_y=None, height=dp(40))
        self.add_widget(self.limit)

        exec_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        exec_row.add_widget(Label(text="Execute for real"))
        self.execute = Switch(active=False)
        exec_row.add_widget(self.execute)
        self.add_widget(exec_row)

        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.start_btn = Button(text="Start", disabled=True,
                                on_release=lambda *_: self.on_start())
        self.stop_btn = Button(text="Stop", disabled=True,
                               on_release=lambda *_: self.stop_event.set())
        btns.add_widget(self.start_btn)
        btns.add_widget(self.stop_btn)
        self.add_widget(btns)

        sv = ScrollView()
        self.console = Label(text="", markup=False, size_hint_y=None, halign="left",
                             valign="top")
        self.console.bind(width=lambda *_: setattr(self.console, "text_size",
                                                   (self.console.width, None)))
        self.console.bind(texture_size=lambda *_: setattr(self.console, "height",
                                                          self.console.texture_size[1]))
        sv.add_widget(self.console)
        self.add_widget(sv)

        self.log("Connect first, then choose an action. Nothing changes until "
                 "'Execute for real' is on. Automating Instagram breaks its ToS.")

    # -- thread-safe UI helpers ----------------------------------------- #
    def log(self, msg):
        Clock.schedule_once(lambda *_: setattr(self.console, "text",
                                               self.console.text + str(msg) + "\n"))

    def set_status(self, text, ok):
        color = "33aa33" if ok else "cc3333"
        Clock.schedule_once(lambda *_: setattr(self.status, "text",
                                               "[color=%s]%s[/color]" % (color, text)))

    def ask_code(self, prompt):
        holder, done = {}, threading.Event()

        def build(*_):
            box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
            ti = TextInput(multiline=False, input_filter="int", size_hint_y=None, height=dp(40))
            box.add_widget(Label(text=prompt))
            box.add_widget(ti)
            b = Button(text="OK", size_hint_y=None, height=dp(44))
            box.add_widget(b)
            pop = Popup(title="Verification", content=box, size_hint=(0.9, 0.5))

            def submit(*_):
                holder["v"] = ti.text.strip()
                pop.dismiss()
                done.set()
            b.bind(on_release=submit)
            pop.open()

        Clock.schedule_once(build)
        done.wait()
        return holder.get("v", "")

    def confirm(self, count):
        holder, done = {}, threading.Event()

        def build(*_):
            box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
            box.add_widget(Label(text="Act on %d account(s) now?" % count))
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            yes, no = Button(text="Yes"), Button(text="No")
            row.add_widget(yes)
            row.add_widget(no)
            box.add_widget(row)
            pop = Popup(title="Confirm", content=box, size_hint=(0.9, 0.4))

            def done_with(v):
                holder["v"] = v
                pop.dismiss()
                done.set()
            yes.bind(on_release=lambda *_: done_with(True))
            no.bind(on_release=lambda *_: done_with(False))
            pop.open()

        Clock.schedule_once(build)
        done.wait()
        return holder.get("v", False)

    # -- actions --------------------------------------------------------- #
    def on_connect(self):
        self.connect_btn.disabled = True

        def work():
            try:
                info = self.core.connect(
                    username=self.username.text.strip(),
                    password=self.password.text,
                    sessionid=self.sessionid.text.strip(),
                    ask_code=self.ask_code, log=self.log)
                self.connected = True
                if info.get("followers") is not None:
                    self.set_status("Connected as @%s  -  %s followers / %s following" % (
                        info["username"], info["followers"], info["following"]), True)
                else:
                    self.set_status("Connected as @%s" % info["username"], True)
                Clock.schedule_once(lambda *_: setattr(self.start_btn, "disabled", False))
            except Exception as e:
                self.set_status("Not connected", False)
                self.log("ERROR: %s" % e)
            finally:
                Clock.schedule_once(lambda *_: setattr(self.connect_btn, "disabled", False))

        threading.Thread(target=work, daemon=True).start()

    def _mode_key(self):
        for m, lbl in core.MODE_LABELS.items():
            if lbl == self.mode.text:
                return m
        return core.MODE_REMOVE_FOLLOWERS

    def on_start(self):
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
            self.log("WARNING: %d is above the safe ceiling of %d - higher block risk." % (
                limit, core.SAFE_LIMIT))

        self.stop_event.clear()
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        dry = not self.execute.active
        mode = self._mode_key()
        speed = self.speed.text

        def work():
            try:
                self.core.run(mode, limit, dry, speed=speed, log=self.log,
                              should_stop=self.stop_event.is_set, confirm=self.confirm)
            except Exception as e:
                self.log("ERROR: %s" % e)
            finally:
                Clock.schedule_once(lambda *_: (setattr(self.start_btn, "disabled", False),
                                                setattr(self.stop_btn, "disabled", True)))

        threading.Thread(target=work, daemon=True).start()


class InstaCleanerApp(App):
    def build(self):
        self.title = "Instagram Cleaner"
        return Root()


if __name__ == "__main__":
    InstaCleanerApp().run()
