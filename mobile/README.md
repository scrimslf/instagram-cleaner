# Instagram Cleaner — Android app (experimental)

A [Kivy](https://kivy.org) front-end that runs the same cleanup logic **on your
phone**, so actions use your phone's residential IP (much less likely to be
blocked than a server).

> ⚠️ **Status: source is ready to build, but not yet compiled/verified into an
> APK.** Building an Android APK needs a Linux toolchain (Android SDK/NDK). The
> easiest path is the official Docker image — no local setup beyond Docker.
> Same Instagram Terms-of-Service risk as the desktop version applies.

## Files

- `main.py` — the Kivy UI (this is the app entry point).
- `insta_core.py` — the Instagram logic (login, targets, remove/unfollow).
- `buildozer.spec` — the Android build configuration.

## Why instagrapi 1.x here?

The desktop app uses `instagrapi 2.x` + `pydantic 2.x`. On Android that fails:
`pydantic-core` is a Rust extension with no `python-for-android` recipe. So the
mobile build pins **`instagrapi==1.19.8` + `pydantic==1.10.19`**, which are pure
Python and package cleanly. The feature set used here (login, followers,
following, remove follower, unfollow) exists in both versions.

## Build the APK (recommended: Docker)

You need [Docker](https://www.docker.com/products/docker-desktop/). Then, from
this `mobile/` folder:

```bash
# Linux / macOS / WSL:
docker run --rm -v "$PWD":/home/user/hostcwd kivy/buildozer android debug

# Windows PowerShell:
docker run --rm -v "${PWD}:/home/user/hostcwd" kivy/buildozer android debug
```

First run downloads the Android SDK/NDK (several GB) and takes 30–60 minutes.
The APK lands in `mobile/bin/instacleaner-1.0.0-*-debug.apk`.

Copy that file to your Android phone and open it (allow "install from unknown
sources"). This is a **debug** APK — fine for personal use / sideloading.

## Build without Docker (advanced)

On Ubuntu/WSL:
```bash
pip install buildozer cython
sudo apt install -y openjdk-17-jdk zip unzip autoconf libtool pkg-config \
    zlib1g-dev libncurses5-dev libtinfo5 cmake libffi-dev libssl-dev
buildozer android debug
```

## Run on desktop first (quick sanity check)

You can launch the same UI on your computer to check it works before building:
```bash
pip install kivy instagrapi
python main.py
```

## Login on mobile

- **Session id (most reliable):** log into instagram.com in your phone browser,
  copy the `sessionid` cookie, paste it in the app. (Browser auto-import isn't
  available on Android — paste it manually.)
- **Username + password:** a popup asks for your 2FA code if needed.

## iOS?

Not provided. The App Store rejects apps that automate Instagram. A personal
sideload would need a paid Apple developer setup; it's out of scope here.
