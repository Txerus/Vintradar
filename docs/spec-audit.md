# Audit de la spécification VintRadar v0.2

État fondé sur le code et les tests du dépôt. « Partiel » signale explicitement ce qui dépend d’une API privée, d’un identifiant absent ou d’une validation sur le serveur réel.

## A — Corrections du score

| Exigence | État | Preuve / limite |
|---|---|---|
| Pool par produit et état | Fait | `score_listing` sélectionne la clé canonique et le segment ; tests produit/état et jeu/console. |
| Exclusion de soi par identifiant | Fait | Test avec deux annonces au même prix : l’autre reste comparable. |
| Fenêtre glissante | Fait | 90 jours sur `first_seen_at` ; test à 91 jours. `PriceStat.window_days=90`. |
| Numéros LEGO fiables | Fait | Contexte LEGO/set/réf/n°, rejet année/pièces/prix ; validation Rebrickable ou Brickset si clé, confiance réduite sinon. Tests vrais/faux positifs. |
| Repli générique structuré | Fait | Marque + catégorie + tokens modèle + taille pour catégories pertinentes. Une confiance insuffisante n’affiche aucun badge. |
| Prix total Vinted | Fait | `total_item_price` est stocké et scoré ; article, protection et livraison restent séparés à l’écran. |
| Seuil ALL et score absent | Fait | API et iOS proposent quatre seuils ; `ALL` notifie avec « prix non évalué », `DEAL` le bloque. Tests. |
| Filtres mots entiers | Fait | Normalisation sans accents, ensembles de mots, exclusions réappliquées à la description enrichie. Test `lego`/`legolas`. |

## B — Base de connaissance et comparables

| Exigence | État | Preuve / limite |
|---|---|---|
| Annonce unique + N–N alertes | Fait | Migration `0004`, contrainte unique et `alert_listings`. La CI migre deux doublons legacy et exige 1 annonce + 2 liens. |
| Connaissance inter-alertes | Fait | Le score interroge toutes les annonces liées au produit, sans filtre d’alerte. |
| Segments d’état | Fait | Cinq segments, aucun mélange neuf/occasion ; repli occasion/neuf séparé. Tests. |
| Exclusions, IQR, quantiles | Fait | Drapeaux normaliseur, IQR, médiane/P20/P75/percentile et causes d’exclusion stockées. Tests. |
| Republications | Fait | Vendeur + titre normalisé, observation au statut le plus fort conservée. Test. |
| Pondération des statuts | Fait | Vente confirmée 3×, active 1×, disparue/inconnue faible. |
| Repli hiérarchique | Fait | Même produit/état, états voisins, puis marque+catégorie avec confiance faible. Tests des niveaux/libellés. |
| Jeux et consoles | Fait | Normaliseurs plateforme/titre/édition/capacité/pack et drapeaux emballage. Variantes Pokémon testées ; console exclue du pool jeu. |
| Sources externes | Partiel vérifiable | Connecteurs Rebrickable, PriceCharting+BCE, BrickLink OAuth 1.0 et Brickset implémentés, cache 24 h, désactivation sans clé, tests HTTP simulés. Appels réels non vérifiés faute d’identifiants. |
| Recherche ciblée | Fait | Déclenchée sous 6 observations, stockée hors lien d’alerte, `targeted_at` persiste le cache 24 h et le débit Vinted est partagé. |
| Bootstrap cinq pages | Fait | Première alerte demande 5 pages via le même limiteur et reste silencieuse. |

## C — Fiche complète

| Exigence | État | Preuve / limite |
|---|---|---|
| Découverte endpoint détail | Fait | Résultats réels documentés dans `docs/vinted-api.md` ; trois endpoints JSON 404, page publique 200. |
| Parseur détail | Fait | JSON-LD + hydratation : description, photos, marque, taille, état, catégorie, couleurs, compteurs et vendeur. Fixture de forme réelle testée. Les champs non publics restent `null`. |
| Profil vendeur 24 h | Partiel | Résumé public de la page article stocké dans `seller_profiles` avec TTL 24 h. Aucun second endpoint profil stable n’a été trouvé/validé ; ancienneté/localisation/connexion peuvent manquer. |
| File, débit, backoff | Fait | Enrichissements séquentiels avant score dans la file logique du scan ; limiteur partagé et backoff 403/429. État de file exposé. Test notification après enrichissement. |
| Une fois sauf prix modifié | Fait | `enriched_at` + `enrichment_price`. |
| Historique intérêt | Fait | Favoris/vues dans `listing_snapshots` et API ; iOS génère « +12 favoris en 2 h ». Test Swift dédié. |

