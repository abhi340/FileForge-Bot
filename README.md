#!/bin/bash
# ══════════════════════════════════════════════════
# Oracle Cloud VM — Full Setup Script
# Run as: sudo bash deploy.sh
# ══════════════════════════════════════════════════

set -e

echo "🚀 Starting server setup..."

# ── System Update ──
apt update && apt upgrade -y

# ── Security ──
apt install -y ufw fail2ban unattended-upgrades
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
echo "y" | ufw enable
systemctl enable fail2ban
systemctl start fail2ban
dpkg-reconfigure -plow unattended-upgrades

# ── Swap (2GB for RAM safety) ──
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "✅ 2GB swap created"
fi

# ── Python ──
apt install -y python3.11 python3.11-venv python3-pip git

# ── Bot User ──
if ! id "filebot" &>/dev/null; then
    adduser --system --home /opt/filebot --shell /bin/bash filebot
fi
mkdir -p /opt/filebot
chown filebot:nogroup /opt/filebot

echo ""
echo "✅ Server ready!"
echo ""
echo "Next steps:"
echo "1. sudo -u filebot bash"
echo "2. cd /opt/filebot"
echo "3. git clone YOUR_REPO bot"
echo "4. cd bot"
echo "5. python3.11 -m venv venv"
echo "6. source venv/bin/activate"
echo "7. pip install -r requirements.txt"
echo "8. nano .env  (add your secrets)"
echo "9. chmod 600 .env"
echo "10. python -m app.main  (test run)"
echo ""
echo "Then create systemd service:"
echo ""
cat << 'SERVICE'
# Save as /etc/systemd/system/filebot.service

[Unit]
Description=File Utility Bot
After=network.target

[Service]
Type=simple
User=filebot
Group=nogroup
WorkingDirectory=/opt/filebot/bot
Environment=PATH=/opt/filebot/bot/venv/bin:/usr/bin
EnvironmentFile=/opt/filebot/bot/.env
ExecStart=/opt/filebot/bot/venv/bin/python -m app.main
Restart=always
RestartSec=10
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/filebot/bot/data /opt/filebot/bot/tmp
MemoryMax=800M
CPUQuota=80%
StandardOutput=journal
StandardError=journal
SyslogIdentifier=filebot

[Install]
WantedBy=multi-user.target
SERVICE

echo ""
echo "Commands:"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable filebot"
echo "  sudo systemctl start filebot"

echo "  sudo journalctl -u filebot -f"



