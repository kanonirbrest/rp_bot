#!/bin/bash
set -e

echo "=== Обновление системы ==="
sudo apt update && sudo apt upgrade -y

echo "=== Установка Python ==="
sudo apt install python3-pip python3-venv -y

echo "=== Создание папки бота ==="
mkdir -p ~/welcome-bot

echo "=== Установка зависимостей ==="
cd ~/welcome-bot
pip3 install -r requirements.txt

echo "=== Настройка автозапуска ==="
sudo tee /etc/systemd/system/welcome-bot.service > /dev/null <<EOF
[Unit]
Description=Welcome Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/welcome-bot
ExecStart=/usr/bin/python3 /home/ubuntu/welcome-bot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable welcome-bot
sudo systemctl start welcome-bot

echo ""
echo "=== Готово! Проверяем статус ==="
sudo systemctl status welcome-bot --no-pager
