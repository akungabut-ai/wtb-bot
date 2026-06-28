"""
🎱 WTB Auto Forward Bot — Telegram
Versi: 5.1 — Tambah sistem sesi (1 /start = 1 pesan)
"""

import logging
import pickle
import os
import time
import json
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
    ChatPermissions,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.error import TelegramError
from config import (
    BOT_TOKEN,
    CHANNEL_ID,
    CHANNEL_USERNAME,
    REQUIRED_CHANNELS,
    DISCUSSION_GROUP_ID,
    ADMIN_IDS,
    BANNED_WORDS,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 20
POST_MAP_FILE    = "post_map.pkl"
MUTE_MAP_FILE    = "mute_map.pkl"
BAN_MAP_FILE     = "ban_map.pkl"
STATS_FILE       = "stats.json"

MUTED_PERMS = ChatPermissions(
    can_send_messages        = False,
    can_send_audios          = False,
    can_send_documents       = False,
    can_send_photos          = False,
    can_send_videos          = False,
    can_send_video_notes     = False,
    can_send_voice_notes     = False,
    can_send_polls           = False,
    can_send_other_messages  = False,
    can_add_web_page_previews= False,
)
UNMUTED_PERMS = ChatPermissions(
    can_send_messages        = True,
    can_send_audios          = True,
    can_send_documents       = True,
    can_send_photos          = True,
    can_send_videos          = True,
    can_send_video_notes     = True,
    can_send_voice_notes     = True,
    can_send_polls           = True,
    can_send_other_messages  = True,
    can_add_web_page_previews= True,
)

# ======================================================================
# PERSISTENCE
# ======================================================================
def _load(path):
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    return {}

def _save(path, data):
    try:
        with open(path, "wb") as f:
            pickle.dump(data, f)
    except Exception as e:
        logger.error(f"Gagal simpan {path}: {e}")

def load_post_map(): return _load(POST_MAP_FILE)
def save_post_map(d): _save(POST_MAP_FILE, d)
def load_mute_map(): return _load(MUTE_MAP_FILE)
def save_mute_map(d): _save(MUTE_MAP_FILE, d)
def load_ban_map(): return _load(BAN_MAP_FILE)
def save_ban_map(d): _save(BAN_MAP_FILE, d)

# ======================================================================
# STATS
# ======================================================================
def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "total_messages": 0,
        "messages_today": 0,
        "last_date": "",
        "active_users": {},
        "activity_log": [],
    }

def save_stats(data):
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Gagal simpan stats: {e}")

def record_activity(context, user_id, username, name, action, detail=""):
    stats = context.bot_data.setdefault("stats", load_stats())
    today = datetime.now().strftime("%Y-%m-%d")

    # Reset counter harian kalau beda hari
    if stats.get("last_date") != today:
        stats["messages_today"] = 0
        stats["last_date"] = today

    stats["total_messages"] += 1
    stats["messages_today"] += 1

    # Catat user aktif
    stats["active_users"][str(user_id)] = {
        "name": name,
        "username": username,
        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Log aktivitas (simpan 200 terakhir)
    log_entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "username": username,
        "name": name,
        "action": action,
        "detail": detail[:100],
    }
    stats["activity_log"].append(log_entry)
    if len(stats["activity_log"]) > 200:
        stats["activity_log"] = stats["activity_log"][-200:]

    save_stats(stats)

# ======================================================================
# HELPERS
# ======================================================================
async def check_all_channels(user_id, context):
    not_joined = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(ch["id"], user_id)
            if member.status not in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER):
                not_joined.append(ch["username"])
        except TelegramError:
            not_joined.append(ch["username"])
    return not_joined

def contains_banned_word(text):
    lower = text.lower()
    for word in BANNED_WORDS:
        if word.lower() in lower:
            return word
    return None

def get_cooldown_remaining(user_id, context):
    cooldowns = context.bot_data.setdefault("cooldowns", {})
    remaining = COOLDOWN_SECONDS - (time.time() - cooldowns.get(user_id, 0))
    return max(0, int(remaining))

def set_cooldown(user_id, context):
    context.bot_data.setdefault("cooldowns", {})[user_id] = time.time()

def is_admin(user_id): return user_id in ADMIN_IDS

