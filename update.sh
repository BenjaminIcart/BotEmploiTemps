#!/bin/bash
# Mise à jour (dans le container) : pct exec <CTID> -- bash /opt/edt-trains/update.sh
set -e
cd /opt/edt-trains
git config --global --add safe.directory /opt/edt-trains
git pull -q
command -v fc-list >/dev/null && fc-list | grep -qi dejavu || apt-get install -y -qq fonts-dejavu-core >/dev/null
venv/bin/pip install -q -r requirements.txt
chown -R edt:edt .
systemctl restart edt-trains
echo "✅ À jour : $(git log -1 --format='%h %s')"
