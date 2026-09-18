# VintRadar

VintRadar est une application iOS personnelle et un backend auto-hébergé de veille d'annonces. Elle n'est pas affiliée à Vinted.

## Architecture

- `backend/` : FastAPI, SQLAlchemy async, Alembic, worker de scan, scoring et sources de prix.
- `ios/` : SwiftUI/Swift 6, projet généré avec XcodeGen.
- `docs/` : décisions d'architecture.
- `.github/workflows/` : tests backend, build Docker, tests Swift et IPA non signée.

Le serveur est conçu pour être joint via Tailscale et exige en plus un Bearer token. Les notifications sont envoyées à ntfy et peuvent ouvrir `vintradar://item/{id}`.

## Serveur

1. Installer Docker et Docker Compose sur le serveur Linux.
2. Installer Tailscale sur le serveur et l'iPhone et connecter les deux au même tailnet.
3. Copier `.env.example` vers `.env`.
4. Remplacer impérativement `POSTGRES_PASSWORD` et `VINTRADAR_API_TOKEN`.
5. Adapter `NTFY_TOPIC`; `NTFY_TOKEN` est optionnel si l'instance ntfy n'impose pas d'authentification.
6. Lancer `docker compose up -d --build`.
7. Vérifier `http://ADRESSE-TAILSCALE:8000/health`.
8. Installer/configurer l'app ntfy iOS sur le topic choisi.

Ollama est optionnel : `docker compose --profile ollama up -d`. Les identifiants BrickLink restent vides tant que la source n'est pas configurée. Les variables sont documentées dans `.env.example`.

## API

OpenAPI est disponible sur `/docs`. Les routes métier demandent `Authorization: Bearer <VINTRADAR_API_TOKEN>`. `/health` reste public pour les healthchecks.

Le worker utilise un débit global prudent (`SCAN_GLOBAL_RPM=4` par défaut), une session anonyme et un backoff sur 403/429. L'API Vinted utilisée étant interne et non contractuelle, son adaptation est isolée dans `backend/app/vinted.py`. VintRadar n'automatise ni achat, ni message, ni action sur un compte.

## iOS et GitHub Actions

La cible de déploiement est **iOS 26**. La CI utilise explicitement le runner GitHub **`macos-latest`** et sélectionne explicitement **`/Applications/Xcode_26.6.app/Contents/Developer`** avec `xcode-select`. Au 18 septembre 2026, `macos-latest` pointe sur l'image macOS 26. Xcode 26.6 y est installé explicitement. Le workflow affiche les Xcode présents et le SDK sélectionné à chaque run. L'app ciblée iOS 26 fonctionne sur iOS 27.

Le workflow :
1. génère `VintRadar.xcodeproj` depuis `ios/project.yml`;
2. lance les tests Swift sur le simulateur iOS 27;
3. compile avec `CODE_SIGNING_ALLOWED=NO`;
4. crée `Payload/VintRadar.app`;
5. produit `VintRadar-unsigned.ipa`;
6. publie l’IPA comme artifact à chaque push;
7. sur `main`, met à jour la pré-release `latest`;
8. sur un tag `vX.Y.Z`, publie `VintRadar-X.Y.Z-unsigned.ipa` dans la Release correspondante.

Aucun Mac local n'est nécessaire.

### Produire une release

```bash
git tag v0.1.0
git push origin v0.1.0
```

Ouvrir ensuite Releases dans GitHub, télécharger `VintRadar-unsigned.ipa` sur l'iPhone et l'installer/re-signer avec SideStore/AltStore.

## Apple ID gratuit

VintRadar ne dépend pas d'APNs, iCloud ou App Groups. Les notifications passent par l'app ntfy. `BGTaskScheduler` ne doit être considéré que comme un rafraîchissement opportuniste; le worker serveur assure la détection. Une app signée avec un Personal Team doit être re-signée périodiquement selon les limites Apple/SideStore.

## Configuration initiale iPhone

Au premier lancement, saisir :
- l'URL FastAPI Tailscale, par exemple `http://100.x.y.z:8000`;
- le même `VINTRADAR_API_TOKEN` que dans `.env`.

L'app teste `/health`, enregistre la configuration localement puis charge le tableau de bord, les alertes et les annonces.

## Tests

Backend :

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

Docker :

```bash
docker build -t vintradar:test backend
```

Les tests iOS sont exécutés en CI, ce qui évite toute dépendance à Xcode local.

## Données et scoring

Les annonces utilisent cinq statuts : `ACTIVE`, `SOLD_CONFIRMED`, `DISAPPEARED`, `DELETED`, `UNKNOWN`. Une disparition n'est jamais assimilée automatiquement à une vente confirmée.

Le scoring robuste élimine les valeurs aberrantes par IQR puis classe le prix selon son percentile : DEAL <=20 %, GOOD <50 %, NORMAL <=75 %, EXPENSIVE >75 %. La confiance dépend du nombre de comparables.

## Sources de prix

L'interface `PriceSource` accueille Vinted interne, BrickLink, PriceCharting, eBay, Keepa et Back Market. Les connecteurs non configurés restent neutres et ne bloquent pas le backend. BrickLink requiert ses identifiants API dans `.env`.

## Secrets GitHub

Aucun secret Apple n'est nécessaire pour fabriquer l'IPA non signée. Le workflow de release utilise automatiquement `GITHUB_TOKEN`. Les secrets applicatifs restent uniquement dans le `.env` du serveur et ne doivent jamais être commités.

## Vérification Vinted en direct

Depuis la racine du dépôt :

```bash
docker compose run --rm api python scripts/check_vinted.py "lego"
```

Le script ouvre une session anonyme, affiche l’état du cookie, le code HTTP et la première annonce brute, compare les clés avec celles utilisées par le parser et sauvegarde le JSON dans `backend/tests/fixtures/vinted/`.

## Télécharger et installer la dernière IPA

La pré-release continue est disponible sur la page GitHub Releases : `https://github.com/Txerus/Vintradar/releases/tag/latest`. Son asset est `VintRadar-latest-unsigned.ipa`. Les versions stables utilisent `VintRadar-X.Y.Z-unsigned.ipa`.

Sur iPhone : ouvrir la Release dans Safari, télécharger l’IPA, l’ouvrir/partager vers SideStore, installer VintRadar puis le re-signer selon la cadence imposée par le compte Apple gratuit. Au premier lancement, renseigner l’URL Tailscale du backend et le token API.

La procédure de recette complète est dans `docs/installation.md`.
