#!/usr/bin/env python3
import os
import logging
from main import main

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Check if telegram token is set
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logging.error("TELEGRAM_TOKEN environment variable not set! Please set it and try again.")
        logging.info("You can get a token by talking to @BotFather on Telegram.")
        print("\n-------------------------------------------------")
        print("ERROR: TELEGRAM_TOKEN environment variable not set!")
        print("-------------------------------------------------")
        print("To run this bot, you need to get a Telegram bot token from @BotFather")
        print("and set it as an environment variable. For example:")
        print("\nexport TELEGRAM_TOKEN=your_token_here\n")
        print("Or add it through the Replit secrets tab in the left sidebar.")
        exit(1)
    
    # Run the bot
    print("Starting Telegram Proxy Checker Bot...")
    main()