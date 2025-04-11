# 𝗔𝗠𝗞𝗨𝗦𝗛...𝗜𝗡𝗡𝗜𝗧 Proxy Checker Bot - Deployment Guide

This guide explains how to deploy the Proxy Checker Telegram Bot on your own VPS (Virtual Private Server).

## Requirements

- A VPS running Linux (Ubuntu/Debian recommended)
- Python 3.9+ installed
- A Telegram Bot Token (obtained from @BotFather)
- Basic knowledge of command line and server administration

## Step 1: Set Up Your VPS

1. Connect to your VPS via SSH:
   ```
   ssh username@your_server_ip
   ```

2. Update your system:
   ```
   sudo apt update && sudo apt upgrade -y
   ```

3. Install required system dependencies:
   ```
   sudo apt install -y python3 python3-pip python3-venv git
   ```

## Step 2: Clone the Repository

1. Clone the bot repository:
   ```
   git clone https://github.com/yourusername/proxy-checker-bot.git
   cd proxy-checker-bot
   ```

   Alternatively, you can upload the files directly to your server using SCP or SFTP.

## Step 3: Set Up Python Environment

1. Create a virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install required Python packages:
   ```
   pip install -r requirements.txt
   ```

   If you don't have a requirements.txt file, create one with the following contents:
   ```
   python-telegram-bot[socks]
   flask
   gunicorn
   aiohttp
   ```

## Step 4: Configure Your Bot

1. Create a .env file to store your Telegram Bot Token:
   ```
   echo "TELEGRAM_TOKEN=your_bot_token_here" > .env
   ```

   Replace `your_bot_token_here` with the token you received from @BotFather.

## Step 5: Test Your Bot

1. Run the bot to ensure it works:
   ```
   python main.py
   ```

   The bot should start without errors. You can send commands like `/start` or `/help` to your bot on Telegram to verify it's working.

2. Press `Ctrl+C` to stop the bot after testing.

## Step 6: Set Up the Bot for Production

### Option 1: Using systemd (Recommended)

1. Create a systemd service file:
   ```
   sudo nano /etc/systemd/system/proxy-checker-bot.service
   ```

2. Add the following content (adjust paths as needed):
   ```
   [Unit]
   Description=Proxy Checker Telegram Bot
   After=network.target

   [Service]
   User=your_username
   WorkingDirectory=/path/to/proxy-checker-bot
   ExecStart=/path/to/proxy-checker-bot/venv/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120 main:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```
   sudo systemctl enable proxy-checker-bot
   sudo systemctl start proxy-checker-bot
   ```

4. Check status to verify it's running:
   ```
   sudo systemctl status proxy-checker-bot
   ```

### Option 2: Using Screen or tmux

1. Install screen if not already installed:
   ```
   sudo apt install screen
   ```

2. Start a new screen session:
   ```
   screen -S proxy-bot
   ```

3. Run the bot using gunicorn:
   ```
   gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120 main:app
   ```

4. Detach from the screen session by pressing `Ctrl+A` followed by `D`.

5. To reattach to the session later:
   ```
   screen -r proxy-bot
   ```

## Step 7: Set Up Automatic Restart (Optional)

You can use a simple script to check if the bot is running and restart it if needed:

1. Create a check script:
   ```
   nano /path/to/proxy-checker-bot/check_bot.sh
   ```

2. Add the following content:
   ```bash
   #!/bin/bash
   if ! pgrep -f "gunicorn.*main:app" > /dev/null; then
       echo "Bot is not running. Restarting..."
       cd /path/to/proxy-checker-bot
       source venv/bin/activate
       gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120 main:app &
   fi
   ```

3. Make the script executable:
   ```
   chmod +x /path/to/proxy-checker-bot/check_bot.sh
   ```

4. Add a cron job to run this script periodically:
   ```
   crontab -e
   ```

5. Add the following line to run the check every 5 minutes:
   ```
   */5 * * * * /path/to/proxy-checker-bot/check_bot.sh >> /path/to/proxy-checker-bot/cron.log 2>&1
   ```

## Step 8: Set Up Nginx as a Reverse Proxy (Optional)

If you want to expose the web status page securely:

1. Install Nginx:
   ```
   sudo apt install nginx
   ```

2. Create a new site configuration:
   ```
   sudo nano /etc/nginx/sites-available/proxy-checker-bot
   ```

3. Add the following configuration (adjust domain as needed):
   ```
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://localhost:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

4. Enable the site and restart Nginx:
   ```
   sudo ln -s /etc/nginx/sites-available/proxy-checker-bot /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

5. You can then set up SSL with Let's Encrypt for secure HTTPS access.

## Troubleshooting

### Bot Not Starting

1. Check logs:
   ```
   sudo journalctl -u proxy-checker-bot
   ```

2. Verify environment variables:
   ```
   cat .env
   ```

3. Ensure all required packages are installed:
   ```
   pip install -r requirements.txt
   ```

### Connection Issues

1. Make sure your server allows outbound connections to Telegram's API servers.
2. Check firewall settings if the web interface isn't accessible.

### Memory Issues

If the bot is using too much memory, adjust the gunicorn worker and thread settings in your systemd file or startup command.

## Maintenance

### Updating the Bot

1. Pull the latest code:
   ```
   cd /path/to/proxy-checker-bot
   git pull
   ```

2. Install any new dependencies:
   ```
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Restart the service:
   ```
   sudo systemctl restart proxy-checker-bot
   ```

### Monitoring

You can set up basic monitoring with tools like:
- Monit
- Prometheus + Grafana
- Simple cron jobs that check the status endpoint

## Security Considerations

1. Always keep your system updated.
2. Don't expose the bot's API directly to the internet.
3. Use a non-root user to run the bot.
4. Consider implementing rate limiting if your bot becomes popular.
5. Regularly check logs for unusual activity.

---

## License and Attribution

This bot was created by 𝗔𝗠𝗞𝗨𝗦𝗛...𝗜𝗡𝗡𝗜𝗧.

For questions or support, please contact [your contact information].