def is_banned(user_id, context):
    ban_map = context.bot_data.get("ban_map", {})
    return user_id in ban_map

def is_whitelisted(user_id, context):
    return user_id in ADMIN_IDS or user_id in context.bot_data.get("whitelist", set())

def ch_url(username): return f"https://t.me/{username.lstrip('@')}"

def welcome_text(name):
    return (
        f"🎱 Halo {name}, selamat datang di bot WTB milik @grammenfess!\n\n"
        "Disini kamu bisa posting Want To Buy kamu dan akan langsung di-forward ke channel.\n\n"
        "Cukup ketik pesan WTB kamu disini tanpa menggunakan 🎱\n\n"
        "Bot akan otomatis kirim pesan kamu ke channel.\n\n"
        "Selamat berbelanja!"
    )

HELP_TEXT = (
    "🎱 <b>Panduan WTB Bot</b>\n\n"
    "Ketik pesan WTB kamu langsung di chat ini.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "⛔ <b>Dilarang keras:</b>\n"
    "• Kata kasar / SARA / ujaran kebencian\n"
    "• Spam (ada jeda 20 detik antar pesan)\n"
    "• Konten ilegal, penipuan, atau judi\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "📋 <b>Perintah:</b>\n"
    "/start — Mulai bot\n"
    "/help  — Panduan ini"
)

# ======================================================================
# KUNCI UTAMA: cari semua candidate channel_msg_id dari sebuah pesan
# ======================================================================
def get_all_candidate_ids(msg):
    candidates = []
    fo = getattr(msg, "forward_origin", None)
    if fo is not None:
        mid = getattr(fo, "message_id", None)
        if mid and mid not in candidates:
            candidates.append(mid)
    ffmid = getattr(msg, "forward_from_message_id", None)
    if ffmid and ffmid not in candidates:
        candidates.append(ffmid)
    if msg.message_id not in candidates:
        candidates.append(msg.message_id)
    logger.info(f"Candidate IDs dari pesan {msg.message_id}: {candidates}")
    return candidates

def find_post_data(post_map, candidates):
    for cid in candidates:
        if cid in post_map:
            logger.info(f"post_map HIT exact: key={cid}")
            return post_map[cid]
        for offset in (-1, 1):
            key = cid + offset
            if key in post_map:
                logger.info(f"post_map HIT offset {offset:+d}: key={key} dari candidate={cid}")
                return post_map[key]
    return None

def build_comment_link(msg):
    if not msg or not msg.chat:
        return None
    raw = str(msg.chat.id)
    gid = raw[4:] if raw.startswith("-100") else raw.lstrip("-")
    return f"https://t.me/c/{gid}/{msg.message_id}"

# ======================================================================
# KIRIM NOTIFIKASI KE OWNER
# ======================================================================
async def notify_owner(context, user, text, post_link=None):
    """Kirim notifikasi ke semua ADMIN_IDS dengan tombol Ban/Unban."""
    name     = user.first_name or "?"
    username = f"@{user.username}" if user.username else "(no username)"
    preview  = text[:200] + ("..." if len(text) > 200 else "")
    now      = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    notif = (
        "📨 <b>Pesan WTB Baru Masuk!</b>\n\n"
        f"👤 <b>Nama:</b> {name}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"📛 <b>Username:</b> {username}\n"
        f"⏰ <b>Waktu:</b> {now}\n\n"
        f"💬 <b>Isi Pesan:</b>\n<i>{preview}</i>\n"
        f"🔗 <b>Link Pesan:</b> <a href='{post_link}'>Lihat di Channel</a>" if post_link else
        f"💬 <b>Isi Pesan:</b>\n<i>{preview}</i>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚫 Ban User",   callback_data=f"ban:{user.id}:{name}"),
            InlineKeyboardButton("✅ Unban User", callback_data=f"unban:{user.id}:{name}"),
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=notif,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except TelegramError as e:
            logger.warning(f"Gagal kirim notif owner ke {admin_id}: {e}")

