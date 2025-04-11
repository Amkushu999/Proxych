import os
import logging
import threading
import time
import asyncio
import re
import random
import concurrent.futures
from typing import Optional, List, Dict, Any, Union, Tuple
from collections import defaultdict
from threading import Lock
from queue import Queue
from datetime import datetime

from flask import Flask, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, ConversationHandler, CallbackContext
)
from telegram.constants import ParseMode
from proxy_checker import check_proxy, check_multiple_proxies, ProxyChecker

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Constants
MAX_CONCURRENT_TASKS = 50  # Maximum concurrent proxy checks
MAX_PROXIES_PER_BATCH = 10  # Maximum number of proxies to check at once
# No animations - all features are direct and immediate

# Global variables to track bot status
bot_thread = None
bot_status = {
    "running": False,
    "started_at": None,
    "last_check": None,
    "active_users": 0,
    "total_checks": 0,
    "successful_checks": 0,
    "errors": []
}

# Stats tracking with thread safety
stats_lock = Lock()
user_stats = defaultdict(lambda: {"checks": 0, "last_active": None})
active_tasks = {}  # Track active tasks per user
task_queue = Queue()  # Global task queue for managing load

# Proxy Checker instance
proxy_checker = ProxyChecker(max_concurrent=MAX_CONCURRENT_TASKS)

# Bot config
BOT_NAME = "𝗣𝗿𝗼𝘅𝘆𝗖𝗛𝗞"  # The bot name to use everywhere

# Welcome message function - no animation
async def send_welcome_message(update: Update) -> None:
    """
    Send a simple welcome message without any animation
    
    Args:
        update: The Telegram update
    """
    try:
        # Just send a simple welcome message
        await update.message.reply_text(
            f"Welcome to {BOT_NAME}!\n\n"
            "Use /pchk [proxy] to check a proxy.\n"
            "Example: /pchk 1.2.3.4:8080\n\n"
            "You can also send multiple proxies at once (one per line)."
        )
    except Exception as e:
        logger.error(f"Welcome message error: {str(e)}")

# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    if not update.effective_user:
        return
        
    user = update.effective_user
    username = user.username or f"User_{user.id}"
    
    # Update user stats
    with stats_lock:
        user_stats[username]["last_active"] = datetime.now().isoformat()
        bot_status["active_users"] += 1
    
    # Use our simple welcome message - no animation
    await send_welcome_message(update)
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm a Proxy Checker Bot.\n\n"
        "I can check if your proxies are working and provide detailed information about them.\n\n"
        "<b>📋 How to use me:</b>\n"
        "• Use /pchk command to check proxies: <code>/pchk 1.2.3.4:8080</code>\n"
        "• You can send multiple proxies (one per line) and I'll check them all\n\n"
        f"⚡️ Powered by {BOT_NAME}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    if not update.effective_user:
        return
        
    user = update.effective_user
    username = user.username or f"User_{user.id}"
    
    # Update user stats
    with stats_lock:
        user_stats[username]["last_active"] = datetime.now().isoformat()
    
    await update.message.reply_text(
        "📋 <b>Proxy Checker Bot Help</b>\n\n"
        "<b>Supported Proxy Formats:</b>\n"
        "• Regular proxy: <code>ip:port</code>\n"
        "• Authenticated proxy: <code>ip:port:username:password</code>\n\n"
        "<b>Supported Protocols:</b>\n"
        "• HTTP\n"
        "• HTTPS\n"
        "• SOCKS4\n"
        "• SOCKS5\n\n"
        "<b>Commands:</b>\n"
        "• /start - Start the bot and get welcome message\n"
        "• /help - Show this help message\n"
        "• /pchk &lt;proxy&gt; - Check a specific proxy\n"
        "• /stats - Show your usage statistics\n\n"
        "<b>Batch Processing:</b>\n"
        "You can send multiple proxies (one per line) and I'll check them all concurrently.\n\n"
        "<b>Example:</b>\n"
        "<code>1.2.3.4:8080\n"
        "5.6.7.8:3128\n"
        "9.10.11.12:80</code>\n\n"
        "Made with ❤️ by 𝗣𝗿𝗼𝘅𝘆𝗖𝗛𝗞",
        parse_mode=ParseMode.HTML
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user stats when the command /stats is issued."""
    if not update.effective_user:
        return
        
    user = update.effective_user
    username = user.username or f"User_{user.id}"
    
    # Get user stats
    with stats_lock:
        user_stat = user_stats[username]
        total_checks = bot_status["total_checks"]
        successful_checks = bot_status["successful_checks"]
        
    # Format last active time
    last_active = "Never"
    if user_stat["last_active"]:
        try:
            last_active_dt = datetime.fromisoformat(user_stat["last_active"])
            last_active = last_active_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            last_active = user_stat["last_active"]
    
    # Generate statistics message
    await update.message.reply_text(
        f"📊 <b>Your Bot Statistics</b>\n\n"
        f"• Proxies Checked: {user_stat['checks']}\n"
        f"• Last Active: {last_active}\n\n"
        f"<b>Global Statistics:</b>\n"
        f"• Total Proxies Checked: {total_checks}\n"
        f"• Working Proxies Found: {successful_checks}\n"
        f"• Success Rate: {(successful_checks / total_checks * 100) if total_checks > 0 else 0:.1f}%\n\n"
        f"Powered by {BOT_NAME}",
        parse_mode=ParseMode.HTML
    )

async def pchk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fast proxy check command without simulations"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    username = user.username or f"User_{user.id}"
    
    # Update user stats
    with stats_lock:
        user_stats[username]["last_active"] = datetime.now().isoformat()
    
    if not context.args:
        # Show enhanced usage help with examples
        await update.message.reply_text(
            "🚀 <b>Proxy Checker - Advanced Usage</b>\n\n"
            "Please provide a proxy to check using the following format:\n\n"
            "<b>Basic usage:</b>\n"
            "<code>/pchk 1.2.3.4:8080</code>\n\n"
            "<b>With authentication:</b>\n"
            "<code>/pchk 1.2.3.4:8080:username:password</code>\n\n"
            "<b>Check multiple proxies:</b>\n"
            "(Send each proxy on a new line)\n"
            "<code>/pchk 1.2.3.4:8080\n5.6.7.8:3128</code>\n\n"
            f"⚡️ <b>Powered by {BOT_NAME}</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Join all args in case proxy has spaces
    proxy = " ".join(context.args)
    
    # Check for multiple proxies (line breaks)
    proxies = [p.strip() for p in proxy.split("\n") if p.strip()]
    
    # Process the request immediately without any animations
    if len(proxies) > 1:
        # Handle multiple proxies
        await process_multiple_proxies(update, proxies, username)
    else:
        # Handle single proxy
        await process_single_proxy(update, proxies[0], username)

async def process_single_proxy(update: Update, proxy_str: str, username: str) -> None:
    """Process a single proxy check with faster, no-simulation approach"""
    # Initial progress message - simple and direct
    progress_message = await update.message.reply_text(
        f"🔍 <b>Checking proxy:</b> <code>{proxy_str}</code>\n\n"
        f"<b>Status:</b> Processing, please wait...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Update global stats
        with stats_lock:
            user_stats[username]["checks"] += 1
            bot_status["total_checks"] += 1
            
        # Direct proxy check without progress simulation
        result = await check_proxy(proxy_str, username)
        
        # Update success stats if proxy is working
        if "✅" in result:
            with stats_lock:
                bot_status["successful_checks"] += 1
        
        # Format the result with custom styling
        styled_result = f"🔎 <b>PROXY CHECK RESULTS</b>\n\n{result}\n\n<i>Checked by {BOT_NAME} Bot</i>"
        
        # Send the result
        await update.message.reply_text(styled_result, parse_mode=ParseMode.HTML)
        
        # Delete the progress message to clean up
        await progress_message.delete()
    except Exception as e:
        logger.error(f"Error checking proxy {proxy_str}: {str(e)}")
        await progress_message.edit_text(
            f"❌ <b>Error checking proxy</b>\n\n"
            f"<code>{proxy_str}</code>\n\n"
            f"<b>Error:</b> {str(e)}\n\n"
            f"Please try again or check your proxy format.",
            parse_mode=ParseMode.HTML
        )

async def process_multiple_proxies(update: Update, proxies: List[str], username: str) -> None:
    """Process multiple proxies concurrently with fast, no-simulation approach"""
    if len(proxies) > MAX_PROXIES_PER_BATCH:
        await update.message.reply_text(
            f"⚠️ <b>Maximum batch size exceeded</b>\n\n"
            f"You've submitted {len(proxies)} proxies, but the maximum is {MAX_PROXIES_PER_BATCH}.\n"
            f"I'll check the first {MAX_PROXIES_PER_BATCH} proxies.",
            parse_mode=ParseMode.HTML
        )
        proxies = proxies[:MAX_PROXIES_PER_BATCH]
    
    # Simple progress message - direct and informative
    progress_message = await update.message.reply_text(
        f"🔄 <b>Batch Proxy Check Started</b>\n\n"
        f"<b>Status:</b> Processing {len(proxies)} proxies concurrently...\n\n"
        f"<i>Results will be sent as they are processed.</i>",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Update global stats
        with stats_lock:
            user_stats[username]["checks"] += len(proxies)
            bot_status["total_checks"] += len(proxies)
        
        # Start time for the entire batch
        start_time = time.time()
        
        # Get results directly from the batch check without animations
        results = await check_multiple_proxies(proxies, username)
        total_time = time.time() - start_time
        
        # Count successful checks
        successful = sum(1 for result in results if "✅" in result)
        
        with stats_lock:
            bot_status["successful_checks"] += successful
        
        # Success rate calculation
        success_rate = (successful / len(proxies) * 100) if proxies else 0
        
        # Update progress message with completion status
        await progress_message.edit_text(
            f"✅ <b>Batch Proxy Check Complete</b>\n\n"
            f"<b>Results Summary:</b>\n"
            f"• Total Proxies: {len(proxies)}\n"
            f"• Working Proxies: {successful}\n"
            f"• Success Rate: {success_rate:.1f}%\n"
            f"• Time Taken: {total_time:.2f} seconds\n\n"
            f"<i>Detailed results will follow...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Group results by working/non-working for better organization
        working_results = [(i, result) for i, result in enumerate(results) if "✅" in result]
        non_working_results = [(i, result) for i, result in enumerate(results) if "✅" not in result]
        
        # Process working proxies first
        if working_results:
            await update.message.reply_text(
                f"✅ <b>{len(working_results)} WORKING PROXIES FOUND</b>",
                parse_mode=ParseMode.HTML
            )
            
            for i, result in working_results:
                # Add batch index to help user track the results
                result_with_index = f"<b>Working Proxy #{i+1}/{len(proxies)}</b>\n\n{result}\n\n<i>Checked by {BOT_NAME} Bot</i>"
                
                # Minimal delay to avoid flood limits
                await asyncio.sleep(0.2)
                await update.message.reply_text(result_with_index, parse_mode=ParseMode.HTML)
        
        # Process non-working proxies
        if non_working_results:
            await update.message.reply_text(
                f"❌ <b>{len(non_working_results)} NON-WORKING PROXIES</b>",
                parse_mode=ParseMode.HTML
            )
            
            for i, result in non_working_results:
                # Add batch index to help user track the results
                result_with_index = f"<b>Failed Proxy #{i+1}/{len(proxies)}</b>\n\n{result}\n\n<i>Checked by {BOT_NAME} Bot</i>"
                
                # Minimal delay to avoid flood limits
                await asyncio.sleep(0.2)
                await update.message.reply_text(result_with_index, parse_mode=ParseMode.HTML)
                
        # Simple completion message
        await update.message.reply_text(
            f"🏁 <b>Batch check completed</b>\n\n"
            f"<i>Thank you for using {BOT_NAME} Proxy Checker</i>",
            parse_mode=ParseMode.HTML
        )
            
    except Exception as e:
        logger.error(f"Error in batch proxy checking: {str(e)}")
        await progress_message.edit_text(
            f"❌ <b>Error in Batch Processing</b>\n\n"
            f"<b>Error details:</b> {str(e)}\n\n"
            f"<i>Please try again with a smaller batch or check each proxy individually.</i>",
            parse_mode=ParseMode.HTML
        )

async def proxy_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process messages that might contain proxy information."""
    if not update.effective_user:
        return
        
    user = update.effective_user
    username = user.username or f"User_{user.id}"
    
    # Update user stats
    with stats_lock:
        user_stats[username]["last_active"] = datetime.now().isoformat()
    
    text = update.message.text
    
    # Split by new lines to detect multiple proxies
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    valid_proxies = []
    
    # Validate each line for proxy format
    for line in lines:
        if ":" in line and len(line.split(":")) in [2, 4]:
            valid_proxies.append(line)
    
    if not valid_proxies:
        await update.message.reply_text(
            "That doesn't look like a valid proxy format.\n\n"
            "Please use:\n"
            "• <code>ip:port</code> - for regular proxies\n"
            "• <code>ip:port:username:password</code> - for authenticated proxies\n\n"
            "You can also send multiple proxies, one per line.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if len(valid_proxies) > 1:
        # Process multiple proxies
        await process_multiple_proxies(update, valid_proxies, username)
    else:
        # Process single proxy
        await process_single_proxy(update, valid_proxies[0], username)

def run_bot_async(token=None):
    """Run the Telegram bot using asyncio."""
    global bot_status
    
    # Get token from environment variable if not provided
    if not token:
        token = os.environ.get("TELEGRAM_TOKEN")
    
    if not token:
        error_msg = "TELEGRAM_TOKEN environment variable not set!"
        logger.error(error_msg)
        bot_status["errors"].append(error_msg)
        bot_status["running"] = False
        return
    
    # Set up asyncio event loop
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def start_bot():
            logger.info("Initializing Telegram bot")
            
            # Create the Application with optimized settings for high concurrency
            application = Application.builder().token(token).concurrent_updates(True).build()
            
            # Set bot commands for menu - only /start and /pchk as requested
            commands = [
                BotCommand("start", "Start the bot and show welcome message"),
                BotCommand("pchk", "Check a proxy: /pchk ip:port"),
            ]
            
            await application.bot.set_my_commands(commands)
            
            # Set up command handlers - only responding to /start and /pchk as requested
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("pchk", pchk_command))
            
            # Removed message handler to only respond to /start and /pchk commands as requested
            # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, proxy_message))
            
            # Start the bot with polling
            logger.info("Starting Telegram bot")
            await application.initialize()
            await application.start()
            await application.updater.start_polling(
                poll_interval=0.5,  # Faster polling interval
                timeout=10,         # Longer timeout for stability
                bootstrap_retries=-1,  # Infinite retries if connection fails
                allowed_updates=Update.ALL_TYPES  # Accept all update types
            )
            
            bot_status["running"] = True
            bot_status["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.info("Bot is running")
            
            try:
                # Just keep running
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Stopping the bot")
            except Exception as e:
                error_msg = f"Error in bot loop: {str(e)}"
                logger.error(error_msg)
                bot_status["errors"].append(error_msg)
            finally:
                # Stop the bot when we're done
                bot_status["running"] = False
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
                await proxy_checker.close()  # Close the proxy checker
        
        # Run the bot
        loop.run_until_complete(start_bot())
    except Exception as e:
        error_msg = f"Error in run_bot_async function: {str(e)}"
        logger.error(error_msg)
        bot_status["errors"].append(error_msg)
        bot_status["running"] = False

def run_bot_thread():
    """Run the Telegram bot in a background thread"""
    global bot_status
    
    logger.info("Starting Telegram bot in a separate thread...")
    bot_status["errors"] = []  # Clear previous errors
    
    try:
        run_bot_async()
    except Exception as e:
        error_msg = f"Error running bot thread: {str(e)}"
        logger.error(error_msg)
        bot_status["errors"].append(error_msg)
        bot_status["running"] = False

# HTML template for status page with more detailed statistics
STATUS_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Proxy Checker Bot Status | {{ bot_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding-top: 2rem; background-color: #f8f9fa; }
        .bot-status { font-size: 1.1rem; padding: 1rem; border-radius: 5px; margin-bottom: 1rem; }
        .running { background-color: #d4edda; color: #155724; }
        .not-running { background-color: #f8d7da; color: #721c24; }
        .card { margin-top: 1rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: none; }
        .card-header { background-color: #6c757d; color: white; font-weight: bold; }
        .stats-card { background-color: #f1f8ff; }
        .footer { margin-top: 3rem; padding: 1rem 0; border-top: 1px solid #dee2e6; }
        .logo { font-size: 2rem; font-weight: bold; margin-bottom: 1rem; letter-spacing: 1px; }
        .stat-value { font-size: 1.5rem; font-weight: bold; }
        .stat-label { font-size: 0.9rem; color: #6c757d; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .fade-in { animation: fadeIn 0.5s ease-in; }
    </style>
</head>
<body>
    <div class="container fade-in">
        <div class="logo text-center mb-4">{{ bot_name }} Proxy Checker</div>
        
        <div class="bot-status {% if status.running %}running{% else %}not-running{% endif %}">
            <strong>Status:</strong> {% if status.running %}RUNNING{% else %}NOT RUNNING{% endif %}
            {% if status.started_at %}
            <div><strong>Started at:</strong> {{ status.started_at }}</div>
            {% endif %}
        </div>
        
        <div class="row">
            <div class="col-md-6">
                <div class="card stats-card">
                    <div class="card-header">Bot Statistics</div>
                    <div class="card-body">
                        <div class="row text-center">
                            <div class="col-6 mb-3">
                                <div class="stat-value">{{ status.total_checks }}</div>
                                <div class="stat-label">TOTAL CHECKS</div>
                            </div>
                            <div class="col-6 mb-3">
                                <div class="stat-value">{{ status.successful_checks }}</div>
                                <div class="stat-label">WORKING PROXIES</div>
                            </div>
                            <div class="col-6">
                                <div class="stat-value">{{ status.active_users }}</div>
                                <div class="stat-label">ACTIVE USERS</div>
                            </div>
                            <div class="col-6">
                                <div class="stat-value">{{ "%.1f"|format(status.successful_checks / status.total_checks * 100) if status.total_checks > 0 else "0.0" }}%</div>
                                <div class="stat-label">SUCCESS RATE</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Usage Instructions</div>
                    <div class="card-body">
                        <h5 class="card-title">How to use the Proxy Checker Bot</h5>
                        <ol>
                            <li>Open Telegram and search for your bot</li>
                            <li>Start a chat with the bot by clicking on the Start button</li>
                            <li>Send a proxy in one of these formats:
                                <ul>
                                    <li><code>ip:port</code> - for regular proxies</li>
                                    <li><code>ip:port:username:password</code> - for authenticated proxies</li>
                                </ul>
                            </li>
                            <li>The bot will check if the proxy is alive and provide detailed information</li>
                        </ol>
                        <h5 class="mt-3">Available Commands</h5>
                        <ul>
                            <li><code>/start</code> - Start the bot and get welcome message</li>
                            <li><code>/pchk ip:port</code> - Check a specific proxy</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
        
        {% if status.errors %}
        <div class="card mt-3">
            <div class="card-header bg-warning">Errors</div>
            <div class="card-body">
                <ul>
                    {% for error in status.errors %}
                    <li>{{ error }}</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
        {% endif %}
        
        <p class="mt-3 text-center">
            <a href="/restart" class="btn btn-primary">Restart Bot</a>
        </p>
        
        <footer class="footer text-center text-muted">
            <p>Proxy Checker Telegram Bot | &copy; 2025 | {{ bot_name }}</p>
        </footer>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Render the status page"""
    global bot_status
    # Update the last check time
    bot_status["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return render_template_string(STATUS_PAGE_HTML, status=bot_status, bot_name=BOT_NAME)

@app.route('/api/status')
def api_status():
    """Return status information as JSON"""
    global bot_status
    # Update the last check time
    bot_status["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(bot_status)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route('/restart')
def restart_bot():
    """Restart the Telegram bot"""
    global bot_thread, bot_status
    
    if bot_thread and bot_thread.is_alive():
        logger.info("Bot thread is already running")
        return jsonify({"status": "Bot already running"})
        
    logger.info("Starting bot thread from /restart route")
    bot_status["errors"] = []  # Clear previous errors
    bot_thread = threading.Thread(target=run_bot_thread)
    bot_thread.daemon = True
    bot_thread.start()
    
    return jsonify({"status": "Bot restarted"})

# Start the bot when the server starts
def start_bot_on_startup():
    global bot_thread
    
    # Wait a moment for the server to start properly
    time.sleep(2)
    
    logger.info("Starting bot thread on application startup")
    bot_thread = threading.Thread(target=run_bot_thread)
    bot_thread.daemon = True
    bot_thread.start()

# Start the bot in a separate thread after a short delay
startup_thread = threading.Thread(target=start_bot_on_startup)
startup_thread.daemon = True
startup_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)