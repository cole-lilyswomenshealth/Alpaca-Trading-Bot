#!/bin/bash
# ==============================================
# Alpaca Trading Bot - Droplet Deployment Script
# Run this ON your DigitalOcean droplet
# ==============================================

set -e

echo "🚀 Deploying Alpaca Trading Bot..."

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+ and dependencies
sudo apt install -y python3 python3-pip python3-venv git nginx

# Create app directory
APP_DIR="/opt/alpaca-trading-bot"
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Clone or copy your repo (adjust the URL to your actual repo)
echo "📁 Setting up application directory at $APP_DIR"
echo "   Copy your project files here, or clone your repo:"
echo "   git clone https://github.com/YOUR_USERNAME/Alpaca-Trading-Bot.git $APP_DIR"
echo ""

# Create virtual environment
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create .env from example if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Created .env from .env.example - EDIT IT with your real API keys!"
    echo "   nano $APP_DIR/.env"
fi

# Create systemd service
sudo tee /etc/systemd/system/alpaca-bot.service > /dev/null <<EOF
[Unit]
Description=Alpaca Trading Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR/server
Environment=PATH=$APP_DIR/venv/bin:/usr/bin
ExecStart=$APP_DIR/venv/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 --access-logfile /var/log/alpaca-bot/access.log --error-logfile /var/log/alpaca-bot/error.log app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create log directory
sudo mkdir -p /var/log/alpaca-bot
sudo chown $USER:$USER /var/log/alpaca-bot

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable alpaca-bot
sudo systemctl start alpaca-bot

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "  1. Edit your .env file:  nano $APP_DIR/.env"
echo "  2. Restart the bot:      sudo systemctl restart alpaca-bot"
echo "  3. Check status:         sudo systemctl status alpaca-bot"
echo "  4. View logs:            sudo journalctl -u alpaca-bot -f"
echo "  5. View access logs:     tail -f /var/log/alpaca-bot/access.log"
echo ""
echo "🌐 Your bot is running at: http://YOUR_DROPLET_IP:5000"
echo "   Webhook URL:            http://YOUR_DROPLET_IP:5000/webhook"
echo "   Health check:           http://YOUR_DROPLET_IP:5000/health"
