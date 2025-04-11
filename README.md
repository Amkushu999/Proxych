# Proxy Checker Telegram Bot

A Telegram bot that checks if proxies are alive and provides detailed information about them.

## Features

- Check if a proxy is reachable
- Test proxy with both HTTP and HTTPS protocols
- Measure connection and response times
- Detect the anonymity level of the proxy
- Support for both authenticated and non-authenticated proxies

## Commands

- `/start` - Initialize the bot
- `/help` - Get help on how to use the bot
- `/check [proxy]` - Check a specific proxy (e.g., `/check 1.2.3.4:8080`)

## Proxy Formats

The bot supports the following proxy formats:

- Regular proxy: `ip:port`
- Authenticated proxy: `ip:port:username:password`

## Setup

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install python-telegram-bot[all] aiohttp
   ```
3. Set up your Telegram bot token:
   ```
   export TELEGRAM_TOKEN=your_telegram_bot_token
   ```
4. Run the bot:
   ```
   python main.py
   ```

## How It Works

1. The bot parses the proxy string to extract the IP, port, and optional credentials
2. It first checks if the proxy is connectable by attempting a socket connection
3. Then it tests the proxy with HTTP and HTTPS requests to determine if it works with these protocols
4. The bot analyzes the response to determine the proxy's anonymity level
5. Finally, it presents a detailed report of the check results

## Privacy & Security

This bot doesn't store any proxy details or check results - all processing is done on-demand and results are only sent to the user who initiated the check.