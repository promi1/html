#!/bin/bash
# VPN Bot — Deployment Script
# Run on the target server as root

set -e

APP_DIR="/opt/vpnbot"
VENV_DIR="$APP_DIR/venv"

echo "═══════════════════════════════════════════"
echo "  🛡️  VPN Bot — Deployment"
echo "═══════════════════════════════════════════"

# 1. System dependencies
echo "📦 Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv sshpass curl jq > /dev/null

# 2. Create app directory
echo "📁 Setting up $APP_DIR..."
mkdir -p "$APP_DIR"

# 3. Copy files
echo "📋 Copying files..."
cp -r . "$APP_DIR/"

# 4. Python venv
echo "🐍 Setting up Python environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# 5. Create .env if not exists
if [ ! -f "$APP_DIR/.env" ]; then
    echo "📝 Creating .env from template..."
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "⚠️  Edit $APP_DIR/.env with your settings!"
fi

# 6. Systemd service
echo "⚙️  Creating systemd service..."
cat > /etc/systemd/system/vpnbot.service << 'EOF'
[Unit]
Description=VPN Telegram Bot + Admin Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vpnbot
EnvironmentFile=/opt/vpnbot/.env
ExecStart=/opt/vpnbot/venv/bin/python /opt/vpnbot/bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vpnbot

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ Deployment complete!"
echo "═══════════════════════════════════════════"
echo ""
echo "  📝 Configure:  nano $APP_DIR/.env"
echo "  🚀 Start:      systemctl start vpnbot"
echo "  📊 Status:      systemctl status vpnbot"
echo "  📜 Logs:        journalctl -u vpnbot -f"
echo "  🔄 Restart:     systemctl restart vpnbot"
echo ""
