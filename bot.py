import os
import requests
import pandas as pd
import numpy as np
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, Filters, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler

# -------------------- ENV VARIABLES --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ACCESS_CODES = os.getenv("ACCESS_CODES", "").split(",")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")

# -------------------- STATES --------------------
ASK_CODE = 1
SETTINGS = 2

# -------------------- USERS --------------------
authorized_users = set()
user_settings = {}  # user_id -> {"symbols": [], "timeframe": "5min"}

# -------------------- DEFAULTS --------------------
DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD"]
DEFAULT_TIMEFRAME = "5min"

# -------------------- SCHEDULER --------------------
scheduler = BackgroundScheduler()

# -------------------- HELPER FUNCTIONS --------------------

def check_access_code(code: str):
    return code in ACCESS_CODES

def fetch_ohlc(symbol: str, interval="5min"):
    from_symbol = symbol[:3]
    to_symbol = symbol[3:]
    url = f"https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={from_symbol}&to_symbol={to_symbol}&interval={interval}&apikey={ALPHA_VANTAGE_KEY}&outputsize=compact"
    try:
        r = requests.get(url).json()
        data = r.get(f"Time Series FX ({interval})", {})
        if not data:
            return None
        df = pd.DataFrame(data).T.astype(float)
        df = df.sort_index()
        return df
    except:
        return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def high_probability_signal(symbol):
    df = fetch_ohlc(symbol)
    if df is None or df.empty:
        return None

    close = df['4. close']
    latest_price = close.iloc[-1]

    # Indicators
    rsi = calculate_rsi(close).iloc[-1]
    ma = close.rolling(14).mean().iloc[-1]
    macd, macd_signal = calculate_macd(close)
    macd_latest = macd.iloc[-1]
    macd_sig_latest = macd_signal.iloc[-1]

    # Strategy: BUY if RSI < 30, price > MA, MACD above signal; SELL if RSI > 70, price < MA, MACD below signal
    if rsi < 30 and latest_price > ma and macd_latest > macd_sig_latest:
        return "BUY"
    elif rsi > 70 and latest_price < ma and macd_latest < macd_sig_latest:
        return "SELL"
    else:
        return "WAIT"

# -------------------- HANDLERS --------------------

def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("🔑 Access Bot", callback_data="access")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Welcome to Pro Forex Bot! Press below to access:", reply_markup=reply_markup)

def access_button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.message.reply_text("Please enter your access code:")
    return ASK_CODE

def ask_code(update: Update, context: CallbackContext):
    code = update.message.text.strip()
    user_id = update.message.from_user.id

    if check_access_code(code):
        authorized_users.add(user_id)
        user_settings[user_id] = {"symbols": DEFAULT_SYMBOLS.copy(), "timeframe": DEFAULT_TIMEFRAME}
        update.message.reply_text("✅ Access granted! Use the buttons below.")
        send_main_menu(update)
    else:
        update.message.reply_text(f"❌ Invalid code! Contact {ADMIN_USERNAME} to get a valid code.")
    return ConversationHandler.END

def send_main_menu(update):
    keyboard = [
        [InlineKeyboardButton("📊 Get Signal", callback_data="get_signal")],
        [InlineKeyboardButton("⚙ Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Main Menu:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if query.data == "get_signal":
        if user_id not in authorized_users:
            query.message.reply_text(f"❌ Access required. Contact {ADMIN_USERNAME}")
            return
        send_signals(query, user_id)

    elif query.data == "settings":
        if user_id not in authorized_users:
            query.message.reply_text(f"❌ Access required. Contact {ADMIN_USERNAME}")
            return
        keyboard = [[InlineKeyboardButton(sym, callback_data=f"toggle_{sym}")] for sym in DEFAULT_SYMBOLS]
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="back_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.message.reply_text("Select symbols to track:", reply_markup=reply_markup)

    elif query.data.startswith("toggle_"):
        sym = query.data.replace("toggle_", "")
        if sym in user_settings[user_id]["symbols"]:
            user_settings[user_id]["symbols"].remove(sym)
        else:
            user_settings[user_id]["symbols"].append(sym)
        query.message.reply_text(f"✅ Updated symbols: {user_settings[user_id]['symbols']}")

    elif query.data == "back_menu":
        send_main_menu(query)

def send_signals(query, user_id):
    symbols = user_settings[user_id]["symbols"]
    msg = "📊 Current Signals:\n"
    for sym in symbols:
        sig = high_probability_signal(sym)
        if sig:
            msg += f"{sym}: {sig}\n"
    query.message.reply_text(msg)

# -------------------- AUTO SIGNAL --------------------

def auto_signal():
    for user_id in authorized_users:
        symbols = user_settings.get(user_id, {}).get("symbols", DEFAULT_SYMBOLS)
        for sym in symbols:
            sig = high_probability_signal(sym)
            if sig in ["BUY", "SELL"]:
                try:
                    context.bot.send_message(chat_id=user_id, text=f"⏰ ALERT: {sym} signal available in 1 minute: {sig}")
                except Exception as e:
                    print("Failed to send auto signal:", e)

# -------------------- MAIN --------------------

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(access_button, pattern="^access$")],
        states={ASK_CODE: [MessageHandler(Filters.text & ~Filters.command, ask_code)]},
        fallbacks=[]
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(button_handler))

    # Auto notifications every minute
    scheduler.add_job(lambda: auto_signal(), 'interval', minutes=1)
    scheduler.start()

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()