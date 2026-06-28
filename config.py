"""
⚙️ Konfigurasi WTB Bot — Versi Railway (baca dari environment variable)
"""
import os

BOT_TOKEN    = os.environ.get("BOT_TOKEN")
CHANNEL_ID   = int(os.environ.get("CHANNEL_ID", "0"))
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@grammenfess")
DISCUSSION_GROUP_ID = int(os.environ.get("DISCUSSION_GROUP_ID", "0"))

ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "5739503807").split(",")
    if x.strip()
]

REQUIRED_CHANNELS = [
    {"id": -1003614448116, "username": "@grammenfess",    "name": "base wtb"},
    {"id": -1002598139052, "username": "@dagetele",       "name": "base daget"},
    {"id": -1001899551122, "username": "@jastipsamudera", "name": "jastip samudera"},
    {"id": -1002177941119, "username": "@sailxor",        "name": "channel store"},
    {"id": -1003720700139, "username": "@jastipperi",     "name": "jastip peri"},
]

BANNED_WORDS = [
    "anjing", "bangsat", "babi", "kontol", "memek",
    "tolol", "goblok", "idiot", "bajingan", "keparat",
    "bocil", "basah", "rahim", "desah", "18+", "viral",
    "judi", "slot", "togel", "gacor", "bet",
]
