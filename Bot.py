"""
Moliya Nazorati Telegram Bot
=============================
Foydalanuvchilarga kirim va chiqimlarini kuzatishga yordam beradi.
"""

import logging
import os
import re
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.path.join(os.path.dirname(__file__), "finance.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def add_transaction(user_id: int, amount: float, category: str, ttype: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO transactions (user_id, amount, category, type, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, ttype, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_balance(user_id: int) -> float:
    conn = get_db()
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) -
            COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS balance
        FROM transactions WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    conn.close()
    return row["balance"]


def get_monthly_report(user_id: int):
    conn = get_db()
    month_start = datetime.now().strftime("%Y-%m")
    rows = conn.execute(
        """
        SELECT category, type, SUM(amount) as total
        FROM transactions
        WHERE user_id = ? AND created_at LIKE ?
        GROUP BY category, type
        ORDER BY total DESC
        """,
        (user_id, f"{month_start}%"),
    ).fetchall()
    conn.close()
    return rows


def get_history(user_id: int, limit: int = 10):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT amount, category, type, created_at
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return rows


TRANSACTION_PATTERN = re.compile(r"^([+-])\s*(\d+(?:[.,]\d+)?)\s*(.*)$")

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("💰 Balans"), KeyboardButton("📊 Hisobot")],
        [KeyboardButton("🕒 Tarix"), KeyboardButton("❓ Yordam")],
    ],
    resize_keyboard=True,
)


def format_money(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Assalomu alaykum! 👋\n\n"
        "Men sizning shaxsiy moliya yordamchingizman.\n\n"
        "Kirim yoki chiqimni qo'shish uchun shunchaki yozing:\n"
        "  +500000 maosh   — kirim qo'shish\n"
        "  -30000 taxi     — chiqim qo'shish\n\n"
        "Quyidagi tugmalardan ham foydalanishingiz mumkin 👇",
        reply_markup=MAIN_KEYBOARD,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Qo'llanma:\n\n"
        "➕ Kirim qo'shish: +summa izoh\n"
        "   Masalan: +1000000 maosh\n\n"
        "➖ Chiqim qo'shish: -summa izoh\n"
        "   Masalan: -25000 ovqat\n\n"
        "/balance — joriy balansni ko'rish\n"
        "/report — shu oylik hisobot\n"
        "/history — so'nggi 10 ta amaliyot"
    )


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    emoji = "✅" if balance >= 0 else "⚠️"
    await update.message.reply_text(
        f"{emoji} Joriy balansingiz: <b>{format_money(balance)}</b> so'm",
        parse_mode="HTML",
    )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_monthly_report(user_id)

    if not rows:
        await update.message.reply_text("Bu oy uchun hali ma'lumot yo'q.")
        return

    income_lines, expense_lines = [], []
    total_income, total_expense = 0, 0

    for row in rows:
        line = f"  • {row['category']}: {format_money(row['total'])} so'm"
        if row["type"] == "income":
            income_lines.append(line)
            total_income += row["total"]
        else:
            expense_lines.append(line)
            total_expense += row["total"]

    text = f"📊 <b>{datetime.now().strftime('%Y-%m')} oylik hisobot</b>\n\n"
    if income_lines:
        text += "🟢 Kirimlar:\n" + "\n".join(income_lines) + "\n\n"
    if expense_lines:
        text += "🔴 Chiqimlar:\n" + "\n".join(expense_lines) + "\n\n"

    text += f"Jami kirim: {format_money(total_income)} so'm\n"
    text += f"Jami chiqim: {format_money(total_expense)} so'm\n"
    text += f"Sof qoldiq: {format_money(total_income - total_expense)} so'm"

    await update.message.reply_text(text, parse_mode="HTML")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_history(user_id)

    if not rows:
        await update.message.reply_text("Hali amaliyotlar yo'q.")
        return

    lines = ["🕒 <b>So'nggi amaliyotlar:</b>\n"]
    for row in rows:
        sign = "+" if row["type"] == "income" else "-"
        date = datetime.fromisoformat(row["created_at"]).strftime("%d.%m %H:%M")
        lines.append(f"{sign}{format_money(row['amount'])} — {row['category']} ({date})")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "💰 Balans":
        return await balance_command(update, context)
    if text == "📊 Hisobot":
        return await report_command(update, context)
    if text == "🕒 Tarix":
        return await history_command(update, context)
    if text == "❓ Yordam":
        return await help_command(update, context)

    match = TRANSACTION_PATTERN.match(text)
    if not match:
        await update.message.reply_text(
            "Tushunmadim 🤔\n"
            "Masalan shunday yozing:\n"
            "+500000 maosh\n"
            "-30000 taxi"
        )
        return

    sign, amount_str, category = match.groups()
    amount = float(amount_str.replace(",", "."))
    category = category.strip() or "Boshqa"
    ttype = "income" if sign == "+" else "expense"

    add_transaction(update.effective_user.id, amount, category, ttype)

    emoji = "🟢" if ttype == "income" else "🔴"
    label = "Kirim" if ttype == "income" else "Chiqim"
    balance = get_balance(update.effective_user.id)

    await update.message.reply_text(
        f"{emoji} {label} qo'shildi: {format_money(amount)} so'm ({category})\n"
        f"💰 Joriy balans: {format_money(balance)} so'm"
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi! .env faylida BOT_TOKEN=... qiymatini kiriting."
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
