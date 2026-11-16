# Supervision à distance d'une station automatisée S7-300 (Flask + snap7)

Application web de supervision et de commande à distance d'une station automatisée pilotée par un automate Siemens S7-300.

## Fonctionnalités
- Visualisation en temps réel des entrées (E124.x) et sorties (A124.x)
- Commande à distance des bits de contrôle (M0.x)
- Consignes analogiques des bacs P1, P2, P3 (0–100 %)
- Accès distant via Ngrok

## Architecture
Interface Web ⇄ API Flask ⇄ snap7 ⇄ Automate S7-300 (S7 sur TCP/IP)

## Technologies
Siemens S7-300 · Step 7 · Python · Flask · python-snap7 · HTML/CSS/JS · Ngrok

## Lancement
```bash
pip install -r requirements.txt
python supervision.py
```

## Documentation
Rapport complet : [docs/rapport.pdf](docs/rapport.pdf)
