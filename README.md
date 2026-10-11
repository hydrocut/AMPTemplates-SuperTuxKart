# AMPTemplates-SuperTuxKart — SuperTuxKart server for AMP

**AMP Generic Module** template for a **SuperTuxKart** server (<https://supertuxkart.net/>, source
<https://github.com/supertuxkart/stk-code>), the free and open-source kart racer.
Written for TeamKit, a free French game host, on 10 Oct 2026. CubeCoders ships no SuperTuxKart
template, and none was found in community template repositories.

> Résumé en français à la fin du fichier.

## Which version, and why

| Source | Version | Verdict |
|---|---|---|
| Latest stable (GitHub release `1.5`, 20 Oct 2025; supertuxkart.net download page) | **1.5** | what players run |
| Pre-releases (`1.5-rc2`, `preview`) | — | not used (`releases/latest` never points to them) |
| Debian 13 `supertuxkart` | 1.4+dfsg-5 | **too old**, not used |
| Debian `trixie-backports` | 1.5-2~bpo13+1 | not reachable: the AMP image has no backports source |

A server must run the same version as the players, so the template downloads the **official Linux
binary** (`SuperTuxKart-<version>-linux-x86_64.tar.gz`, ~735 MB, ~820 MB extracted) from the GitHub
release. With the *Game version* setting left empty, each **Update** follows
`https://github.com/supertuxkart/stk-code/releases/latest` (stable only) and downloads only when
the version changed; a fixed number (e.g. `1.5`) can be set instead. The official FAQ announces a
1.5.1 bug-fix release: it will be picked up by the next Update.

The archive is self-contained: `ldd` with its `lib/` folder shows **only glibc** from the system
(tested in `cubecoders/ampbase:debian`). Nothing to compile, no `apt` package for the game.
The data cannot be trimmed: without `data/sfx` the server aborts (`SFXManager: Could not read sound
effects XML file`), without `data/music` it logs errors — tested.

## Files

| File | Role |
|---|---|
| `supertuxkart.kvp`, `supertuxkart*.json`, `manifest.json` | the AMP template |
| `scripts/lancer-stk.sh` | install step (Update) and start script |
| `scripts/reglages_stk.py` | turns AMP settings into the server XML (checked, escaped) |
| `scripts/AMP_reglages.txt` | settings model; AMP renders it to `reglages-amp.txt` (`ConfigType: template`) |
| `verifier.py` | pre-push checks, must print `Tout est bon.` |

The three `scripts/` files are fetched from this repository (raw.githubusercontent.com, branch
`main`) at each Update, so **the repository must be public**.

Instance layout: `jeu/` (game, replaced as a whole on version change), `serveur.xml` (server config),
`accueil.txt` (welcome message), `bots-teamkit.txt` (bots to start, written by the script), `donnees/bots/` (bot client profile), `donnees/config/supertuxkart/config-0.10/` (saved STK session,
`serveur.log`), `donnees/supertuxkart/addons/` (add-ons).

## How the server is started

`/bin/bash lancer-stk.sh demarrer <port> <discovery port> <max players>`, which:

1. if the public list is requested and an STK account is set, logs it in the official way
   (`supertuxkart --init-user --no-graphics --login=… --password=…`, see `NETWORKING.md`): this saves
   a session that the server reuses. **`--no-graphics` is required**: without it `--init-user` tries to
   open a window and aborts in a container (tested). The password comes from an environment variable,
   is never written to disk or printed, and is unset before the game starts;
2. runs `reglages_stk.py`, which checks every value, writes `serveur.xml`, `accueil.txt` and
   `jeu/data/stk_config_teamkit.xml` (copy of `stk_config.xml` with the discovery port);
3. **`exec`s the game**: `supertuxkart --server-config=serveur.xml --network-console --log=nocolor
   --stk-config=stk_config_teamkit.xml`. The game *is* the AMP process: the AMP console goes straight
   to the game's network console, and AMP's SIGTERM stops it cleanly (`main_abort`, exit code 0, tested).

Details that cost a test each:

- **`--log=nocolor`**: otherwise every line reaches AMP wrapped in ANSI colour codes.
- **The network console spins at 100 % of a core once its stdin is closed** (`pollCommand` loop).
  The game's stdin is fed by a tiny relay (`cat`, then `sleep infinity`) started under
  `setpriv --pdeathsig KILL`: if AMP ever closes the console, stdin stays open; when the game exits,
  the relay goes too (tested: 1.5 % CPU after EOF, no leftover process).
- **Players joining during a race are not logged by name** (`ServerLobby: New player …` is only
  printed when no game is running), so they appear in AMP's list only if they joined in the lobby.
  Leaving is always logged.

## Settings exposed in AMP (French UI)

| AMP setting | Game key | Default |
|---|---|---|
| Port du jeu (Network tab) | `server-port` | 2759/UDP (STK default) |
| Port de découverte (Network tab) | `server-discovery-port` (in the `stk_config` copy) | 2757/UDP |
| Nom du serveur | `server-name` | `TeamKit.fr — Serveur francophone` |
| Message d'accueil | `motd` → `accueil.txt` | French TeamKit message with the Discord link |
| Nombre de joueurs (`$MaxUsers`) | `server-max-players` | 8 (2–20; STK warns above 8, 20 karts max) |
| Mot de passe du serveur | `private-server-password` | empty (public) |
| Mode de jeu | `server-mode` | 3 = race; 4 time trial, 0 grand prix, 1 GP time trial, 7 battle (free-for-all), 8 capture the flag, 6 soccer |
| Difficulté | `server-difficulty` | 1 = intermediate |
| Pistes par grand prix | `gp-track-count` | 3 |
| Football : gagner aux buts | `soccer-goal-target` | no (timed matches) |
| Serveur sans propriétaire | `owner-less` | **yes** (games start by themselves, nobody can kick) |
| Joueurs pour lancer une partie | `min-start-game-players` | 2 |
| Bots IA | `ai-handling` + a `--network-ai` client | no (see *AI bots*) |
| Nombre de bots | `--network-ai=<n>` | 3 (1–19, capped at players − 1) |
| Visibilité | `wan-server` | public list (falls back to IP-only, see below) |
| Compte STK : identifiant / mot de passe | `--init-user --login --password` | empty |
| Version du jeu | Update step | empty = latest stable |

`serveur.xml` is **updated, not overwritten**: only the keys above are replaced at each start; any other
key from `NETWORKING.md` (`kick-idle-player-seconds`, `hit-limit`, `capture-limit`, `time-limit-ctf`,
`max-ping`, `auto-end`, `live-spectate`…) can be edited by hand and is kept (tested). The game itself
writes the full file with every key on stop.

### Text values

The game reads its XML with irrXML, which decodes only the five named entities, then passes the
**server name** through `StringUtils::xmlDecode`, which reads raw bytes: a raw UTF-8 accent would be
mangled. `reglages_stk.py` therefore writes the name like the game's own `xmlEncode` (`é` → `&#xE9;`,
`"` → `&#x22;`). Tested: the LAN discovery answer returned `TeamKit.fr — Serveur "francophone" & Cie été`
intact. The **welcome message** goes to `accueil.txt`, which the game reads as UTF-8 when `motd` names a
`.txt` file: every character passes. The **server password** is not decoded by the game, so it is limited
to printable ASCII without spaces (the script refuses to start otherwise) and escaped with named
entities; `a&b"c<d`-style passwords were tested with a real client connection, including after the
game's own rewrite of the file, which puts the password back **unescaped** (handled: the script replaces
the whole line).