# ======================================================================
# /start
# ======================================================================
async def cmd_start(update, context):
    user = update.effective_user
    not_joined = await check_all_channels(user.id, context)
    if not_joined:
        buttons = [
            [InlineKeyboardButton(f"📢 {ch['name']}", url=ch_url(ch['username']))]
            for ch in REQUIRED_CHANNELS if ch["username"] in not_joined
        ]
        buttons.append([InlineKeyboardButton("✅ Sudah Subscribe Semua", callback_data="check_sub_start")])
        await update.message.reply_text(
            "⚠️ <b>Kamu belum subscribe semua channel wajib!</b>\n\nSilahkan subscribe dulu ya, baru bisa kirim WTB 🙏",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        # Beri sesi aktif ke user (1 sesi = 1 pesan)
        context.bot_data.setdefault("active_sessions", set()).add(user.id)
        await update.message.reply_text(welcome_text(user.first_name), parse_mode="HTML")

# ======================================================================
# /help
# ======================================================================
async def cmd_help(update, context):
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

# ======================================================================
# PESAN PRIVATE → kirim ke channel
# ======================================================================
async def handle_message(update, context):
    user    = update.effective_user
    message = update.message
    if not message or not message.text:
        return
    text = message.text.strip()

    # Cek apakah user dibanned
    if is_banned(user.id, context):
        await message.reply_text(
            "🚫 <b>Kamu telah dibanned!</b>\n\nKamu tidak bisa mengirim pesan ke channel ini.",
            parse_mode="HTML"
        )
        return

    # Cek sesi aktif — wajib /start dulu sebelum bisa kirim pesan
    active_sessions = context.bot_data.setdefault("active_sessions", set())
    if user.id not in active_sessions:
        await message.reply_text(
            "⚠️ <b>Ketik /start dulu sebelum kirim pesan ya!</b> 🙏",
            parse_mode="HTML"
        )
        return

    not_joined = await check_all_channels(user.id, context)
    if not_joined:
        buttons = [
            [InlineKeyboardButton(f"📢 {ch['name']}", url=ch_url(ch['username']))]
            for ch in REQUIRED_CHANNELS if ch["username"] in not_joined
        ]
        buttons.append([InlineKeyboardButton("✅ Sudah Subscribe Semua", callback_data="check_sub_private")])
        await message.reply_text(
            "⚠️ <b>Kamu belum subscribe semua channel wajib!</b>\n\nSilahkan subscribe dulu ya, baru bisa kirim WTB 🙏",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    sisa = get_cooldown_remaining(user.id, context)
    if sisa > 0:
        await message.reply_text(
            f"⏳ <b>Sabar dulu ya!</b>\n\nKirim lagi dalam <b>{sisa} detik</b> 🙏",
            parse_mode="HTML")
        return

    if contains_banned_word(text):
        await message.reply_text(
            "🚫 <b>Pesan ditolak!</b>\n\nPesan mengandung kata yang tidak diizinkan.\nEdit dan kirim ulang ya 🙏",
            parse_mode="HTML")
        return

    try:
        sent = await context.bot.send_message(chat_id=CHANNEL_ID, text=f"🎱 {text}")
    except TelegramError as e:
        logger.error(f"Gagal kirim ke channel: {e}")
        await message.reply_text("❌ <b>Ada error!</b>\n\nPesan gagal dikirim. Coba lagi ya 🙏", parse_mode="HTML")
        return

    set_cooldown(user.id, context)

    # Hapus sesi setelah 1 pesan terkirim — user harus /start lagi
    context.bot_data.setdefault("active_sessions", set()).discard(user.id)

    post_map = context.bot_data.setdefault("post_map", load_post_map())
    post_map[sent.message_id] = {
        "user_id"      : user.id,
        "original_text": text,
        "message_id"   : sent.message_id,
    }
    save_post_map(post_map)
    logger.info(f"Post tersimpan: msg_id={sent.message_id} user_id={user.id}")

    # Catat statistik
    record_activity(
        context,
        user_id=user.id,
        username=user.username or "",
        name=user.first_name or "",
        action="kirim_pesan",
        detail=text,
    )

    ch_pure   = CHANNEL_USERNAME.lstrip("@")
    post_link = f"https://t.me/{ch_pure}/{sent.message_id}"

    # Kirim notifikasi ke owner
    await notify_owner(context, user, text, post_link=post_link)
    preview   = text[:80] + ("..." if len(text) > 80 else "")

    await message.reply_text(
        f"🎱 <b>Pesan kamu berhasil dikirim!</b>\n\n📝 <i>{preview}</i>\n\n"
        "Postinganmu udah live di channel! Tunggu seller yang DM kamu ya 🔥",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👀 Lihat Postingan", url=post_link)]]),
    )

# ======================================================================
# GROUP: cek subscribe
# ======================================================================
async def handle_group_message(update, context):
    message = update.message
    if not message or not message.from_user or message.sender_chat:
        return
    user = message.from_user
    if user.is_bot:
        return
    chat_id = message.chat_id
    if DISCUSSION_GROUP_ID and chat_id != DISCUSSION_GROUP_ID:
        return
    if is_whitelisted(user.id, context):
        return
    not_joined = await check_all_channels(user.id, context)
    if not not_joined:
        return

    try:
        await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user.id, permissions=MUTED_PERMS)
        logger.info(f"Muted user {user.id} di group {chat_id}")
    except TelegramError as e:
        logger.warning(f"Gagal mute user {user.id}: {e}")

    name = user.first_name
    not_joined_set = {u.lstrip("@") for u in not_joined}
    ch_list = "\n".join(
        f'  {i+1}. <a href="{ch_url(ch["username"])}">{ch["name"]}</a>'
        for i, ch in enumerate(REQUIRED_CHANNELS)
        if ch["username"].lstrip("@") in not_joined_set
    )
    reply_text = (
        f"⚠️ <b>Hei {name}!</b>\n\nKamu belum subscribe semua channel wajib, "
        f"jadi komentarmu ditahan sementara 🙏\n\n"
        f"📢 <b>Channel yang belum di-join:</b>\n{ch_list}\n\n"
        "Setelah join semua, klik tombol di bawah untuk verifikasi ✅"
    )
    buttons = [
        [InlineKeyboardButton(f"📢 Join {ch['name']}", url=ch_url(ch['username']))]
        for ch in REQUIRED_CHANNELS if ch["username"].lstrip("@") in not_joined_set
    ]
    buttons.append([InlineKeyboardButton(
        "✅ Sudah Subscribe Semua",
        callback_data=f"check_sub_group:{user.id}:{chat_id}:{message.message_id}"
    )])
    try:
        bot_reply = await message.reply_text(
            reply_text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
        )
        mute_map = context.bot_data.setdefault("mute_map", load_mute_map())
        mute_map.setdefault(user.id, []).append({"chat_id": chat_id, "msg_id": bot_reply.message_id})
        save_mute_map(mute_map)
    except TelegramError as e:
        logger.warning(f"Gagal reply: {e}")

# ======================================================================
# GROUP: notifikasi komentar ke sender
# ======================================================================
async def handle_channel_comment(update, context):
    message = update.message
    if not message:
        return
    if not message.reply_to_message:
        return
    if not message.from_user or message.from_user.is_bot:
        return
    if message.sender_chat:
        return
    if DISCUSSION_GROUP_ID and message.chat_id != DISCUSSION_GROUP_ID:
        return

    original = message.reply_to_message
    is_from_channel = (
        original.sender_chat is not None
        or getattr(original, "forward_from_chat", None) is not None
        or getattr(original, "forward_origin", None) is not None
    )
    if not is_from_channel:
        return

    candidates = get_all_candidate_ids(original)
    post_map   = context.bot_data.setdefault("post_map", load_post_map())
    data       = find_post_data(post_map, candidates)

    if not data:
        return

    sender_user_id = data["user_id"]
    commenter      = message.from_user
    if commenter.id == sender_user_id:
        return

    commenter_name = commenter.first_name or "Seseorang"
    commenter_un   = f"@{commenter.username}" if commenter.username else "(no username)"
    comment_text   = message.text or message.caption or ""
    preview        = comment_text[:120] if comment_text else "(mengirim media / stiker)"

    channel_msg_id = data["message_id"]
    ch_pure        = CHANNEL_USERNAME.lstrip("@")
    post_link      = f"https://t.me/{ch_pure}/{channel_msg_id}"
    comment_link   = build_comment_link(message)

    notif_text = (
        "🔔 <b>Ada komentar baru di postinganmu!</b>\n\n"
        f"👤 <b>{commenter_name}</b> {commenter_un} mengomentari pesanmu:\n"
        f"💬 <i>{preview}</i>\n\n"
        "Cek sekarang~ 👇"
    )

    row = [InlineKeyboardButton("📌 Lihat Pesan", url=post_link)]
    if comment_link:
        row.append(InlineKeyboardButton("💬 Lihat Komentar", url=comment_link))

    try:
        await context.bot.send_message(
            chat_id     = sender_user_id,
            text        = notif_text,
            parse_mode  = "HTML",
            reply_markup= InlineKeyboardMarkup([row]),
        )
    except TelegramError as e:
        logger.warning(f"Gagal kirim notif ke {sender_user_id}: {e}")

# ======================================================================
# CALLBACK HANDLER
# ======================================================================
async def callback_handler(update, context):
    query = update.callback_query

    # ── Ban User ──────────────────────────────────────────────────────
    if query.data.startswith("ban:"):
        if not is_admin(query.from_user.id):
            await query.answer("⛔ Kamu bukan admin!", show_alert=True)
            return
        parts   = query.data.split(":", 2)
        user_id = int(parts[1])
        name    = parts[2] if len(parts) > 2 else "?"

        ban_map = context.bot_data.setdefault("ban_map", load_ban_map())
        if user_id in ban_map:
            await query.answer(f"⚠️ User {name} sudah dibanned sebelumnya.", show_alert=True)
            return

        ban_map[user_id] = {
            "name"      : name,
            "banned_at" : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "banned_by" : query.from_user.id,
        }
        save_ban_map(ban_map)
        context.bot_data["ban_map"] = ban_map

        # Notif ke user yang dibanned
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🚫 <b>Kamu telah dibanned!</b>\n\n"
                    "Kamu tidak dapat lagi mengirim pesan ke channel WTB.\n"
                    "Jika ini adalah kesalahan, hubungi admin."
                ),
                parse_mode="HTML",
            )
        except TelegramError:
            pass

        await query.answer(f"✅ User {name} berhasil dibanned!", show_alert=True)
        # Update tombol di pesan notifikasi
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🚫 Sudah Dibanned", callback_data="noop"),
                        InlineKeyboardButton("✅ Unban User", callback_data=f"unban:{user_id}:{name}"),
                    ]
                ])
            )
        except TelegramError:
            pass
        logger.info(f"User {user_id} dibanned oleh admin {query.from_user.id}")
        return

    # ── Unban User ────────────────────────────────────────────────────
    if query.data.startswith("unban:"):
        if not is_admin(query.from_user.id):
            await query.answer("⛔ Kamu bukan admin!", show_alert=True)
            return
        parts   = query.data.split(":", 2)
        user_id = int(parts[1])
        name    = parts[2] if len(parts) > 2 else "?"

        ban_map = context.bot_data.setdefault("ban_map", load_ban_map())
        if user_id not in ban_map:
            await query.answer(f"⚠️ User {name} tidak ada di daftar ban.", show_alert=True)
            return

        ban_map.pop(user_id)
        save_ban_map(ban_map)
        context.bot_data["ban_map"] = ban_map

        # Notif ke user yang di-unban
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "✅ <b>Banned kamu telah dicabut!</b>\n\n"
                    "Kamu sudah bisa kembali mengirim pesan WTB ke channel.\n"
                    "Patuhi peraturan ya! 🙏"
                ),
                parse_mode="HTML",
            )
        except TelegramError:
            pass

        await query.answer(f"✅ User {name} berhasil di-unban!", show_alert=True)
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🚫 Ban User",   callback_data=f"ban:{user_id}:{name}"),
                        InlineKeyboardButton("✅ Sudah Di-unban", callback_data="noop"),
                    ]
                ])
            )
        except TelegramError:
            pass
        logger.info(f"User {user_id} di-unban oleh admin {query.from_user.id}")
        return

    if query.data == "noop":
        await query.answer()
        return

    # ── Check subscribe ───────────────────────────────────────────────
    if query.data == "check_sub_start":
        user = query.from_user
        not_joined = await check_all_channels(user.id, context)
        if not not_joined:
            await query.edit_message_text(welcome_text(user.first_name), parse_mode="HTML")
        else:
            await query.answer(f"❌ Masih belum subscribe:\n{', '.join(not_joined)}\n\nJoin dulu ya!", show_alert=True)
        return

    if query.data == "check_sub_private":
        await query.answer()
        user = query.from_user
        not_joined = await check_all_channels(user.id, context)
        if not not_joined:
            await query.edit_message_text(
                "✅ <b>Mantap! Kamu udah subscribe semua channel!</b>\n\n"
                "Sekarang ketik pesan WTB kamu dan bot langsung forward ke channel~ 🚀",
                parse_mode="HTML",
            )
        else:
            await query.answer(f"❌ Masih belum:\n{', '.join(not_joined)}\n\nJoin dulu ya!", show_alert=True)
        return

    if query.data.startswith("check_sub_group:"):
        parts          = query.data.split(":")
        target_user_id = int(parts[1])
        group_chat_id  = int(parts[2])
        if query.from_user.id != target_user_id:
            await query.answer("⛔ Tombol ini bukan untukmu!", show_alert=True)
            return
        not_joined = await check_all_channels(target_user_id, context)
        if not_joined:
            await query.answer(f"❌ Masih belum:\n{', '.join(not_joined)}\n\nJoin dulu ya!", show_alert=True)
            return
        await query.answer()
        try:
            await context.bot.restrict_chat_member(
                chat_id=group_chat_id, user_id=target_user_id, permissions=UNMUTED_PERMS)
        except TelegramError as e:
            logger.warning(f"Gagal unmute {target_user_id}: {e}")
        mute_map = context.bot_data.get("mute_map", {})
        replies  = mute_map.pop(target_user_id, [])
        save_mute_map(mute_map)
        for entry in replies:
            try:
                await context.bot.delete_message(chat_id=entry["chat_id"], message_id=entry["msg_id"])
            except TelegramError:
                pass
        try:
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"✅ <b>{query.from_user.first_name} sudah diverifikasi!</b>\nSelamat, kamu bebas berkomentar sekarang~ 🎉",
                parse_mode="HTML",
            )
        except TelegramError:
            pass
        return

    if query.data == "help":
        await query.answer()
        await query.message.reply_text(HELP_TEXT, parse_mode="HTML")
        return

    await query.answer()

