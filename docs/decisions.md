# Décisions techniques

- XcodeGen : configuration légère et déterministe en CI.
- Deployment target iOS 26, soit une version majeure sous le SDK iOS 27.
- CI iOS : runner GitHub `xcode-27` et sélection explicite de `/Applications/Xcode_27.0.app`.
- Pas d'APNs, App Groups ou iCloud. ntfy porte les notifications.
- BGTaskScheduler est opportuniste et ne porte aucune garantie de temps réel.
- L'API Vinted non contractuelle est confinée à `backend/app/vinted.py`.
- Débit faible et backoff; aucun contournement de challenge anti-bot.
- SOLD_CONFIRMED et DISAPPEARED restent distincts : une disparition n'est pas une vente.
- Les sources externes partagent une interface. Les connecteurs non configurés retournent aucune cotation sans casser l'application.
