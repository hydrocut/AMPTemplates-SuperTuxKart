#!/bin/bash
# lancer-stk.sh - pose par le template AMP TeamKit (recree a chaque Update).
#
#   lancer-stk.sh installer [version]                       etape d'Update
#   lancer-stk.sh demarrer <port> <port_decouverte> <joueurs_max>   ligne de commande d'AMP
#
# installer : telecharge le binaire Linux OFFICIEL de SuperTuxKart (GitHub
#   supertuxkart/stk-code), le meme que celui des joueurs. Version vide = la
#   derniere version stable publiee. Ne retelecharge rien si elle est deja la.
# demarrer : connecte le compte STK si la liste publique est demandee, ecrit
#   serveur.xml avec les reglages d'AMP, puis REMPLACE ce script par le jeu (exec) :
#   la console d'AMP arrive directement sur la console reseau du jeu, et le
#   SIGTERM d'AMP arrete le serveur proprement.
cd "$(dirname "$0")" || exit 1
ICI="$PWD"
JEU="$ICI/jeu"
BIN="$JEU/bin/supertuxkart"
DEPOT="supertuxkart/stk-code"
export LANG=C.UTF-8 LC_ALL=C.UTF-8

# Tout ce que le jeu ecrit reste dans le dossier de l'instance :
#   donnees/config/supertuxkart/config-0.10/  compte STK enregistre, journal serveur.log
#   donnees/supertuxkart/addons/              pistes et karts additionnels (addons)
environnement() {
  local racine="$1"
  export LD_LIBRARY_PATH="$racine/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export SUPERTUXKART_DATADIR="$racine"
  export SUPERTUXKART_ASSETS_DIR="$racine/data/"
  export XDG_CONFIG_HOME="$ICI/donnees/config"
  export XDG_DATA_HOME="$ICI/donnees"
  export XDG_CACHE_HOME="$ICI/donnees/cache"
  export HOME="$ICI/donnees"
  mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME/supertuxkart/addons/tracks" "$XDG_DATA_HOME/supertuxkart/addons/karts"
}

# Verifie un dossier de jeu : bibliotheques presentes et numero de version.
controler() {
  local racine="$1" absentes version
  [ -x "$racine/bin/supertuxkart" ] || { echo "ERREUR : $racine/bin/supertuxkart absent."; return 1; }
  absentes=$(LD_LIBRARY_PATH="$racine/lib" ldd "$racine/bin/supertuxkart" 2>/dev/null | grep "not found")
  if [ -n "$absentes" ]; then
    echo "ERREUR : bibliotheques manquantes pour supertuxkart :"
    echo "$absentes"
    return 1
  fi
  version=$( (environnement "$racine"; timeout 30 "$racine/bin/supertuxkart" --version --log=nocolor </dev/null 2>&1) | sed -n 's/.*main: SuperTuxKart, \(.*\)\.$/\1/p' | head -n 1)
  [ -n "$version" ] || { echo "ERREUR : supertuxkart --version ne repond pas."; return 1; }
  echo "SuperTuxKart $version : binaire et bibliotheques OK."
}

installer() {
  local voulue="$1" installee url ext z nouveau
  set -o pipefail
  installee=$(cat "$JEU/VERSION-TEAMKIT" 2>/dev/null)
  if [ -z "$voulue" ]; then
    # La page « latest » de GitHub ne pointe jamais sur une pre-version (rc, beta).
    voulue=$(curl -fsSI --max-time 30 "https://github.com/$DEPOT/releases/latest" | tr -d '\r' | sed -n 's#^[Ll]ocation: .*/releases/tag/##p' | tail -n 1)
    if [ -z "$voulue" ]; then
      echo "ERREUR : impossible de savoir quelle est la derniere version stable (GitHub injoignable ?)."
      if [ -x "$BIN" ]; then
        echo "Le jeu deja installe ($installee) est garde."
        exit 0
      fi
      exit 1
    fi
    echo "Derniere version stable de SuperTuxKart : $voulue (installee : ${installee:-aucune})."
  fi
  if [[ ! "$voulue" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?(-[A-Za-z0-9]+)?$ ]]; then
    echo "ERREUR : version '$voulue' invalide. Exemple : 1.5 (vide = la derniere version stable)."
    exit 1
  fi
  if [ -x "$BIN" ] && [ "$installee" = "$voulue" ]; then
    echo "SuperTuxKart $voulue deja installe : rien a telecharger."
    controler "$JEU"
    exit $?
  fi
  url=""
  for ext in tar.gz tar.xz; do
    if curl -fsIL --max-time 30 -o /dev/null "https://github.com/$DEPOT/releases/download/$voulue/SuperTuxKart-$voulue-linux-x86_64.$ext"; then
      url="https://github.com/$DEPOT/releases/download/$voulue/SuperTuxKart-$voulue-linux-x86_64.$ext"
      break
    fi
  done
  if [ -z "$url" ]; then
    echo "ERREUR : pas d'archive Linux x86_64 pour la version $voulue sur https://github.com/$DEPOT/releases"
    exit 1
  fi
  case "$url" in *.xz) z=-J ;; *) z=-z ;; esac
  nouveau="$ICI/jeu.nouveau"
  rm -rf "$nouveau" "$ICI/jeu.ancien"
  mkdir -p "$nouveau"
  echo "Telechargement et extraction de $url (environ 750 Mo, 820 Mo une fois extrait)..."
  if ! curl -fsSL --retry 3 --connect-timeout 30 "$url" | tar -x $z -C "$nouveau" --strip-components=1 --no-same-owner; then
    rm -rf "$nouveau"
    echo "ERREUR : telechargement ou extraction rate (place disque ? reseau ?). L'ancienne version est gardee."
    exit 1
  fi
  if ! controler "$nouveau"; then
    rm -rf "$nouveau"
    echo "ERREUR : l'archive telechargee ne fonctionne pas. L'ancienne version est gardee."
    exit 1
  fi
  echo "$voulue" > "$nouveau/VERSION-TEAMKIT"
  # Bascule : l'ancien dossier n'est efface qu'une fois le nouveau en place.
  [ -d "$JEU" ] && mv "$JEU" "$ICI/jeu.ancien"
  mv "$nouveau" "$JEU"
  rm -rf "$ICI/jeu.ancien"
  echo "SuperTuxKart $voulue installe dans jeu/ (les joueurs doivent avoir la meme version)."
}