# ======================================================================
# ADMIN COMMANDS
# ======================================================================
def admin_only(func):
    async def wrapper(update, context):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Kamu bukan admin!")
            return
        await func(update, context)
    return wrapper

@admin_only
async def cmd_stats(update, context):
    """Tampilkan statistik bot."""
    stats    = context.bot_data.get("stats", load_stats())
    post_map = context.bot_data.get("post_map", {})
    ban_map  = context.bot_data.get("ban_map", {})

    total_users  = len(stats.get("active_users", {}))
    total_msg    = stats.get("total_messages", 0)
    today_msg    = stats.get("messages_today", 0)
    total_posts  = len(post_map)
    total_banned = len(ban_map)

    # 5 user paling aktif
    active = stats.get("active_users", {})
    top5   = sorted(active.items(), key=lambda x: x[1].get("last_active", ""), reverse=True)[:5]
    top_text = ""
    for i, (uid, info) in enumerate(top5, 1):
        un = f"@{info.get('username')}" if info.get("username") else info.get("name", "?")
        top_text += f"  {i}. {un} — terakhir: {info.get('last_active', '-')}\n"

    text = (
        "📊 <b>Statistik WTB Bot</b>\n\n"
        f"📨 Total pesan masuk  : <b>{total_msg}</b>\n"
        f"📅 Pesan hari ini     : <b>{today_msg}</b>\n"
        f"👥 Total user aktif   : <b>{total_users}</b>\n"
        f"📌 Total post channel : <b>{total_posts}</b>\n"
        f"🚫 User dibanned      : <b>{total_banned}</b>\n\n"
        f"🏆 <b>User Aktif Terakhir:</b>\n{top_text or '  (belum ada data)'}"
    )
    await update.message.reply_text(text, parse_mode="HTML")

