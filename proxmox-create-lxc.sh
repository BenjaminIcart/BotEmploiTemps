#!/bin/bash
# À lancer sur l'HÔTE Proxmox (shell du nœud), en root
set -e
CTID=${CTID:-$(pvesh get /cluster/nextid)}
STORAGE=${STORAGE:-local-lvm}
BRIDGE=${BRIDGE:-vmbr0}

pveam update >/dev/null
TPL=$(pveam available --section system | awk '/debian-13-standard.*amd64/ {print $2}' | sort -V | tail -1)
[ -z "$TPL" ] && TPL=$(pveam available --section system | awk '/debian-12-standard.*amd64/ {print $2}' | sort -V | tail -1)
pveam list local | grep -q "$TPL" || pveam download local "$TPL"

pct create "$CTID" "local:vztmpl/$TPL" \
  --hostname edt-trains --cores 1 --memory 512 --swap 256 \
  --rootfs "$STORAGE:4" --net0 name=eth0,bridge=$BRIDGE,ip=dhcp \
  --unprivileged 1 --features nesting=1 --onboot 1 --timezone Europe/Paris
pct start "$CTID"
sleep 8
pct exec "$CTID" -- bash -c "apt-get update -qq && apt-get install -y -qq curl >/dev/null && \
  bash <(curl -fsSL https://raw.githubusercontent.com/BenjaminIcart/BotEmploiTemps/main/install.sh)"
IP=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')
echo ""
echo "✅ Container $CTID créé — IP : $IP"
echo "➡️  pct enter $CTID   puis   nano /opt/edt-trains/.env   puis   systemctl restart edt-trains"
echo "🌐 Site : http://$IP:8080"
