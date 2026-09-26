# Installation et exploitation

## 1. Préparer le LXC sur l’hôte Proxmox

Les commandes de cette section se lancent sur **l’hôte Proxmox** (`root@<nœud>`), pas dans le conteneur.

Créer un LXC Debian 12 **non privilégié**, relié en DHCP à `vmbr0`. Dans `/etc/pve/lxc/<CTID>.conf`, activer :

```ini
features: nesting=1,keyctl=1
lxc.cgroup2.devices.allow: c 10:200 rwm
lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
```

Si Docker/runc échoue avec `open sysctl net.ipv4.ip_unprivileged_port_start … permission denied`, ajouter :

```ini
lxc.apparmor.profile: unconfined
lxc.mount.entry: /dev/null sys/module/apparmor/parameters/enabled none bind,create=file
```

Puis redémarrer le LXC. Ce contournement désactive le confinement AppArmor du conteneur : il agrandit sa surface d’attaque. Réserver ce LXC à VintRadar, maintenir Debian/Docker à jour et ne pas y héberger de secrets ou services sans rapport.

## 2. Installer dans le conteneur

Les commandes suivantes se lancent **dans le LXC Debian** (`root@<conteneur>`).

```bash
apt update
apt install -y ca-certificates curl git qrencode
curl -fsSL https://get.docker.com | sh
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
git clone https://github.com/Txerus/Vintradar.git
cd Vintradar
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/health
```

Changer `POSTGRES_PASSWORD`, générer un long `VINTRADAR_API_TOKEN`, choisir un topic ntfy non devinable et renseigner les clés optionnelles. `REBRICKABLE_API_KEY` est gratuite. `PRICECHARTING_TOKEN`, les quatre `BRICKLINK_*` et `BRICKSET_API_KEY` restent vides si ces services ne sont pas utilisés.

Pour BrickLink, créer un compte, demander l’accès API dans les paramètres développeur BrickLink, attendre sa validation éventuelle, puis créer un Consumer Key/Secret et un Token Value/Secret. Le guide demande exclusivement les ventes réalisées (`guide_type=sold`) en Europe et en EUR.

## 3. Tailscale, MagicDNS et HTTPS

Dans l’administration Tailscale, activer MagicDNS et les certificats HTTPS. Dans le LXC :

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve --bg --https=8443 http://127.0.0.1:8080
tailscale serve status
```

Configurer `NTFY_BASE_URL=https://<nom-magicdns>:8443` dans `.env`, puis relancer `docker compose up -d`. `NTFY_UPSTREAM_BASE_URL=https://ntfy.sh` est indispensable aux notifications instantanées iOS de l’instance auto-hébergée.

Sur l’iPhone, activer **Use Tailscale DNS**. Sans cette option, l’app peut afficher « a server with the specified hostname could not be found » alors que le tunnel est connecté.

L’URL VintRadar à saisir dans l’app est `https://<nom-magicdns>`. L’URL ntfy est `https://<nom-magicdns>:8443`.

## 4. Onboarding et QR du token

Dans le LXC :

```bash
set -a
. ./.env
set +a
./backend/scripts/show_token_qr.sh
```

Scanner le QR depuis l’iPhone ou copier le token. Le script n’envoie le secret nulle part ; il le rend uniquement dans le terminal.

## 5. Recette Vinted réelle

La CI valide les parseurs sur des fixtures sans contacter Vinted. La validation depuis l’IP réelle du serveur est :

```bash
docker compose run --rm api python scripts/check_vinted.py lego
```

Sortie attendue : cookie anonyme présent, URL `https://api.vinted.fr/svc-catalogue/items?...`, HTTP 200, noms d’en-têtes sans leurs valeurs, puis `Listings: 48` (le nombre peut varier). La capture est écrite sous `tests/fixtures/vinted/live/`, dossier ignoré par Git.

Choisir ensuite un identifiant renvoyé :

```bash
ITEM_ID=$(python - <<'PY'
import json, pathlib
p=max(pathlib.Path("backend/tests/fixtures/vinted/live").glob("catalog_*.json"))
print(json.loads(p.read_text())["items"][0]["id"])
PY
)
docker compose run --rm api python scripts/check_item.py "$ITEM_ID"
```

Sortie attendue : URL `https://www.vinted.fr/items/<id>`, HTTP 200, champs JSON-LD/hydratation parsés et liste explicite des champs indisponibles. Une valeur absente est signalée ; elle n’est jamais inventée.

Après au moins un scan, trouver un identifiant interne et expliquer son score :

```bash
LISTING_ID=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-vintradar}" -d "${POSTGRES_DB:-vintradar}" -Atc 'select id from listings order by first_seen_at desc limit 1')
docker compose run --rm api python scripts/explain_listing.py "$LISTING_ID"
```

Sortie attendue : titre, prix total et JSON contenant `product`, `condition_segment`, `window_days: 90`, décompte des exclusions, quantiles et `comparable_ids`, ou une raison explicite si `evaluated` vaut `false`.

## 6. Premier scan et notifications

Le bootstrap d’une nouvelle alerte collecte cinq pages en respectant la cadence globale et n’envoie aucune notification. Les scans suivants enrichissent les nouvelles annonces avant filtrage, score et notification. Le seuil « Toutes les annonces » notifie aussi un prix non évalué en donnant sa raison ; « Affaires uniquement » exige un score `DEAL`.

Installer ntfy sur l’iPhone, ajouter l’URL du serveur ntfy Tailscale et s’abonner au topic. Le bouton « Voir sur Vinted » utilise `https://www.vinted.fr/items/<id>`, lien universel qui ouvre l’app Vinted si elle est installée.

## 7. Mettre à jour

Dans le dépôt du LXC :

```bash
git pull
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 migrate api worker
```

Le service `migrate` doit terminer avec le code 0 avant le démarrage de l’API et du worker. Télécharger ensuite `VintRadar-latest-unsigned.ipa` depuis la pré-release `latest`, puis l’installer et le re-signer dans SideStore.

Depuis la migration `0005`, `migrate` lance automatiquement `scripts/rescore_all.py --pending` après Alembic. Le premier redémarrage v0.2.1 peut donc durer : chaque annonce active héritée est relue à la cadence Vinted, puis reclassée et recalculée avant le démarrage de l’API. La progression apparaît sous la forme d’une ligne JSON `rescore_all` dans les logs de `migrate`.

Pour forcer ultérieurement un recalcul complet, y compris des annonces déjà à jour :

```bash
docker compose run --rm api python scripts/rescore_all.py
```
