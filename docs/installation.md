# Recette de bout en bout

## 1. Démarrer le serveur
Copier `.env.example` vers `.env`, renseigner un mot de passe PostgreSQL, un `VINTRADAR_API_TOKEN` fort et le topic ntfy, puis :

```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

Le serveur et l'iPhone doivent être sur le même tailnet Tailscale.

## 2. Valider Vinted en direct
```bash
docker compose run --rm api python scripts/check_vinted.py "lego"
```
Le script doit obtenir une session anonyme, recevoir HTTP 200, afficher au moins une annonce et sauvegarder le JSON réel dans `backend/tests/fixtures/vinted/`.

## 3. Configurer l'iPhone
Installer la dernière IPA avec SideStore. Au premier lancement, saisir l'URL Tailscale du serveur et le même `VINTRADAR_API_TOKEN`, puis vérifier que le test de connexion réussit.

Installer ntfy sur l'iPhone et s'abonner au topic défini par `NTFY_TOPIC`.

## 4. Créer une alerte de recette
Depuis VintRadar, créer une alerte simple sur un terme actif (par exemple `lego`), sans prix minimal et avec une fréquence courte raisonnable. Vérifier côté API que l'alerte existe et côté worker qu'un scan est exécuté sans 401/403/429 persistant.

## 5. Valider la notification
Attendre qu'une annonce nouvelle soit enregistrée. La notification ntfy doit apparaître sur l'iPhone avec titre, prix et lien. Ouvrir la notification.

Résultat attendu : le deep link `vintradar://item/{id}` ouvre VintRadar et affiche la fiche correspondant à l'annonce. Le bouton Vinted doit ouvrir l'annonce source.

## 6. Critères de recette
La recette est réussie uniquement si le serveur est sain, le scan Vinted renvoie des annonces réelles, une nouvelle annonce est persistée, ntfy est effectivement reçu sur l'iPhone, le deep link ouvre VintRadar et la fiche affiche l'annonce correspondante.
