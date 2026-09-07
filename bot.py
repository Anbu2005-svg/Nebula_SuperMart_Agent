import os
import asyncio
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from db.seed import seed_database
from agent.control_loop import run_agent_turn, clear_conversation
from skills.documents import generate_invoice_pdf, generate_analysis_deck
from skills.auth import (
    is_user_authenticated,
    register_shop,
    login_shop,
    get_user_session,
    logout_user_session
)

# User login/signup state machine: {telegram_id: {"step": "choice"|"signup_name"|"signup_pwd"|"signup_meta"|"login_name"|"login_pwd", "data": {}}}
USER_AUTH_STATE: Dict[str, Dict[str, Any]] = {}

def get_auth_choice_keyboard():
    """Returns New Shop (Sign Up) vs Existing Shop (Log In) inline choice keyboard buttons."""
    keyboard = [
        [KeyboardButton(text="🆕 New Shop (Sign Up)")],
        [KeyboardButton(text="🔑 Existing Shop (Log In)")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — starts fresh conversation context for user."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    chat_id = update.effective_chat.id
    clear_conversation(chat_id)
    USER_AUTH_STATE.pop(telegram_id, None)
    
    session = get_user_session(telegram_id)
    if not session:
        auth_msg = (
            "🏬 *Welcome to Supermarket Ops Agent!*\n\n"
            "To get started, please select whether you want to register a **New Shop** or log into an **Existing Shop**."
        )
        await update.message.reply_text(auth_msg, parse_mode="Markdown", reply_markup=get_auth_choice_keyboard())
        return

    welcome_text = (
        f"🛒 *Welcome back to {session['shop_name']}!*\n\n"
        f"📍 Address: {session['shop_address'] or 'Not specified'}\n"
        f"📑 GSTIN: {session['shop_gstin'] or 'Not specified'}\n\n"
        "You can manage your supermarket using natural language or slash commands:\n\n"
        "• `/stock` — View all products & inventory stock\n"
        "• `/lowstock` — View low stock reorder items\n"
        "• `/bill` — Create a bill (e.g. `/bill 2 sugar, 4 Maggi, UPI`)\n"
        "• `/khata` — View customer credit balances\n"
        "• `/summary` — View today's sales & revenue summary\n"
        "• `/invoice <bill_id>` — Download PDF Tax Invoice\n"
        "• `/analysis` — Download PowerPoint Sales Deck\n"
        "• `/logout` — Log out of this shop session"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logout command."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    logout_user_session(telegram_id)
    USER_AUTH_STATE.pop(telegram_id, None)
    await update.message.reply_text("🔒 Logged out successfully. Send /start anytime to log into another shop session.", reply_markup=ReplyKeyboardRemove())

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /new command — resets conversation memory while preserving database preferences."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    if not is_user_authenticated(telegram_id):
        await update.message.reply_text("🔐 Authentication required. Send /start to log into your shop.", parse_mode="Markdown")
        return
        
    chat_id = update.effective_chat.id
    clear_conversation(chat_id)
    await update.message.reply_text("🔄 Conversation history cleared! Active draft bills and inventory data remain saved in the database.")

async def invoice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /invoice <bill_id> command."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    if not is_user_authenticated(telegram_id):
        await update.message.reply_text("🔐 Authentication required. Send /start to log into your shop.", parse_mode="Markdown")
        return

    if not context.args:
        await update.message.reply_text("Please specify a Bill ID. Example: `/invoice BILL-12345678`", parse_mode="Markdown")
        return
        
    bill_id = context.args[0].strip()
    await update.message.reply_text(f"📄 Generating PDF Invoice for Bill `{bill_id}`...", parse_mode="Markdown")
    
    res = generate_invoice_pdf(bill_id)
    if res.get("status") == "success" and "file_path" in res:
        file_path = res["file_path"]
        if os.path.exists(file_path):
            with open(file_path, "rb") as doc:
                await update.message.reply_document(
                    document=doc,
                    filename=os.path.basename(file_path),
                    caption=f"Tax Invoice for Bill {bill_id}"
                )
            return
    await update.message.reply_text(f"❌ Failed to generate PDF invoice: {res.get('message', 'Unknown error')}")

async def analysis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /analysis command."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    if not is_user_authenticated(telegram_id):
        await update.message.reply_text("🔐 Authentication required. Send /start to log into your shop.", parse_mode="Markdown")
        return

    period = " ".join(context.args) if context.args else "Today"
    await update.message.reply_text(f"📊 Generating PowerPoint Operations & Sales Deck for period '{period}'...", parse_mode="Markdown")
    
    res = generate_analysis_deck(period)
    if res.get("status") == "success" and "file_path" in res:
        file_path = res["file_path"]
        if os.path.exists(file_path):
            with open(file_path, "rb") as doc:
                await update.message.reply_document(
                    document=doc,
                    filename=os.path.basename(file_path),
                    caption=f"Supermarket Operations & Sales Analysis Deck ({period})"
                )
            return
    await update.message.reply_text(f"❌ Failed to generate analysis deck: {res.get('message', 'Unknown error')}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages and multi-step shop authentication state machine."""
    if not update.message:
        return

    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    user_text = (update.message.text or "").strip()
    if not user_text:
        return

    # Check if user has an active shop session
    session = get_user_session(telegram_id)
    
    # State machine for unauthenticated users (Login / Sign Up flow)
    if not session:
        state = USER_AUTH_STATE.get(telegram_id, {}).get("step")
        
        if not state or user_text in ["🆕 New Shop (Sign Up)", "🔑 Existing Shop (Log In)"]:
            if user_text == "🆕 New Shop (Sign Up)":
                USER_AUTH_STATE[telegram_id] = {"step": "signup_name", "data": {}}
                await update.message.reply_text("📝 *New Shop Registration*\n\nPlease enter your **Shop Name** (Mandatory):", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
                return
            elif user_text == "🔑 Existing Shop (Log In)":
                USER_AUTH_STATE[telegram_id] = {"step": "login_name", "data": {}}
                await update.message.reply_text("🔑 *Shop Login*\n\nPlease enter your **Shop Name**:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
                return
            else:
                await update.message.reply_text("🏬 Please select an option below:", parse_mode="Markdown", reply_markup=get_auth_choice_keyboard())
                return

        # Handle Registration Steps
        if state == "signup_name":
            USER_AUTH_STATE[telegram_id]["data"]["shop_name"] = user_text
            USER_AUTH_STATE[telegram_id]["step"] = "signup_pwd"
            await update.message.reply_text(f"🔐 Setting up **{user_text}**.\n\nPlease enter a **Password** for this shop (Mandatory):", parse_mode="Markdown")
            return

        elif state == "signup_pwd":
            USER_AUTH_STATE[telegram_id]["data"]["password"] = user_text
            USER_AUTH_STATE[telegram_id]["step"] = "signup_meta"
            await update.message.reply_text(
                "📍 *Optional Shop Details*\n\n"
                "Enter **Shop Address & GSTIN** separated by comma (or reply `skip` to complete registration):\n"
                "Example: `123 Main St Chennai, 33AABCU9603R1ZM`",
                parse_mode="Markdown"
            )
            return

        elif state == "signup_meta":
            shop_name = USER_AUTH_STATE[telegram_id]["data"]["shop_name"]
            password = USER_AUTH_STATE[telegram_id]["data"]["password"]
            
            shop_address = None
            shop_gstin = None
            if user_text.lower() != "skip":
                parts = [p.strip() for p in user_text.split(",") if p.strip()]
                if len(parts) >= 1:
                    shop_address = parts[0]
                if len(parts) >= 2:
                    shop_gstin = parts[1]

            reg_res = register_shop(shop_name=shop_name, password=password, shop_address=shop_address, shop_gstin=shop_gstin)
            if reg_res.get("status") == "success":
                login_res = login_shop(telegram_id=telegram_id, shop_name=shop_name, password=password)
                USER_AUTH_STATE.pop(telegram_id, None)
                await update.message.reply_text(
                    f"🎉 **Registration Successful!**\n\nShop **{shop_name}** is now ready! Anyone in your shop can log in using Shop Name: `{shop_name}` & your Password.\n\nType `/stock` or ask any query to start!",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ {reg_res.get('message')}\n\nPlease try again by clicking /start.")
                USER_AUTH_STATE.pop(telegram_id, None)
            return

        # Handle Login Steps
        elif state == "login_name":
            USER_AUTH_STATE[telegram_id]["data"]["shop_name"] = user_text
            USER_AUTH_STATE[telegram_id]["step"] = "login_pwd"
            await update.message.reply_text(f"🔑 Enter Password for shop **{user_text}**:", parse_mode="Markdown")
            return

        elif state == "login_pwd":
            shop_name = USER_AUTH_STATE[telegram_id]["data"]["shop_name"]
            password = user_text
            login_res = login_shop(telegram_id=telegram_id, shop_name=shop_name, password=password)
            USER_AUTH_STATE.pop(telegram_id, None)
            
            if login_res.get("status") == "success":
                await update.message.reply_text(
                    f"✅ **Login Successful!** Connected to **{shop_name}**.\n\nYou now have full access to this shop's database. Type `/stock` or ask any query!",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ {login_res.get('message')}\n\nPlease try logging in again with /start.")
            return

    chat_id = update.effective_chat.id
    owner_id = telegram_id
    update_id = str(update.update_id)

    # 💬 Continuous ChatGPT-style typing indicator while agent processes multi-turn requests
    async def keep_typing():
        try:
            while True:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    typing_task = asyncio.create_task(keep_typing())

    try:
        reply_text, generated_files = await asyncio.to_thread(
            run_agent_turn,
            user_message=user_text,
            chat_id=chat_id,
            owner_id=owner_id,
            update_id=update_id
        )
    finally:
        typing_task.cancel()

    # Send text response formatted with Markdown
    try:
        await update.message.reply_text(reply_text, parse_mode="Markdown")
    except Exception:
        # Fallback to plain text if message contains unescaped markdown characters
        await update.message.reply_text(reply_text)

    # Send generated document files if any
    for file_path in generated_files:
        if os.path.exists(file_path):
            with open(file_path, "rb") as doc:
                await update.message.reply_document(
                    document=doc,
                    filename=os.path.basename(file_path),
                    caption=f"Generated File: {os.path.basename(file_path)}"
                )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command — displays command menu and quick start guide."""
    help_text = (
        "🤖 *Supermarket Ops Agent — Available Commands*\n\n"
        "• `/start` — Start bot session & verify mobile contact\n"
        "• `/new` — Reset conversation context (standing preferences persist)\n"
        "• `/invoice <bill_id>` — Download official PDF GST Tax Invoice\n"
        "• `/analysis <period>` — Download PowerPoint (.pptx) operations sales deck\n"
        "• `/help` — Show this interactive command guide\n"
        "• `/logout` — De-authenticate user session\n\n"
        "💬 *You can also ask anything in plain text:* e.g. \"Show stock\", \"Start a bill\", \"Charge khata ₹500 to Ravi\", \"Show today's sales summary\""
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stock command."""
    update.message.text = "Show all products in stock with prices and quantities"
    await handle_message(update, context)

async def lowstock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /lowstock command."""
    update.message.text = "List all low stock items at or below reorder level"
    await handle_message(update, context)

async def bill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bill command."""
    args = " ".join(context.args) if context.args else ""
    if args:
        update.message.text = f"make a bill: {args}"
    else:
        update.message.text = "Start a new draft bill"
    await handle_message(update, context)

async def khata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /khata command."""
    args = " ".join(context.args) if context.args else ""
    if args:
        update.message.text = f"Khata query for {args}"
    else:
        update.message.text = "List all customer khata credit balances"
    await handle_message(update, context)

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /summary command."""
    update.message.text = "Show today's sales summary and total revenue breakdown"
    await handle_message(update, context)

async def post_init(application):
    """Register interactive slash commands list with Telegram UI popup menu."""
    commands = [
        BotCommand("start", "Start session & fresh context"),
        BotCommand("stock", "View all products & inventory stock"),
        BotCommand("lowstock", "View low stock reorder items"),
        BotCommand("bill", "Create a bill (e.g. /bill 2 sugar, UPI)"),
        BotCommand("khata", "View customer credit balances"),
        BotCommand("summary", "View today's sales & revenue summary"),
        BotCommand("invoice", "Download PDF GST Tax Invoice"),
        BotCommand("analysis", "Download PowerPoint Sales Deck"),
        BotCommand("new", "Reset chat history fresh"),
        BotCommand("help", "Show interactive commands guide"),
        BotCommand("logout", "Logout & clear session")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Successfully pushed comprehensive bot commands menu to Telegram API.")

def main():
    """Main application entry point."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        print("ERROR: Please set a valid TELEGRAM_BOT_TOKEN in your .env file!")
        return

    # Ensure DB exists and is seeded
    db_path = os.getenv("DB_PATH", "supermarket.db")
    seed_database(db_path)

    app = ApplicationBuilder().token(token).post_init(post_init).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("logout", logout_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("stock", stock_command))
    app.add_handler(CommandHandler("lowstock", lowstock_command))
    app.add_handler(CommandHandler("bill", bill_command))
    app.add_handler(CommandHandler("khata", khata_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("invoice", invoice_command))
    app.add_handler(CommandHandler("analysis", analysis_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), handle_message))

    print(f"🤖 Supermarket Ops Agent Telegram Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
