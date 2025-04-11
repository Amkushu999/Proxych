import os
import logging
import threading
import time
from flask import Flask, jsonify, render_template_string
from main import main

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Global variables
bot_thread = None
bot_status = {
    "running": False,
    "started_at": None,
    "errors": []
}

def run_bot():
    """Run the Telegram bot in a background thread"""
    global bot_status
    
    # Import asyncio here to keep it within this thread
    import asyncio
    
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        error_msg = "TELEGRAM_TOKEN environment variable not set!"
        logger.error(error_msg)
        bot_status["errors"].append(error_msg)
        bot_status["running"] = False
        return
    
    logger.info("Starting Telegram bot...")
    bot_status["running"] = True
    bot_status["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the main function directly if it's not async, or use loop.run_until_complete if it is
        main(token)
    except Exception as e:
        error_msg = f"Error running bot: {str(e)}"
        logger.error(error_msg)
        bot_status["errors"].append(error_msg)
        bot_status["running"] = False

# HTML template for status page
STATUS_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Proxy Checker Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding-top: 2rem; }
        .bot-status { font-size: 1.1rem; padding: 1rem; border-radius: 5px; margin-bottom: 1rem; }
        .running { background-color: #d4edda; color: #155724; }
        .not-running { background-color: #f8d7da; color: #721c24; }
        .card { margin-top: 1rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mb-4">Telegram Proxy Checker Bot</h1>
        
        <div class="bot-status {% if status.running %}running{% else %}not-running{% endif %}">
            <strong>Status:</strong> {% if status.running %}Running{% else %}Not Running{% endif %}
            {% if status.started_at %}
            <div><strong>Started at:</strong> {{ status.started_at }}</div>
            {% endif %}
        </div>
        
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
                    <li><code>/help</code> - Show help information</li>
                    <li><code>/check ip:port</code> - Check a specific proxy</li>
                </ul>
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
        
        <footer class="mt-5 text-center text-muted">
            <p>Proxy Checker Telegram Bot | <a href="https://github.com/your-username/proxy-checker-bot">GitHub</a></p>
        </footer>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Render the status page"""
    return render_template_string(STATUS_PAGE_HTML, status=bot_status)

@app.route('/api/status')
def api_status():
    """Return status information as JSON"""
    return jsonify(bot_status)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route('/start_bot')
def start_bot_route():
    """Start the bot manually"""
    global bot_thread, bot_status
    
    if bot_thread is None or not bot_thread.is_alive():
        logger.info("Starting bot thread from /start_bot route")
        bot_status["errors"] = []  # Clear previous errors
        bot_thread = threading.Thread(target=run_bot)
        bot_thread.daemon = True
        bot_thread.start()
        return jsonify({"status": "Bot started"})
    
    return jsonify({"status": "Bot already running"})

# Start the bot when the application loads
def start_bot_on_startup():
    global bot_thread
    logger.info("Starting bot thread on application startup")
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

# Start the bot
start_bot_on_startup()

# This is needed for gunicorn
# The variable name must be "app" for gunicorn to find it
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)