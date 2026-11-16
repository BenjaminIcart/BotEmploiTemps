#!/bin/bash
# Installation DANS le container (Debian), en root
set -e
REPO=https://github.com/BenjaminIcart/BotEmploiTemps.git
DIR=/opt/edt-trains
apt-get update -qq && apt-get install -y -qq git python3-venv tzdata >/dev/null
ln -sf /usr/share/zoneinfo/Europe/Paris /etc/localtime
id edt &>/dev/null || useradd -r -s /usr/sbin/nologin edt
if [ -d $DIR/.git ]; then git -C $DIR pull; else git clone -q $REPO $DIR; fi
[ -f $DIR/.env ] || cp $DIR/.env.example $DIR/.env
python3 -m venv $DIR/venv
$DIR/venv/bin/pip install -q -r $DIR/requirements.txt
chown -R edt:edt $DIR && chmod 600 $DIR/.env
cat > /etc/systemd/system/edt-trains.service <<UNIT
[Unit]
Description=EDT + trains -> Discord
After=network-online.target
Wants=network-online.target

[Service]
User=edt
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable -q edt-trains && systemctl restart edt-trains
echo "✅ Installé. Remplis $DIR/.env puis : systemctl restart edt-trains && journalctl -u edt-trains -f"