## Public list, STK account

**Being listed requires an STK online account** (`NETWORKING.md`: “You are required to have an stk online
account first”; free registration at <https://online.supertuxkart.net/register.php>). Without a valid
session, the game creates no server when `wan-server` is true (`main.cpp`: the WAN branch has no `else`), so the start script falls back to
a **LAN-type server reachable by IP** and says so in the console:

- *Visibilité = public* + account → listed in **En ligne > Réseau global** (Online > Global networking);
  players need to be signed in with an STK account there (that is how the game works).
- No account, failed login, or *Visibilité = IP* → players use **En ligne > Entrez l'adresse du serveur**
  (Online > Enter server address) and type `IP:port`. `NETWORKING.md` confirms a LAN server can be joined
  this way. If the discovery port is the default 2757, typing only the IP works too (the game asks
  2757 for the server port — tested).

**Not tested for real: the public listing**, because no STK account was created for the tests (creating
accounts is the owner's call). The code path is the official one; see the start-up steps for Kevin.
The STK team asks always-on public servers to be reachable directly (port forward): AMP opens the port.

## Console and player list

AMP console → game network console: `help`, `listpeers` (host id, IP, version), `kick <id>`, `kickall`,
`speedstats`, `quit` (`help`, `listpeers`, `speedstats`, `quit` tested). `kickban` bans only with the
SQLite server management, which this template does not enable: it then acts as `kick`.

Real lines (SuperTuxKart 1.5):

```
Sat Oct 10 17:53:44 2026 [info   ] STKHost: Listening has been started.                                  <- AppReadyRegex
Sun Oct 11 07:20:39 2026 [info   ] ServerLobby: New player Player with online id 0 from 127.0.0.1:60368 with SuperTuxKart/1.5 (Linux).   <- UserJoinRegex
Sun Oct 11 07:20:06 2026 [info   ] ServerLobby: New player Bot 1 with online id 0 from 127.0.0.1:59689 with AI.   <- NOT a player (AI bot)
Sun Oct 11 07:22:38 2026 [info   ] ServerLobby: Player disconnected                                       <- UserLeaveRegex
```

Lines ending in `with AI.` come from the AI bot client (its user agent is literally `AI`,
`client_lobby.cpp`): `UserJoinRegex` skips them, so bots never show up in AMP's player list and an
instance with only bots looks empty in AMP. Their `Bot N disconnected` lines still match the leave regex,
which is harmless (AMP removes a name it does not list).

`Console.ThrowawayMessageRegex` drops pure noise (`Message of type N received`, `New network player
controller`, `ProtocolManager … protocol has been started/terminated`, `Destroyed singleton`, the 17
`Asset N will be loaded` lines at start).

## AI bots

Optional, off by default. Official mechanism (`NETWORKING.md`, `ai-handling`: “auto add / remove AI
connected with network-ai=x, which will kick N - 1 bot(s) where N is the number of human players. Only use
this for non-GP racing server”):

- The start script launches, before handing over to the game, a supervisor (`lancer-stk.sh bots`) tied to
  the server with `setpriv --pdeathsig TERM`. It waits until the server's UDP port is bound, then runs a
  second, windowless SuperTuxKart: `--connect-now=127.0.0.1:<port> --network-ai=<n> --no-graphics`
  (plus `--server-password` when the server has one), with its own profile in `donnees/bots/` and the
  **same add-on folder as the server** (otherwise track voting would be limited to official tracks).
  Its log: `donnees/bots/config/supertuxkart/config-0.10/stdout.log`.
- If the bot client dies, it is restarted after 10, 20, 30, 40 s; after 5 failures in a row it gives up
  until the next server start (a client that ran 10 minutes resets the counter). Tested with `kill -9`.
- When the server stops, the supervisor and the bot client stop with it (tested: no leftover process,
  server exit code 0).
- **Modes**: `ServerLobby::supportsAI()` accepts only race (3) and time trial (4). In grand prix, battle,
  soccer and capture the flag the game ignores the AI client, so the script does not start it and prints
  `bots IA DESACTIVES : le mode … ne les accepte pas` (tested for 0, 6, 7, 8). `ai-handling` is written
  `true` only when bots really run.
- **Count**: with H humans the game races `n − H + 1` bots (`server_lobby.cpp`), none once H > n.
  Tested: n = 4 → 1 human + 4 bots, 2 humans + 3 bots; n = 7 → 1 human + 7 bots (8 karts). The script
  caps n at *max players − 1* so humans + bots fit the server's slots (12 asked with 8 slots → 7).
- **No human, no race**: the AI client is not counted as a player (`STKHost::updatePlayers` skips it with
  `ai-handling`), so `min-start-game-players` is never reached by bots alone — tested, no race started.
- **Visible side effect**: the in-game server list counts the bots in the lobby (`m_lobby_players`):
  an empty server with 4 bots shows **4/8** (measured on the LAN discovery answer). The public list
  receives the AI count separately (`current-ai`), how the client displays it was not checked.
- `ai-anywhere` is not needed: `127.0.0.1` is a LAN address for the game.
- **Instances created before this option** keep their old settings form (AMP copies the manifest at
  creation; *Fetch latest* does not update it). After an Update, `reglages-amp.txt` then contains a literal
  `{{BotsIA}}`: the script treats it as *no bots* and says so, the server still starts. To get the two new
  settings (and the new `UserJoinRegex` that hides bots), the instance's manifest and console keys must be
  refreshed, or the instance recreated.

## Add-on tracks and karts

The server loads add-ons from `donnees/supertuxkart/addons/tracks/<id>/` and `…/addons/karts/<id>/`
(`--disable-addon-*` not used). To add one: download it from <https://online.supertuxkart.net/addons.php>,
unzip it there with AMP's file manager, restart. Track voting only offers tracks **every** player in the
lobby has, so players must install the same add-on (in game: *Extensions* menu, or `/installaddon <id>`
in the lobby chat). `official-tracks-threshold` (0.7) and `official-karts-threshold` (1.0) keep out
players missing too many official tracks/karts. Add-ons are kept across game updates (outside `jeu/`).

## Resources (measured, 10 Oct 2026)

| | |
|---|---|
| RAM | ~35 MB idle; 85–135 MB during races (8 karts: 87 MB). **With bots**, add the bot client: ~35 MB idle, 57 MB (4 bots) to 87 MB (7 bots) in a race; measured peak server + bots = 80 + 87 MB with 1 human + 7 bots |
| CPU | ~2 % of a core during an 8-kart race on the TeamKit host; the bot client adds about as much |
| Disk | ~820 MB (`jeu/`), plus ~1.6 GB **peak** during a version change (old + new) |
| Start | < 1 s to the ready line (plus up to 20 s for the account login in public mode) |

## Before pushing

```
python verifier.py
```

Must print `Tout est bon.`: JSON, includes, ports, complete `Console.*` / `Limits.*` block, every
setting reaching exactly one place, enum lists matching the script, a render → script → *read like the
game* round trip (empty, spaces, accents, quotes, `&`, `<`, `{`, `#`, emoji; the raw-password rewrite),
refusals, kept hand-made keys, three distinct ports, download URLs, LF endings, launcher options,
`bash -n`, console regexes on real lines.

## Install in AMP

ADS → Configuration → Instance Deployment → **Configuration Repositories**: add
`hydrocut/AMPTemplates-SuperTuxKart:main`, save, **Fetch latest**. Create Instance →
**SuperTuxKart (TeamKit)** → **Update** (must print `SuperTuxKart 1.5 : binaire et bibliotheques OK.`)
→ **Start**.

## Credits

SuperTuxKart is free software (code: GPL-3.0-or-later; data under various free licenses, see `COPYING`) by the SuperTuxKart team. This repository only contains the
template; the game is downloaded from the official GitHub releases.

---

## Résumé en français

Template AMP pour un **serveur SuperTuxKart** (course de karts libre et gratuite). La version stable
est la **1.5** ; Debian 13 n'a que la 1.4 : le template télécharge donc le **binaire Linux officiel**
depuis GitHub, exactement la version des joueurs (réglage vide = dernière version stable, rien n'est
retéléchargé si elle est déjà là). Conteneur `cubecoders/ampbase:debian`. **Port 2759 en UDP**
(+ 2757 en UDP pour la découverte).

- **Liste publique** : il faut un **compte STK gratuit** (règle du jeu). Identifiant + mot de passe
  masqué dans AMP ; le mot de passe passe par une variable d'environnement, jamais dans un fichier ni
  dans le dépôt. Sans compte, le serveur démarre quand même et se rejoint par **En ligne > Entrez
  l'adresse du serveur** (`IP:port`).
- **Réglages en français** : nom (TeamKit par défaut), message d'accueil (TeamKit + Discord), nombre
  de joueurs, mot de passe, mode (course, contre-la-montre, grand prix, bataille, capture du drapeau,
  football), difficulté, pistes par grand prix, sans propriétaire, version.
- **Bots IA** (option, coupée par défaut) : un second SuperTuxKart sans affichage complète la course
  d'un joueur seul (course et contre-la-montre seulement ; coupés avec un message dans les autres modes).
  N bots avec 1 joueur, chaque joueur en plus remplace un bot ; sans humain, pas de course. Invisibles
  dans la liste des joueurs d'AMP, mais comptés dans la liste des serveurs du jeu (« 4/8 » à vide).
  Relancés s'ils tombent (4 fois), arrêtés avec le serveur. +35 à 90 Mo de RAM.
- **Addons** : déposés dans `donnees/supertuxkart/addons/tracks|karts/` ; les joueurs doivent avoir les
  mêmes (menu Extensions ou `/installaddon <id>`).
- **Testé en vrai** le 10 oct. 2026 dans un conteneur jetable : 35 Mo de RAM au repos, ~90 à 135 Mo en
  course, prêt en moins d'une seconde. **Pas testé : la liste publique** (aucun compte STK créé).
- Avant de pousser : `python verifier.py` doit répondre « Tout est bon. ».
