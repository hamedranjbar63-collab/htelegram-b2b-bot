====================== main.py ======================
# ================= CONFIG =================
import os
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Railway Variable

ADMINS = ["hamed_r_k", "rangbaramin", "amirrangbar1369"]

# ================= IMPORTS =================
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import sqlite3
from difflib import get_close_matches
from PIL import Image, ImageDraw, ImageFont

# ================= DATABASE =================
conn = sqlite3.connect("data.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS products(
 code TEXT PRIMARY KEY,
 name TEXT,
 unit TEXT,
 price INTEGER,
 active INTEGER DEFAULT 1
)""")

cur.execute("""
CREATE TABLE IF NOT EXISTS orders(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 chat_id INTEGER,
 total INTEGER DEFAULT 0
)""")

cur.execute("""
CREATE TABLE IF NOT EXISTS order_items(
 order_id INTEGER,
 code TEXT,
 qty INTEGER,
 price INTEGER,
 total INTEGER
)""")

conn.commit()

# ================= UTIL =================
def get_order(chat_id):
    cur.execute(
        "SELECT id FROM orders WHERE chat_id=? ORDER BY id DESC LIMIT 1",
        (chat_id,)
    )
    r = cur.fetchone()
    if r:
        return r[0]
    cur.execute("INSERT INTO orders(chat_id,total) VALUES (?,0)", (chat_id,))
    conn.commit()
    return cur.lastrowid

# ================= INVOICE =================
def make_invoice(order_id, items, total):
    img = Image.new("RGB", (900, 1200), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    y = 40
    d.text((30, y), f"Invoice #{order_id}", font=font, fill="black")
    y += 40

    for i, it in enumerate(items, 1):
        d.text(
            (30, y),
            f"{i}. {it['name']} | {it['qty']} {it['unit']} × {it['price']}",
            font=font,
            fill="black"
        )
        y += 30

    y += 30
    d.text((30, y), f"TOTAL: {total} IRR", font=font, fill="black")

    path = f"invoice_{order_id}.png"
    img.save(path)
    return path

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🛒 ثبت سفارش", callback_data="order")],
        [InlineKeyboardButton("🔍 جستجوی کالا", callback_data="search")],
        [InlineKeyboardButton("🎙 جستجوی صوتی", callback_data="voice")],
        [InlineKeyboardButton("👁 پیش‌نمایش فاکتور", callback_data="preview")]
    ]
    await update.message.reply_text(
        "به سامانه سفارش‌گیری B2B خوش آمدید",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ================= SEARCH TEXT =================
async def search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    cur.execute("SELECT code,name,unit,price FROM products WHERE active=1")
    products = cur.fetchall()

    names = [p[1] for p in products]
    matches = get_close_matches(text, names, n=5, cutoff=0.3)

    if not matches:
        await update.message.reply_text("❌ کالایی پیدا نشد")
        return

    msg = "نتایج:\n\n"
    for m in matches:
        for p in products:
            if p[1] == m:
                msg += f"▪ {p[1]} ({p[2]}) | {p[3]} ریال\n"

    msg += "\nکد کالا + تعداد بفرست (مثال: 1001 5)"
    await update.message.reply_text(msg)

# ================= VOICE =================
async def voice_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙 ویس دریافت شد\n"
        "⛔ تبدیل صوت به متن هنوز فعال نشده\n"
        "✔️ آماده اتصال به Whisper / Google STT"
    )

# ================= ADD ITEM =================
async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        code, qty = update.message.text.split()
        qty = int(qty)
    except:
        return

    cur.execute("SELECT name,unit,price FROM products WHERE code=?", (code,))
    p = cur.fetchone()
    if not p:
        await update.message.reply_text("❌ کد نامعتبر")
        return

    order_id = get_order(update.effective_chat.id)
    total = qty * p[2]

    cur.execute(
        "INSERT INTO order_items VALUES (?,?,?,?,?)",
        (order_id, code, qty, p[2], total)
    )
    cur.execute(
        "UPDATE orders SET total = total + ? WHERE id=?",
        (total, order_id)
    )
    conn.commit()

    await update.message.reply_text(f"✅ {p[0]} اضافه شد")

# ================= PREVIEW =================
async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cur.execute(
        "SELECT id,total FROM orders WHERE chat_id=? ORDER BY id DESC LIMIT 1",
        (chat_id,)
    )
    o = cur.fetchone()
    if not o:
        await update.callback_query.message.reply_text("سبد خالی است")
        return

    cur.execute("""
    SELECT p.name,p.unit,oi.qty,oi.price
    FROM order_items oi
    JOIN products p ON p.code=oi.code
    WHERE oi.order_id=?
    """, (o[0],))

    rows = cur.fetchall()
    items = [{"name": r[0], "unit": r[1], "qty": r[2], "price": r[3]} for r in rows]

    img = make_invoice(o[0], items, o[1])
    await context.bot.send_photo(chat_id=chat_id, photo=open(img, "rb"))

# ================= CALLBACK =================
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    await update.callback_query.answer()

    if data == "search":
        await update.callback_query.message.reply_text("نام کالا را بنویس")
    elif data == "voice":
        await update.callback_query.message.reply_text("ویس بفرست")
    elif data == "preview":
        await preview(update, context)

# ================= APP =================
app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(callback))
app.add_handler(MessageHandler(filters.Regex(r"^\d+\s+\d+$"), add_item))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_text))
app.add_handler(MessageHandler(filters.VOICE, voice_search))

print("BOT STARTED")
app.run_polling()
