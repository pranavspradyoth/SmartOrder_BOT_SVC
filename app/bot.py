import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application,MessageHandler,filters, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
import pytz
import os
import json
from dotenv import load_dotenv
load_dotenv()

# Replace with your Telegram Bot Token from BotFather
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Admin Backend Base URL
ADMIN_BACKEND_URL = os.getenv("ADMIN_SVC")  # Flask admin backend running locally

# Store user orders in memory (for demo) → in production, keep in DB
user_orders = {}
user_cart = {}
# Start command → show welcome + fetch menu
async def hi_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return  # only allow text messages here

    text = update.message.text.strip().lower()
    if text in ["hi", "hey", "/start"]:
        response = requests.get(f"{ADMIN_BACKEND_URL}/categories")
        categories = response.json()

        keyboard = [
            [InlineKeyboardButton(cat['name'], callback_data=f"cat_{cat['name']}")]
            for cat in categories
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "👋 Welcome to Canteen Bot!\nSelect a category:",
            reply_markup=reply_markup
        )

async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.split("_", 1)[1]
    print("llllllll",category)
    response = requests.get(f"{ADMIN_BACKEND_URL}/itemsperCat?category={category}")
    items = response.json()
    print("iiiiii",items)
    if not items:
        await query.edit_message_text(text=f"No items available in {category}.")
        return

    keyboard = []
    for item in items:
        if item.get("available", True):
            keyboard.append([InlineKeyboardButton(f"{item['name']} - ₹{item['price']}", callback_data=f"add_{item['_id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=f"📋 Menu for *{category}*:\n(Select items to add to cart)", reply_markup=reply_markup, parse_mode="Markdown")

# Add item → ask quantity
async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = query.data.split("_")[1]
    print("iiiiiiid",item_id,type(item_id))
    response = requests.get(f"{ADMIN_BACKEND_URL}/item?item_id={item_id}")
    item = response.json()

    # Save item temporarily to wait for quantity
    context.user_data["pending_item"] = item
    await query.edit_message_text(text=f"🛒 How many *{item['name']}* do you want?\n(Reply with a number)", parse_mode="Markdown")

# Handle quantity message
async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_item" not in context.user_data:
        return

    try:
        qty = int(update.message.text.strip())
        if qty <= 0:
            await update.message.reply_text("⚠️ Quantity must be at least 1.")
            return
    except:
        await update.message.reply_text("⚠️ Please enter a valid number.")
        return

    item = context.user_data.pop("pending_item")
    user_id = update.message.from_user.id

    if user_id not in user_cart:
        user_cart[user_id] = []

    user_cart[user_id].append({
        "item_id": item["_id"],
        "name": item["name"],
        "qty": str(qty),
        "price": item["price"]
    })

    total = sum(int(x["qty"]) * int(x["price"]) for x in user_cart[user_id])

    # show confirm/add more/cancel buttons
    keyboard = [
        [InlineKeyboardButton("✅ Confirm Order", callback_data="confirm_order")],
        [InlineKeyboardButton("➕ Add More Items", callback_data="back_to_categories")],
        [InlineKeyboardButton("❌ Cancel Order", callback_data="cancel_order")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🛒 Added {qty} x {item['name']}.\n\nCurrent Cart:\n" +
        "\n".join([f"{i['qty']} x {i['name']} (₹{int(i['qty'])*int(i['price'])})" for i in user_cart[user_id]]) +
        f"\n\n💰 Total: ₹{total}",
        reply_markup=reply_markup
    )
# Confirm order → send to backend
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in user_cart or not user_cart[user_id]:
        await query.edit_message_text("⚠️ Your cart is empty.")
        return

    order_data = {
        "user_id": user_id,
        "items": user_cart[user_id],
        "status": "Received",
        "total": sum(int(x["qty"]) * int(x["price"]) for x in user_cart[user_id])
    }
    print("oooooooooo",order_data)
    response = requests.post(f"{ADMIN_BACKEND_URL}/orders", json=order_data)

    if response.status_code == 200:
        order_id = response.json()["orderId"]
        user_orders[user_id] = order_id
        user_cart[user_id] = []  # clear cart
        await query.edit_message_text("✅ Order placed! We'll notify you about updates. Your Order Id is " + str(order_id))
    else:
        await query.edit_message_text("❌ Failed to place order. Try again later.")

# Cancel order
async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_cart[user_id] = []
    await query.edit_message_text("❌ Your cart has been cleared.")

# Go back to categories
async def back_to_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    response = requests.get(f"{ADMIN_BACKEND_URL}/categories")
    categories = response.json()

    keyboard = [
        [InlineKeyboardButton(cat['name'], callback_data=f"cat_{cat['name']}")]
        for cat in categories
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text="📋 Select a category:",
        reply_markup=reply_markup
    )

# Poll order status
# async def poll_order_status(app):
#      while True:
#         print("Polling order status...,uer_orders:",user_orders)
#         for user_id, order_id in list(user_orders.items()):
#             try:
#                 response = requests.get(f"{ADMIN_BACKEND_URL}/order?order_id={order_id}")
#                 if response.status_code == 200:
#                     order = response.json()
#                     status = order.get("status")

#                     if status in ["Preparing", "Ready", "Served"]:
#                         await app.bot.send_message(
#                             chat_id=user_id,
#                             text=f"🍴 Your order status: *{status}*",
#                             parse_mode="Markdown"
#                         )

#                         if status == "Served":
#                             # Clear user tracking once order is completed
#                             user_orders.pop(user_id, None)
#                             user_cart[user_id] = []  # empty cart
#                             await app.bot.send_message(
#                                 chat_id=user_id,
#                                 text="✅ Your order is complete!\nType 'hi' to start a new order."
#                             )

#             except Exception as e:
#                 print(f"⚠️ Error checking order status for user {user_id}: {e}")

#         await asyncio.sleep(5)

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(MessageHandler(filters.Regex("(?i)^(hi|hey)$") & ~filters.COMMAND, hi_message))
    application.add_handler(CallbackQueryHandler(category_selected, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(add_item, pattern="^add_"))
    application.add_handler(MessageHandler(filters.Regex("^[0-9]+$"), handle_quantity))
    application.add_handler(CallbackQueryHandler(confirm_order, pattern="^confirm_order"))
    application.add_handler(CallbackQueryHandler(cancel_order, pattern="^cancel_order"))
    application.add_handler(CallbackQueryHandler(back_to_categories, pattern="^back_to_categories"))

    # application.job_queue.run_once(lambda ctx: asyncio.create_task(poll_order_status(application)), 0)

    print("🤖 Telegram Bot running...")
    application.run_polling()
if __name__ == "__main__":
    main()
