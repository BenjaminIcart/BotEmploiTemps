# BotEmploiTemps 🚆

Emploi du temps (.ics) → Discord (webhook) + surveillance des retards ligne N (Coignières / Trappes → Paris Montparnasse) + petit site web.

## Fonctionnement
- **Toutes les 15 min** : relit le .ics, envoie un message Discord si un cours est annulé, ajouté ou déplacé, et recalcule le train si le 1er cours change.
- **20h** : EDT du lendemain + heure de départ conseillée (Coignières 🚶 / Trappes 🚗) + trains retour.
- **Le matin** : surveillance du train conseillé (✅ à l'heure / ⏱️ retard / 🚫 supprimé + alternatives).
- **10 min avant la fin des cours** : prochains trains retour.
- **Site web** (`:8080`) : EDT de la semaine, train conseillé, retour, sync forcée, historique des retards.
- **Optionnel** : webhook Home Assistant à chaque changement d'état.

Données trains : API PRIM d'Île-de-France Mobilités (Calculateur IDFM / Navitia, temps réel).

## Installation sur Proxmox
Dans le shell du nœud Proxmox :
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/BenjaminIcart/BotEmploiTemps/main/proxmox-create-lxc.sh)"
```
Puis :
```bash
pct enter <CTID>
nano /opt/edt-trains/.env
systemctl restart edt-trains && journalctl -u edt-trains -f
```

## Mise à jour
```bash
pct exec <CTID> -- bash -c "cd /opt/edt-trains && git pull && systemctl restart edt-trains"
```
