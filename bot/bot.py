import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

BOT_TOKEN = "7740700463:AAHCcvzIoYWUDc2Oo8f9RbsWl1wBEYEjFOs"
ADMIN_ID = 7872536527

user_data_store = {}
waiting_for_delivery = {}
last_user_activity = {}
spam_count = {}
banned_users = set()
SPAM_COOLDOWN = 3  # seconds
SPAM_LIMIT = 3

logging.basicConfig(level=logging.INFO)

def is_spamming(user_id):
    if user_id == ADMIN_ID or user_id in banned_users:
        return False
    now = time.time()
    last_time = last_user_activity.get(user_id, 0)

    if now - last_time < SPAM_COOLDOWN:
        spam_count[user_id] = spam_count.get(user_id, 0) + 1
        if spam_count[user_id] >= SPAM_LIMIT:
            banned_users.add(user_id)
        return True

    last_user_activity[user_id] = now
    spam_count[user_id] = 0
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        if user_id in banned_users:
            return
        if is_spamming(user_id):
            return await update.message.reply_text("⏳ Please wait before sending again.")
        
        # Try sending the image with a full path for better clarity
        #image_path = "qrcode.png"
        try:
            await update.message.reply_photo(open('bot/qrcode.png', 'rb'))
        except Exception as e:
            logging.error(f"Error sending photo: {e}")
            return await update.message.reply_text("❌ Failed to send the photo. Please try again later.")
        
        await update.message.reply_text("Welcome! Please send your product ID.")
    except Exception as e:
        logging.error(f"Error in /start: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        if user_id in banned_users:
            return
        if is_spamming(user_id):
            return await update.message.reply_text("⏳ Please wait before sending again.")

        text = update.message.text
        
        # Check if the product ID is valid
        valid_product_ids = ["ZERO001", "ZERO002", "ZERO003"]
        if text not in valid_product_ids:
            await update.message.reply_text("❌ Unknown product ID. Please send a valid product ID.")
            return

        user_data_store[user_id] = {'product_id': text}
        await update.message.reply_text("Thanks! Now send your receipt (PDF or image).")
    except Exception as e:
        logging.error(f"Error in handle_text: {e}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        if user_id in banned_users:
            return
        if is_spamming(user_id):
            return await update.message.reply_text("⏳ Please wait before sending again.")

        if user_id not in user_data_store or 'product_id' not in user_data_store[user_id]:
            await update.message.reply_text("Please send your product ID first.")
            return

        file_id = None
        file_type = None

        if update.message.document:
            file_id = update.message.document.file_id
            file_type = 'document'
        elif update.message.photo:
            file_id = update.message.photo[-1].file_id
            file_type = 'photo'
        else:
            await update.message.reply_text("Only PDF or image is supported.")
            return

        user_data_store[user_id]['receipt_id'] = file_id
        user_data_store[user_id]['receipt_type'] = file_type

        keyboard = InlineKeyboardMarkup([[ 
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{user_id}")
        ]])

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🛒 User {user_id} wants to buy:\n📦 Product ID: {user_data_store[user_id]['product_id']}"
        )

        if file_type == 'document':
            await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, reply_markup=keyboard)
        else:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=file_id, reply_markup=keyboard)

        await update.message.reply_text("Your request has been sent to the admin.")
    except Exception as e:
        logging.error(f"Error in handle_file: {e}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        action, target_user_id = query.data.split(":")
        target_user_id = int(target_user_id)

        if action == "approve":
            waiting_for_delivery[ADMIN_ID] = target_user_id
            await context.bot.send_message(chat_id=target_user_id, text="✅ Your purchase has been approved!")
            await context.bot.send_message(chat_id=ADMIN_ID, text="Now send the product file (PDF or image) to deliver to the user.")
        elif action == "reject":
            await context.bot.send_message(chat_id=target_user_id, text="❌ Your purchase has been rejected.")

        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logging.error(f"Error in handle_callback: {e}")

async def handle_admin_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.from_user.id != ADMIN_ID:
            return

        if ADMIN_ID not in waiting_for_delivery:
            await update.message.reply_text("No user waiting for delivery.")
            return

        target_user_id = waiting_for_delivery.pop(ADMIN_ID)

        if update.message.document:
            await context.bot.send_document(chat_id=target_user_id, document=update.message.document.file_id)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=target_user_id, photo=update.message.photo[-1].file_id)
        elif update.message.text:
            await context.bot.send_message(chat_id=target_user_id, text=update.message.text)
        else:
            await update.message.reply_text("Unsupported file type.")
            return

        await update.message.reply_text("✅ Product delivered to the user.")
    except Exception as e:
        logging.error(f"Error in handle_admin_delivery: {e}")

def main():
    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
        app.add_handler(CallbackQueryHandler(handle_callback))
        app.add_handler(MessageHandler(filters.ALL, handle_admin_delivery), group=1)

        print("🤖 Bot is running...")
        app.run_polling()
    except Exception as e:
        logging.error(f"Error in main: {e}")

if __name__ == "__main__":
    main()