@admin_only
async def cmd_log(update, context):
    """Tampilkan 10 aktivitas terakhir."""
    stats = context.bot_data.get("stats", load_stats())
    logs  = stats.get("activity_log", [])[-10:]

    if not logs:
        await update.message.reply_text("📋 Belum ada log aktivitas.")
        return

    lines = []
    for entry in reversed(logs):
        un      = f"@{entry['username']}" if entry.get("username") else entry.get("name", "?")
        detail  = entry.get("detail", "")[:50]
        lines.append(
            f"⏰ {entry['time']}\n"
            f"👤 {un} (<code>{entry['user_id']}</code>)\n"
            f"💬 {detail}\n"
        )

    text = "📋 <b>Log Aktivitas Terbaru (10 terakhir):</b>\n\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode="HTML")

@admin_only
async def cmd_banned_list(update, context):
    """Tampilkan daftar user yang dibanned."""
    ban_map = context.bot_data.get("ban_map", load_ban_map())

    if not ban_map:
        await update.message.reply_text("✅ Tidak ada user yang dibanned saat ini.")
        return

    lines = []
    for uid, info in ban_map.items():
        name      = info.get("name", "?")
        banned_at = info.get("banned_at", "-")
        lines.append(f"• <b>{name}</b> (<code>{uid}</code>)\n  🕐 {banned_at}")

    text = f"🚫 <b>Daftar User Dibanned ({len(ban_map)}):</b>\n\n" + "\n\n".join(lines)
    await update.message.reply_text(text, parse_mode="HTML")

