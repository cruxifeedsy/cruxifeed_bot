import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, ConversationHandler
from apscheduler.schedulers.background import BackgroundScheduler
import time

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ACCESS_CODES = os.getenv("ACCESS_CODES", "").split(",")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")

# State for ConversationHandler
ASK_CODE = 1

# Users who already accessed the bot
authorized_users = set()

# List of symbols to track
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD"]

# Scheduler for auto notifications
scheduler = BackgroundScheduler()

# --- Helper functions ---
def check_access_code(user_code: str):
    return user_code in ACCESS_CODES

def fetch_forex(symbol: str):
    # Using Alpha Vantage free API
    url = f"https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={symbol[:3]}&to_symbol={symbol[3:]}&interval=5min&apikey={ALPHA_VANTAGE_KEY}"
    try:
        r = requests.get(url).json()
        data = r.get("Time Series FX (5min)", {})
        if not data:
            return None
        latest_time = list(data.keys())[0]
        latest_price = float(data[latest_time]["1. open"])
        return latest_price
    except:
        return None

def calculate_signal(symbol: str):
    # Dummy logic for demo: you can replace with RSI, MACD, MA strategy
    price = fetch_forex(symbol)
    if price is None:
        return None
    # Simple example: price > some threshold → BUY, else SELL
    # Replace this with real strategy later
    if price % 2 > 1:  # dummy condition
        return "BUY"
    else:
        return "SELL"

# --- Command handlers ---
def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("Access Bot", callback_data="access")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Welcome! Press below to access the bot.", reply_markup=reply_markup)

def access_button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.message.reply_text("Please enter your access code:")
    return ASK_CODE

def ask_code(update: Update, context: CallbackContext):
    user_code = update.message.text.strip()
    user_id = update.message.from_user.id

    if check_access_code(user_code):
        authorized_users.add(user_id)
        update.message.reply_text("✅ Access granted! You can now use /signal to get forex signals.")
    else:
        update.message.reply_text(f"❌ Invalid code! Contact {ADMIN_USERNAME} to get a valid code.")
    return ConversationHandler.END

def signal_command(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in authorized_users:
        update.message.reply_text(f"❌ You need access first. Contact {ADMIN_USERNAME}")
        return

    message = "📊 Current Forex Signals:\n"
    for sym in SYMBOLS:
        sig = calculate_signal(sym)
        if sig:
            message += f"{sym}: {sig}\n"
    update.message.reply_text(message)

# --- Auto notification function ---
def auto_signal():
    for user_id in authorized_users:
        for sym in SYMBOLS:
            sig = calculate_signal(sym)
            if sig == "BUY" or sig == "SELL":
                try:
                    context.bot.send_message(chat_id=user_id, text=f"⏰ ALERT: {sym} signal available in 1 minute: {sig}")
                except Exception as e:
                    print("Failed to send auto signal:", e)

# --- Main ---
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Conversation handler for access code
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(access_button, pattern="^access$")],
        states={
            ASK_CODE: [CommandHandler("cancel", lambda u,c: ConversationHandler.END),
                       MessageHandler(None, ask_code)]
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("signal", signal_command))

    # Start the scheduler for auto signals every 1 minute
    scheduler.add_job(lambda: auto_signal(), 'interval', minutes=1)
    scheduler.start()

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()