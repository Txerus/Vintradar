# API Vinted observée

Vinted ne publie pas de contrat pour les endpoints utilisés ici. Toutes les requêtes sont isolées dans `backend/app/vinted.py`, limitées en débit et couvertes par un repli.

## Catalogue

Validation réelle renouvelée le 26 septembre 2026 avec l’annonce active
`10144942217` (« Overcooked ! Special Édition ») :

| Requête | Résultat réel |
|---|---|
| `https://api.vinted.fr/svc-catalogue/items` | HTTP 200, 48 annonces pour `lego` |
| `https://api.vinted.fr/svc-catalogue/items/{id}` | HTTP 404 `Route not found` |
| `https://api.vinted.fr/svc-item/items/{id}` | HTTP 404 `Route not found` |
| `https://api.vinted.fr/svc-items/items/{id}` | HTTP 404 `Route not found` |
| `https://api.vinted.fr/svc-item-details/items/{id}` | HTTP 404 `Route not found` |
| `https://api.vinted.fr/svc-item-details/item/{id}` | HTTP 404 `Route not found` |
| `https://api.vinted.fr/api/v2/items/{id}` | HTTP 404 `Route not found` |
| `https://api.vinted.fr/api/v2/items/{id}/details` | HTTP 403 |
| `https://www.vinted.fr/api/v2/items/{id}` | HTTP 404 HTML |
| `https://www.vinted.fr/api/v2/items/{id}/details` | HTTP 403 HTML |
| `https://www.vinted.fr/web/gateway/items/{id}` | HTTP 404 `Route not found` |
| `https://www.vinted.fr/web/gateway/item-details/{id}` | HTTP 404 `Route not found` |
| `https://www.vinted.fr/items/{id}` | HTTP 200, redirection vers l’URL canonique, 2 108 629 octets |

Le catalogue reçoit `X-Anon-Id` et `X-Csrf-Token` seulement quand la session anonyme les expose. Les diagnostics n’affichent jamais leur valeur. En cas d’échec, `/catalog` est lu et son JSON-LD `ItemList` sert de repli.

## Détail d’une annonce

Aucun endpoint JSON complet de détail n’a été trouvé parmi les variantes observées.
Le JavaScript officiel utilise bien le proxy `https://www.vinted.fr/web/gateway`
pour des greffons séparés (`/item-details/plugins/{id}/{feature}` et
`/item-details/more-items/{id}`), mais aucun de ces chemins ne fournit la fiche
complète. Un nom de greffon invalide répond HTTP 400 `INVALID_FEATURE`.

Le client sonde une fois par session les variantes de détail les plus probables,
puis mémorise leur indisponibilité. Le repli validé est la page publique
`/items/{id}` :

- JSON-LD `Product` : titre, description, photos, marque, disponibilité et prix public ;
- données d’hydratation Next/RSC `self.__next_f` : description, galerie complète,
  attributs (taille, état, couleurs), fil de catégorie, identifiants, favoris/vues
  quand présents et résumé vendeur ;
- HTTP 404 : annonce `DELETED` ;
- `is_sold`/indisponibilité : `SOLD_CONFIRMED` ;
- `is_reserved` : traité comme `SOLD_CONFIRMED` pour les statistiques, conformément à la règle produit ;
- réponse inexploitable : `DISAPPEARED`, jamais « vendue » par supposition.

Sur l’annonce de contrôle, le parseur a réellement obtenu : titre, description de
169 caractères, 3 photos, état « Très bon état », catégorie `3026` avec le chemin
« Électronique › Jeux vidéo et consoles › Jeux », 0 favori et une note vendeur de
4,9. L’URL finale après redirection était
`https://www.vinted.fr/items/10144942217-overcooked-special-edition`.

Les compteurs, dates, localisation et dernière connexion ne sont pas toujours publics. Le parseur renvoie alors `null` et `check_item.py` les liste comme indisponibles.

Chaque requête de détail conserve le statut HTTP, l’URL demandée, l’URL finale
après redirections et, en cas d’erreur ou de parsing impossible, les 500 premiers
caractères de la réponse. `scripts/diagnose_enrichment.py` rejoue les échecs sans
les modifier ; l’option `--apply` persiste les enrichissements redevenus valides.

## Limites et maintenance

Les structures `self.__next_f` et les noms de sections sont internes et peuvent changer sans préavis. Les fixtures versionnées ne contiennent que des données représentatives minimales. Les captures live créées par `check_vinted.py` sont placées dans `tests/fixtures/vinted/live/` et ignorées par Git.