demarrer() {
  local port="$1" decouverte="$2" joueurs="$3" visibilite wan sortie
  if [ ! -x "$BIN" ]; then
    echo "ERREUR : SuperTuxKart n'est pas installe (jeu/bin/supertuxkart absent) : lance Update."
    exit 1
  fi
  if [ ! -f reglages_stk.py ]; then
    echo "ERREUR : reglages_stk.py absent : lance Update."
    exit 1
  fi
  environnement "$JEU"
  echo "TeamKit : SuperTuxKart $(cat "$JEU/VERSION-TEAMKIT" 2>/dev/null) dans le dossier jeu/."

  visibilite=$(sed -n 's/^visibilite=//p' reglages-amp.txt 2>/dev/null | head -n 1 | tr -d '\r')
  wan=non
  if [ "$visibilite" = "public" ]; then
    if [ -z "$STK_IDENTIFIANT" ] || [ -z "$STK_MOT_DE_PASSE" ]; then
      echo "TeamKit : ATTENTION, liste publique demandee mais aucun compte STK (identifiant + mot de passe) dans l'onglet Configuration d'AMP."
      echo "TeamKit : le serveur demarre quand meme, joignable seulement par son adresse IP (En ligne > Entrez l'adresse du serveur)."
    else
      # Methode officielle (NETWORKING.md) : --init-user enregistre une session du
      # compte dans donnees/config/.../players.xml, que le serveur reutilise.
      # Le mot de passe n'est jamais ecrit sur le disque ni affiche.
      echo "TeamKit : connexion du compte STK '$STK_IDENTIFIANT' a online.supertuxkart.net..."
      sortie=$(timeout 60 "$BIN" --init-user --no-graphics --log=nocolor \
        --login="$STK_IDENTIFIANT" --password="$STK_MOT_DE_PASSE" </dev/null 2>&1)
      if grep -q "Logged in from command-line" <<<"$sortie" && grep -q "Done saving user, leaving" <<<"$sortie"; then
        wan=oui
        echo "TeamKit : compte STK connecte, le serveur sera dans la liste publique officielle."
      else
        echo "TeamKit : ATTENTION, la connexion du compte STK a echoue (identifiant ou mot de passe faux, ou online.supertuxkart.net injoignable) :"
        grep -E '\[(error|fatal|warn) *\]' <<<"$sortie" | grep -vF -- "$STK_MOT_DE_PASSE" | grep -v "SFXManager\|irr_driver\|MusicManager" | head -n 5 | sed 's/^/    /'
        echo "TeamKit : le serveur demarre quand meme, joignable seulement par son adresse IP."
      fi
    fi
  fi
  unset STK_MOT_DE_PASSE

  python3 "$ICI/reglages_stk.py" reglages-amp.txt "$ICI/serveur.xml" "$JEU/data" "$port" "$decouverte" "$joueurs" "$wan" || exit 1

  # Bots IA : un second processus, lance AVANT l'exec et rattache au jeu par
  # --pdeathsig : il s'arrete tout seul quand le serveur s'arrete. Son entree est
  # /dev/null (la console d'AMP reste au serveur), sa sortie va dans la console.
  bots=$(head -n 1 "$ICI/bots-teamkit.txt" 2>/dev/null | tr -cd '0-9')
  if [ -n "$bots" ] && [ "$bots" -gt 0 ]; then
    STK_BOTS_MDP=$(sed -n 's/^mot_de_passe=//p' reglages-amp.txt | head -n 1 | tr -d '\r') \
      setpriv --pdeathsig TERM -- /bin/bash "$ICI/lancer-stk.sh" bots "$port" "$bots" </dev/null &
  fi

  # --log=nocolor : sans lui, chaque ligne arrive dans AMP avec des codes couleur ANSI.
  # --stk-config  : copie de stk_config.xml avec le port de decouverte d'AMP.
  # Entree : la console reseau du jeu tourne a 100 % d'un coeur des que son entree
  # est fermee (essai du 10/10/2026). Le relais recopie la console d'AMP puis,
  # si elle se ferme, garde l'entree ouverte (sleep). --pdeathsig : le relais
  # disparait avec le jeu.
  exec "$BIN" --server-config="$ICI/serveur.xml" --network-console --log=nocolor \
    --stk-config=stk_config_teamkit.xml \
    < <(exec setpriv --pdeathsig KILL -- /bin/bash -c 'cat; exec sleep infinity')
}

