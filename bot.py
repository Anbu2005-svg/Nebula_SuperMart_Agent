import os
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
from skills.auth import is_user_authenticated, authenticate_user, deauthenticate_user

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_auth_keyboard():
    """Returns simple 1-click Mobile Contact Verification keyboard button."""
    keyboard = [[KeyboardButton(text="📱 Click to Verify Mobile Number", request_contact=True)]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    
    if not is_user_authenticated(telegram_id):
        auth_msg = (
            "🔐 *Supermarket Ops Agent — Simple Mobile Verification*\n\n"
            "Welcome! To access store operations, please click the button below to verify your mobile contact."
        )
        await update.message.reply_text(auth_msg, parse_mode="Markdown", reply_markup=get_auth_keyboard())
        return

    welcome_text = (
        "🛒 *Welcome to Supermarket Ops Agent!*\n\n"
        "I am your AI operations assistant. You can talk to me naturally or use commands:\n\n"
        "• *Inventory List:* \"Show all products in stock\", \"List low stock items\"\n"
        "• *Receive Stock:* \"Add 50 packets of Maggi Noodles at ₹12 cost, ₹14 MRP, 18% GST\"\n"
        "• *Billing:* \"Start a bill\", \"Add 2 Aashirvaad Atta and 1 Tata Salt\", \"Preview bill\", \"Finalize with UPI\"\n"
        "• *Khata (Credit):* \"Charge ₹500 khata to Ravi\", \"What is Ravi's balance?\", \"Ravi paid ₹200\"\n"
        "• *Daily Summary:* \"Show today's sales summary\"\n"
        "• *Set Preferences:* \"Set default payment mode to UPI\"\n\n"
        "⚡ *Commands:*\n"
        "• `/invoice <bill_id>` — Download PDF Tax Invoice\n"
        "• `/analysis` — Download PowerPoint Analytics Deck\n"
        "• `/new` — Reset conversation context (Preferences persist!)\n"
        "• `/logout` — De-authenticate session"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logout command."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    deauthenticate_user(telegram_id)
    await update.message.reply_text("🔒 Logged out successfully. Click verify to re-authenticate when needed.", reply_markup=ReplyKeyboardRemove())

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /new command — resets conversation memory while preserving database preferences."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    if not is_user_authenticated(telegram_id):
        await update.message.reply_text("🔐 Authentication required. Please tap the button below to verify.", parse_mode="Markdown", reply_markup=get_auth_keyboard())
        return
        
    chat_id = update.effective_chat.id
    clear_conversation(chat_id)
    await update.message.reply_text("🔄 Conversation history cleared! Active draft bills and standing preferences remain saved in the database.")

async def invoice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /invoice <bill_id> command."""
    telegram_id = str(update.effective_user.id) if update.effective_user else "default"
    if not is_user_authenticated(telegram_id):
        await update.message.reply_text("🔐 Authentication required. Please tap the button below to verify.", parse_mode="Markdown", reply_markup=get_auth_keyboard())
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
        await update.message.reply_text("🔐 Authentication required. Please tap the button below to verify.", parse_mode="Markdown", reply_markup=get_auth_keyboard())
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
    """Handle regular text messages and contact sharing."""
    if not update.message:
        return

    telegram_id = str(update.effective_user.id) if update.effective_user else "default"

    # Handle Simple 1-Click Mobile Contact Sharing Authentication
    if update.message.contact:
        phone = update.message.contact.phone_number
        authenticate_user(telegram_id, phone_number=phone)
        await update.message.reply_text(
            f"✅ **Mobile Verified!** ({phone})\n\nAuthentication successful. Welcome to Supermarket Ops Agent! Ask any store operation query.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    user_text = update.message.text
    if not user_text:
        return

    # Check Simple Auth
    if not is_user_authenticated(telegram_id):
        auth_req = (
            "🔐 *Verification Required*\n\n"
            "To access Supermarket Ops Agent, please tap the button below to verify your mobile contact."
        )
        await update.message.reply_text(auth_req, parse_mode="Markdown", reply_markup=get_auth_keyboard())
        return

    chat_id = update.effective_chat.id
    owner_id = telegram_id
    update_id = str(update.update_id)

    # Show typing status while AI processes turn
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    reply_text, generated_files = run_agent_turn(
        user_message=user_text,
        chat_id=chat_id,
        owner_id=owner_id,
        update_id=update_id
    )

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

async def post_init(application):
    """Register interactive slash commands list with Telegram UI popup menu."""
    commands = [
        BotCommand("start", "Start bot & verify mobile contact"),
        BotCommand("new", "Reset conversation history"),
        BotCommand("invoice", "Download PDF GST Tax Invoice"),
        BotCommand("analysis", "Download PowerPoint Sales Deck"),
        BotCommand("help", "Show commands guide"),
        BotCommand("logout", "De-authenticate user session")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Successfully pushed bot commands menu to Telegram API.")

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
    app.add_handler(CommandHandler("invoice", invoice_command))
    app.add_handler(CommandHandler("analysis", analysis_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), handle_message))

    print(f"🤖 Supermarket Ops Agent Telegram Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
