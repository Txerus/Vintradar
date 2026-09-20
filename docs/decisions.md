# Décisions techniques

- XcodeGen : configuration légère et déterministe en CI.
- Deployment target iOS 26, soit une version majeure sous le SDK iOS 27.
- CI iOS : runner GitHub `macos-latest` et sélection explicite de `/Applications/Xcode_26.6.app`; l'image est diagnostiquée avant le build.
- Pas d'APNs, App Groups ou iCloud. ntfy porte les notifications.
- BGTaskScheduler est opportuniste et ne porte aucune garantie de temps réel.
- L'API Vinted non contractuelle est confinée à `backend/app/vinted.py`.
- Débit faible et backoff; aucun contournement de challenge anti-bot.
- SOLD_CONFIRMED et DISAPPEARED restent distincts : une disparition n'est pas une vente.
- Les sources externes partagent une interface. Les connecteurs non configurés retournent aucune cotation sans casser l'application.
- V0.2 : `listings.external_id` est unique globalement et `alert_listings` porte l’appartenance ainsi que la date de première détection par alerte. Favoris, vu et masqué restent attachés à l’annonce globale.
- Le prix statistique est `total_item_price` fourni par Vinted (article + protection acheteur). La livraison reste affichée séparément et n’est pas ajoutée une seconde fois au score.
- Une annonce réservée vérifiée dans sa fiche est classée `SOLD_CONFIRMED`, selon la règle fonctionnelle demandée. Une fiche encore active reste active même si elle a quitté une page de recherche ; une réponse inexploitable devient `DISAPPEARED`.
- Le détail Vinted utilise la page publique `/items/{id}` : les variantes JSON testées le 19/09/2026 répondaient toutes 404. Le JSON-LD est prioritaire, puis les données d’hydratation complètent les attributs.
- La note vendeur `feedback_reputation` observée sur une échelle 0–1 est convertie sur 5 pour l’affichage. Une valeur déjà supérieure à 1 est conservée.
- Un produit générique peut être indexé, mais aucun badge n’est rendu si le produit, la catégorie ou le segment d’état n’atteint pas la confiance minimale.
- Les références externes restent séparées de la médiane Vinted. Un écart supérieur à 40 % force la confiance à « faible » au lieu de fusionner les sources.
- Le cache des connecteurs optionnels et des recherches ciblées dure 24 h dans le processus worker. Une relance du conteneur peut donc provoquer un nouveau contrôle, toujours soumis au débit global.
- L’aperçu d’alerte interroge une page et signale un budget dépassé ; la fréquence minimale est fixée à deux minutes.