@admin_only
async def cmd_ban(update, context):
    """Ban user via command: /ban <user_id>"""
    if not context.args:
        await update.message.reply_text("Usage: /ban &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus angka.")
        return

    ban_map = context.bot_data.setdefault("ban_map", load_ban_map())
    if uid in ban_map:
        await update.message.reply_text(f"⚠️ User <code>{uid}</code> sudah dibanned.", parse_mode="HTML")
        return

    ban_map[uid] = {
        "name"      : str(uid),
        "banned_at" : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "banned_by" : update.effective_user.id,
    }
    save_ban_map(ban_map)
    context.bot_data["ban_map"] = ban_map

    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                "🚫 <b>Kamu telah dibanned!</b>\n\n"
                "Kamu tidak dapat lagi mengirim pesan ke channel WTB.\n"
                "Jika ini adalah kesalahan, hubungi admin."
            ),
            parse_mode="HTML",
        )
    except TelegramError:
        pass

    await update.message.reply_text(f"✅ User <code>{uid}</code> berhasil dibanned.", parse_mode="HTML")

@admin_only
async def cmd_unban(update, context):
    """Unban user via command: /unban <user_id>"""
    if not context.args:
        await update.message.reply_text("Usage: /unban &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus angka.")
        return

    ban_map = context.bot_data.setdefault("ban_map", load_ban_map())
    if uid not in ban_map:
        await update.message.reply_text(f"⚠️ User <code>{uid}</code> tidak ada di daftar ban.", parse_mode="HTML")
        return

    ban_map.pop(uid)
    save_ban_map(ban_map)
    context.bot_data["ban_map"] = ban_map

    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                "✅ <b>Banned kamu telah dicabut!</b>\n\n"
                "Kamu sudah bisa kembali mengirim pesan WTB ke channel.\n"
                "Patuhi peraturan ya! 🙏"
            ),
            parse_mode="HTML",
        )
    except TelegramError:
        pass

    await update.message.reply_text(f"✅ User <code>{uid}</code> berhasil di-unban.", parse_mode="HTML")

