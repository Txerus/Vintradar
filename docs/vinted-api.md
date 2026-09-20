# API Vinted observée

Vinted ne publie pas de contrat pour les endpoints utilisés ici. Toutes les requêtes sont isolées dans `backend/app/vinted.py`, limitées en débit et couvertes par un repli.

## Catalogue

Validation réelle du 19 septembre 2026 depuis l’environnement de développement :

| Requête | Résultat réel |
|---|---|
| `https://api.vinted.fr/svc-catalogue/items` | HTTP 200, 48 annonces pour `lego` |
| `https://api.vinted.fr/svc-catalogue/items/{id}` | HTTP 404 `Route not found` |
| `https://api.vinted.fr/svc-items/items/{id}` | HTTP 404 `Route not found` |
| `https://api.vinted.fr/api/v2/items/{id}` | HTTP 404 `Route not found` |
| `https://www.vinted.fr/api/v2/items/{id}` | HTTP 404 HTML |
| `https://www.vinted.fr/items/{id}` | HTTP 200 HTML |

Le catalogue reçoit `X-Anon-Id` et `X-Csrf-Token` seulement quand la session anonyme les expose. Les diagnostics n’affichent jamais leur valeur. En cas d’échec, `/catalog` est lu et son JSON-LD `ItemList` sert de repli.

## Détail d’une annonce

Aucun endpoint JSON de détail fonctionnel n’a été trouvé parmi les variantes ci-dessus. Le chemin validé est donc la page publique `/items/{id}` :

- JSON-LD `Product` : titre, description, photos, marque, disponibilité et prix public ;
- données d’hydratation Next : attributs (taille, état, couleurs), fil de catégorie, identifiants, favoris/vues quand présents et résumé vendeur ;
- HTTP 404 : annonce `DELETED` ;
- `is_sold`/indisponibilité : `SOLD_CONFIRMED` ;
- `is_reserved` : traité comme `SOLD_CONFIRMED` pour les statistiques, conformément à la règle produit ;
- réponse inexploitable : `DISAPPEARED`, jamais « vendue » par supposition.

Les compteurs, dates, localisation et dernière connexion ne sont pas toujours publics. Le parseur renvoie alors `null` et `check_item.py` les liste comme indisponibles.

## Limites et maintenance

Les structures `self.__next_f` et les noms de sections sont internes et peuvent changer sans préavis. Les fixtures versionnées ne contiennent que des données représentatives minimales. Les captures live créées par `check_vinted.py` sont placées dans `tests/fixtures/vinted/live/` et ignorées par Git.
