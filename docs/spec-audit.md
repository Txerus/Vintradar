# Audit de la spécification VintRadar

Cet audit décrit le comportement prouvé par le code et les tests. Une classe, une table ou un écran vide ne compte pas comme une fonction terminée.

| Exigence | État | Preuve ou limite exacte |
|---|---|---|
| PostgreSQL et Alembic | Implémenté | Les migrations `0001` à `0003` sont transactionnelles et reproductibles. La CI part d'un service PostgreSQL 17 vide, exécute `alembic upgrade head`, puis inspecte les huit tables et les colonnes métier. |
| Démarrage Docker | Implémenté | Le service Compose `migrate` doit terminer avec succès avant le démarrage de l'API et du worker. Le Dockerfile définit `PYTHONPATH=/app`. |
| Authentification Bearer | Implémenté | Toutes les routes métier et `/auth/check` sont protégées. `/health` reste public uniquement pour le healthcheck. Test API succès/401. |
| Alertes | Implémenté | Création, lecture, modification, suppression, pause, termes inclus/exclus, prix, filtres `attribute_ids`, fréquence et seuil. Validation des prix, seuils et fréquences testée. |
| Recherche Vinted | Implémenté, dépendant d'une API interne | Utilise `https://api.vinted.fr/svc-catalogue/items`, la session anonyme, `X-Anon-Id`, `X-Csrf-Token` lorsqu'il est exposé, et les filtres `attribute_ids[...]`. Tests avec transport simulé. Le script live affiche URL, noms d'en-têtes et corps d'erreur sans révéler les tokens. |
| Repli de collecte | Implémenté | En cas d'échec API, lecture de `/catalog` et extraction du JSON-LD `ItemList`, avec test de fixture. Ce repli HTML remplace le repli Playwright initialement envisagé. |
| Premier scan | Implémenté | Les annonces existantes sont persistées sans notification. Une annonce nouvelle lors d'un scan ultérieur peut notifier. Test d'intégration worker sur deux scans. |
| Scoring | Implémenté | `robust_score` est exécuté par le worker sur le coût article + frais disponibles. Label, percentile, médiane, taille d'échantillon et confiance sont stockés et renvoyés à iOS. Tests du score, de la persistance et du seuil. |
| Seuil de notification | Implémenté | `DEAL`, `GOOD` et `NORMAL` sont ordonnés ; une notification n'est envoyée que si le score atteint le seuil. Les affaires reçoivent le préfixe 🔥. Test worker. |
| Notifications ntfy | Implémenté | Publication JSON sur la racine ntfy avec `topic`, `title`, `message`, `click` et `actions`. Les accents et emojis ne sont jamais placés dans des en-têtes HTTP. Test avec transport HTTP simulé. |
| Cadence worker | Implémenté | Le débit global et `scan_minutes` par alerte sont appliqués. Tests des alertes en pause et de l'échéance temporelle. |
| Normalisation produits | Implémenté | Les annonces alimentent `products`, `listing_product_match` et `price_stats`; LEGO/iPhone ont une clé canonique et les autres une clé normalisée. Test d'intégration worker. |
| Historique | Implémenté | Un snapshot est créé à la découverte et à chaque variation de prix/statut observée. Route et affichage Swift Charts testés côté API/compilation. |
| Statuts | Partiel, par sécurité | Les cinq statuts sont stockables, mais le collecteur ne déduit pas `SOLD_CONFIRMED`, `DELETED` ou `DISAPPEARED` de l'absence dans une page limitée à 48 résultats. Une telle déduction serait fausse sans vérification individuelle fiable. |
| Sources de prix externes | Partiel | L'interface de plugins et les emplacements de configuration existent. BrickLink, PriceCharting, eBay, Keepa et Back Market ne produisent pas de prix sans connecteur et identifiants opérationnels ; ils ne participent pas au score actuel. |
| App iOS : onboarding | Implémenté | Teste désormais `/auth/check`, donc une mauvaise URL ou un mauvais token ne valide plus l'onboarding. |
| App iOS : accueil | Implémenté | Santé serveur, dernier scan, indicateurs, recherche globale et meilleures affaires. |
| App iOS : alertes | Implémenté | CRUD, pause/reprise, seuil, cadence, budget et navigation vers les annonces. |
| App iOS : annonces/favoris | Implémenté | Recherche, tri, favoris, vu, masqué, cache hors ligne et synchronisation des drapeaux. |
| App iOS : détail | Implémenté selon les données disponibles | Galerie, prix total, score expliqué, comparables, historique, caractéristiques, description, vendeur et lien source. Les blocs galerie/vendeur restent naturellement vides si Vinted ne fournit pas ces champs. |
| Cache hors ligne iOS | Implémenté | SwiftData stocke les annonces et drapeaux ; migration automatique depuis l'ancien cache `UserDefaults`. Test SwiftData en mémoire. |
| Deep links | Implémenté | `vintradar://item/{id}` et `vintradar://alert/{id}`. |
| Interface adaptative | Implémenté | SwiftUI natif, Charts, composants Liquid Glass, couleurs sémantiques, VoiceOver et cible universelle iPhone/iPad. Compilation et tests Xcode en CI. |
| Achat ou messagerie automatisés | Absent volontairement | Hors périmètre : VintRadar observe uniquement et n'effectue aucune action sur un compte Vinted. |

## Limites qui nécessitent une preuve externe

- L'API Vinted est privée et non contractuelle. Les tests garantissent le format des requêtes et les replis, pas la disponibilité future du service.
- La réception d'une notification sur un iPhone réel dépend du serveur ntfy et de l'abonnement du téléphone. Le transport JSON est testé, mais pas un appareil externe depuis la CI.
- Les connecteurs de prix tiers nécessitent des comptes, contrats ou clés API propres à chaque fournisseur avant de pouvoir être qualifiés d'opérationnels.