@admin_only
async def cmd_addban(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /addban &lt;kata&gt;", parse_mode="HTML"); return
    word = " ".join(context.args).lower().strip()
    if word in [w.lower() for w in BANNED_WORDS]:
        await update.message.reply_text(f"⚠️ Kata <code>{word}</code> sudah ada.", parse_mode="HTML"); return
    BANNED_WORDS.append(word)
    await update.message.reply_text(f"✅ Kata <code>{word}</code> ditambahkan.", parse_mode="HTML")

@admin_only
async def cmd_removeban(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /removeban &lt;kata&gt;", parse_mode="HTML"); return
    word = " ".join(context.args).lower().strip()
    lower_list = [w.lower() for w in BANNED_WORDS]
    if word not in lower_list:
        await update.message.reply_text(f"❌ Kata <code>{word}</code> tidak ditemukan.", parse_mode="HTML"); return
    BANNED_WORDS.pop(lower_list.index(word))
    await update.message.reply_text(f"✅ Kata <code>{word}</code> dihapus.", parse_mode="HTML")

@admin_only
async def cmd_listban(update, context):
    if not BANNED_WORDS:
        await update.message.reply_text("📋 Daftar kata terlarang kosong."); return
    words = "\n".join(f"• <code>{w}</code>" for w in sorted(BANNED_WORDS))
    await update.message.reply_text(f"📋 <b>Kata Terlarang ({len(BANNED_WORDS)}):</b>\n\n{words}", parse_mode="HTML")

@admin_only
async def cmd_whitelist(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /whitelist &lt;user_id&gt;", parse_mode="HTML"); return
    try: uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus angka."); return
    context.bot_data.setdefault("whitelist", set()).add(uid)
    await update.message.reply_text(f"✅ User <code>{uid}</code> ditambahkan ke whitelist.", parse_mode="HTML")

@admin_only
async def cmd_unwhitelist(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /unwhitelist &lt;user_id&gt;", parse_mode="HTML"); return
    try: uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus angka."); return
    context.bot_data.get("whitelist", set()).discard(uid)
    await update.message.reply_text(f"✅ User <code>{uid}</code> dihapus dari whitelist.", parse_mode="HTML")

@admin_only
async def cmd_unmute(update, context):
    if not context.args or not DISCUSSION_GROUP_ID:
        await update.message.reply_text(
            "Usage: /unmute &lt;user_id&gt;\nPastikan DISCUSSION_GROUP_ID sudah diisi di config.",
            parse_mode="HTML"); return
    try: uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus angka."); return
    try:
        await context.bot.restrict_chat_member(chat_id=DISCUSSION_GROUP_ID, user_id=uid, permissions=UNMUTED_PERMS)
        await update.message.reply_text(f"✅ User <code>{uid}</code> berhasil di-unmute.", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Gagal unmute: {e}")

@admin_only
async def cmd_broadcast(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /broadcast &lt;pesan&gt;", parse_mode="HTML"); return
    msg      = " ".join(context.args)
    post_map = context.bot_data.get("post_map", {})
    user_ids = {v["user_id"] for v in post_map.values()}
    success  = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 <b>Pengumuman:</b>\n\n{msg}", parse_mode="HTML")
            success += 1
        except TelegramError:
            pass
    await update.message.reply_text(f"✅ Broadcast terkirim ke {success}/{len(user_ids)} user.")

# ======================================================================
# MAIN
# ======================================================================
def main():
    post_map = load_post_map()
    mute_map = load_mute_map()
    ban_map  = load_ban_map()
    stats    = load_stats()
    logger.info(f"Loaded {len(post_map)} posts, {len(mute_map)} muted users, {len(ban_map)} banned users dari disk.")
    logger.info(f"Post map keys: {list(post_map.keys())}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["post_map"] = post_map
    app.bot_data["mute_map"] = mute_map
    app.bot_data["ban_map"]  = ban_map
    app.bot_data["stats"]    = stats

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("stats",       cmd_stats))
    app.add_handler(CommandHandler("log",         cmd_log))
    app.add_handler(CommandHandler("banned_list", cmd_banned_list))
    app.add_handler(CommandHandler("ban",         cmd_ban))
    app.add_handler(CommandHandler("unban",       cmd_unban))
    app.add_handler(CommandHandler("addban",      cmd_addban))
    app.add_handler(CommandHandler("removeban",   cmd_removeban))
    app.add_handler(CommandHandler("listban",     cmd_listban))
    app.add_handler(CommandHandler("whitelist",   cmd_whitelist))
    app.add_handler(CommandHandler("unwhitelist", cmd_unwhitelist))
    app.add_handler(CommandHandler("unmute",      cmd_unmute))
    app.add_handler(CommandHandler("broadcast",   cmd_broadcast))

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_message,
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND,
        handle_group_message,
    ), group=1)

    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.REPLY & ~filters.COMMAND,
        handle_channel_comment,
    ), group=2)

    logger.info("🎱 WTB Bot v5.1 started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
