import os
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("MARKET_API_KEY")

SYMBOL = "EUR/USD"
INTERVAL = "5min"

# ================= DATA FETCH =================
def get_market_data():
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&outputsize=100&apikey={API_KEY}"
    r = requests.get(url).json()

    if "values" not in r:
        return None

    df = pd.DataFrame(r["values"])
    df = df.astype(float)
    df = df.iloc[::-1]
    return df

# ================= ANALYSIS =================
def analyze_market():
    df = get_market_data()
    if df is None:
        return "⚠️ Market data unavailable"

    rsi = RSIIndicator(df["close"], window=14).rsi().iloc[-1]
    macd = MACD(df["close"])
    macd_val = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    ema = EMAIndicator(df["close"], window=50).ema_indicator().iloc[-1]
    price = df["close"].iloc[-1]

    signal = "Neutral"

    if rsi < 30 and macd_val > macd_signal and price > ema:
        signal = "📈 STRONG BUY SETUP"
    elif rsi > 70 and macd_val < macd_signal and price < ema:
        signal = "📉 STRONG SELL SETUP"

    return f"""
📊 *Market Analysis ({SYMBOL})*

Price: {price:.5f}
RSI: {rsi:.2f}
EMA Trend: {'Uptrend' if price > ema else 'Downtrend'}
MACD: {'Bullish' if macd_val > macd_signal else 'Bearish'}

🔥 Signal: *{signal}*
"""

# ================= BUTTONS =================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Get Signal Now", callback_data="signal")],
        [InlineKeyboardButton("🔁 Start Auto Alerts", callback_data="alerts")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *Pro Forex Analysis Bot*\nChoose an option:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "signal":
        result = analyze_market()
        await query.message.reply_text(result, parse_mode="Markdown")

    elif query.data == "alerts":
        context.job_queue.run_repeating(send_auto_signal, interval=60, first=5, chat_id=query.message.chat_id)
        await query.message.reply_text("🔔 Auto-alerts started! I’ll notify when strong setup appears.")

# ================= AUTO SIGNAL =================
async def send_auto_signal(context: ContextTypes.DEFAULT_TYPE):
    analysis = analyze_market()
    if "STRONG" in analysis:
        await context.bot.send_message(context.job.chat_id, f"⚠️ Setup forming!\n{analysis}", parse_mode="Markdown")

# ================= MAIN =================
app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))

print("Bot running...")
app.run_polling()