# Bots IA (lance par demarrer, jamais par AMP directement) : attend que le serveur
# ecoute, lance « supertuxkart --connect-now=127.0.0.1:<port> --network-ai=<n> »
# sans affichage, le relance s'il tombe (5 essais au plus, puis abandon jusqu'au
# prochain demarrage), et l'arrete quand le serveur s'arrete (SIGTERM recu par
# --pdeathsig). Le serveur tourne avec ai-handling : il ne compte pas ces bots
# comme des joueurs et n'en fait rouler que N - (joueurs humains) + 1.
bots() {
  local port="$1" n="$2" mdp="$STK_BOTS_MDP" hex essai=0 debut code pid="" arret=0
  unset STK_BOTS_MDP
  [[ "$port" =~ ^[0-9]+$ && "$n" =~ ^[0-9]+$ ]] || exit 1
  environnement "$JEU"
  # Profil et cache a part (le serveur ecrit les siens) ; meme dossier d'addons
  # que le serveur, sinon le vote des pistes se limiterait aux pistes officielles.
  export XDG_CONFIG_HOME="$ICI/donnees/bots/config" XDG_CACHE_HOME="$ICI/donnees/bots/cache" HOME="$ICI/donnees/bots"
  mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
  trap 'arret=1; [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null' TERM INT

  # Le serveur ecoute quand son port UDP apparait dans /proc/net/udp*.
  hex=$(printf ':%04X' "$port")
  for _ in $(seq 1 120); do
    [ "$arret" = 1 ] && exit 0
    if awk -v p="$hex" 'substr($2, length($2) - 4) == p { t = 1 } END { exit !t }' /proc/net/udp /proc/net/udp6 2>/dev/null; then
      break
    fi
    sleep 0.5
  done
  sleep 2

  while [ "$arret" = 0 ]; do
    debut=$(date +%s)
    # Journal des bots : donnees/bots/config/supertuxkart/config-0.10/stdout.log (le jeu l'ecrit).
    setpriv --pdeathsig TERM -- "$BIN" --connect-now="127.0.0.1:$port" --network-ai="$n" \
      --no-graphics --log=nocolor ${mdp:+"--server-password=$mdp"} </dev/null >/dev/null 2>&1 &
    pid=$!
    echo "TeamKit : bots IA lances ($n bots, connectes au serveur en local)."
    wait "$pid"
    code=$?
    # Le SIGTERM interrompt « wait » : on attend la vraie fin des bots.
    [ "$arret" = 1 ] && { wait "$pid" 2>/dev/null; exit 0; }
    pid=""
    # Un client qui a tenu 10 minutes remet le compteur a zero.
    [ $(( $(date +%s) - debut )) -ge 600 ] && essai=0
    essai=$((essai + 1))
    if [ "$essai" -ge 5 ]; then
      echo "TeamKit : ATTENTION, les bots IA se sont arretes 5 fois de suite (code $code) : abandon jusqu'au prochain demarrage du serveur. Journal : donnees/bots/config/supertuxkart/config-0.10/stdout.log"
      exit 1
    fi
    echo "TeamKit : les bots IA se sont arretes (code $code), relance dans $((essai * 10)) s (essai $essai sur 4)."
    sleep $((essai * 10)) &
    pid=$!
    wait "$pid" 2>/dev/null
    pid=""
  done
}

case "$1" in
  installer) installer "$2" ;;
  demarrer) demarrer "$2" "$3" "$4" ;;
  bots) bots "$2" "$3" ;;
  *) echo "usage : lancer-stk.sh installer [version] | demarrer <port> <port_decouverte> <joueurs_max>"; exit 1 ;;
esac
