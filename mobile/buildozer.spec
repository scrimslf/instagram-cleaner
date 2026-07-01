[app]

# Application
title = Instagram Cleaner
package.name = instacleaner
package.domain = org.scrimslf

# Source
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0.0

# Requirements
# NOTE: instagrapi 1.x + pydantic 1.x are used on purpose. pydantic 2.x ships a
# Rust extension (pydantic-core) that python-for-android cannot build. The 1.x
# stack is pure Python and packages cleanly for Android.
requirements = python3,kivy,pillow,requests,urllib3,idna,certifi,charset-normalizer,pysocks,pydantic==1.10.19,instagrapi==1.19.8

orientation = portrait
fullscreen = 0

# Permissions: the app only needs the internet.
android.permissions = INTERNET

# Android build targets (safe defaults; bump if needed).
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a

# Keep it simple: no services, no extra assets.
android.allow_backup = 1

[buildozer]
log_level = 2
warn_on_root = 1