## D — Pourquoi ce prix ?

| Exigence | État | Preuve / limite |
|---|---|---|
| Explication JSON stockée | Fait | Décomposition, reconnaissance, état, repli, fenêtre, exclusions, quantiles, confiance et IDs. |
| Endpoint pricing | Fait | `GET /listings/{id}/pricing` renvoie explication + comparables. Test API. |
| Script terminal | Fait | `scripts/explain_listing.py`. |
| Phrase, graphique, comparables iOS | Fait | Phrase française testée, Swift Charts avec P20/médiane/position et liste tappable. Validation de compilation confiée à la CI macOS. |
| Correction/exclusion produit | Fait | `PUT /listings/{id}/product` et feuille iOS ; correction manuelle persistée et test API. Recalcul appliqué au scan suivant. |
| Raison cartes/ntfy | Fait | Écart à médiane + nombre ; raison explicite si non évalué. |
| Fiche et vendeur iOS | Fait selon données | Galerie, description, catégorie, date, compteurs et bloc vendeur affichent tous les champs disponibles, sans valeur inventée. |

## E — Suivi des ventes

| Exigence | État | Preuve / limite |
|---|---|---|
| Vérification individuelle | Fait | Jusqu’à trois absentes par scan sont relues à faible cadence. Active reste active ; vendue/réservée → `SOLD_CONFIRMED` ; 404 → `DELETED` ; erreur inexploitable → `DISAPPEARED`. Test des trois issues. |
| Priorité vente confirmée | Fait | Pondération supérieure et statut rendu dans les comparables. |

## F — Exploitation et produit

| Exigence | État | Preuve / limite |
|---|---|---|
| Restart Compose | Fait | `unless-stopped` sur postgres/api/worker/ntfy, absent de migrate. |
| ntfy auto-hébergé iOS | Fait | `NTFY_BASE_URL` et `NTFY_UPSTREAM_BASE_URL` dans exemple/Compose. |
| Guide Proxmox/Tailscale | Fait | LXC non privilégié, tun, AppArmor et contrepartie, contexte hôte/conteneur, MagicDNS/HTTPS/DNS iPhone. |
| QR et mise à jour | Fait | Script `qrencode` et procédure `git pull && docker compose up -d --build` + SideStore. |
| Fixtures live ignorées | Fait | `tests/fixtures/vinted/live/` dans `.gitignore`. |
| Log structuré et worker/status | Fait | Ligne JSON par scan et état erreur/403/429/file ; accueil iOS les affiche. |
| Lien universel | Fait | `https://www.vinted.fr/items/{id}` côté backend, ntfy et iOS. |
| Aperçu éditeur/budget | Fait | Endpoint, debounce iOS, quatre seuils, minimum 2 minutes et avertissement. |

## G — Tests et livraison

| Exigence | État | Preuve / limite |
|---|---|---|
| Tests backend | Fait localement | 27 tests réussis le 20/09/2026 en 1,81 s ; la valeur finale CI est à reporter après push. |
| Migration PostgreSQL | En attente CI | Docker absent localement ; job GitHub avec PostgreSQL 17, fusion de doublons, `alembic check` et inspection de schéma. |
| Tests/build iOS | En attente CI | Runner macOS/Xcode requis. Le workflow vérifie tests, sources, binaire, Assets.car, icônes, IPA et SHA-256. |
| Appels live privés | À valider serveur | `check_vinted.py`, `check_item.py` et `explain_listing.py` sont fournis avec commandes/sorties attendues dans `docs/installation.md`. |

## Hors périmètre volontaire

VintRadar n’achète pas, ne réserve pas et n’envoie aucun message sur un compte Vinted.
