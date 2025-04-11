#!/usr/bin/env python3
import os
import logging
import threading
import time
from main import main

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_bot():
    """Run the Telegram bot"""
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    
    logger.info("Starting Telegram bot...")
    try:
        main(token)
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}")

if __name__ == "__main__":
    # Start the bot in a separate thread
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    logger.info("Bot thread started. The bot will run until this process is terminated.")
    
    # Keep the main thread running
    try:
        while True:
            time.sleep(60)
            logger.info("Bot checker heartbeat - still running")
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down.")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        logger.info("Bot runner shutting down.")