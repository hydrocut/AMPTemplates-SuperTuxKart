# -*- coding: utf-8 -*-
"""
reglages_stk.py - pose par le template AMP TeamKit (recree a chaque Update).

Appele par lancer-stk.sh juste avant le demarrage du serveur :

    python3 reglages_stk.py <reglages-amp.txt> <serveur.xml> <jeu/data> <port> <port_decouverte> <joueurs_max> <wan oui|non>

1. lit reglages-amp.txt, ecrit par AMP a partir de AMP_reglages.txt (une ligne
   cle=valeur par reglage, valeur brute : AMP ne l'echappe pas) ;
2. controle chaque valeur et refuse de demarrer sur une valeur impossible ;
3. met a jour serveur.xml (le fichier --server-config de SuperTuxKart) : seules les
   cles gerees par AMP sont remplacees, toute autre cle ajoutee a la main est gardee ;
4. ecrit le message d'accueil dans accueil.txt (UTF-8, lu tel quel par le jeu) ;
5. ecrit jeu/data/stk_config_teamkit.xml, copie de stk_config.xml avec le port de
   decouverte choisi dans AMP (le jeu le lit avec --stk-config).

Pourquoi tout ca : SuperTuxKart lit son XML avec irrXML, qui ne decode PAS les
entites numeriques, puis passe le nom du serveur dans StringUtils::xmlDecode, qui
lit l'octet brut. Un accent ecrit tel quel (UTF-8) arrive donc casse chez les
joueurs ; il faut l'ecrire &#xE9; comme le fait le jeu lui-meme (xmlEncode).
Le message d'accueil, lui, est lu en UTF-8 quand il vient d'un fichier .txt.
"""
import io
import os
import re
import sys

# Modes de jeu de server-mode (src/network/server_config.cpp, getLocalGameMode).
MODES = {
    '3': 'course',
    '4': 'contre-la-montre',
    '0': 'grand prix (course)',
    '1': 'grand prix (contre-la-montre)',
    '7': 'bataille (chacun pour soi)',
    '8': 'capture du drapeau',
    '6': 'football',
}
DIFFICULTES = {'0': 'novice', '1': 'intermediaire', '2': 'expert', '3': 'SuperTux'}
NOM_PAR_DEFAUT = 'TeamKit.fr'
ACCUEIL_FICHIER = 'accueil.txt'
EN_TETE = (
    '<?xml version="1.0"?>\n'
    '<server-config version="%d" >\n\n'
    '    <!-- Fichier de SuperTuxKart (--server-config). Les cles marquees AMP plus bas\n'
    '         sont REECRITES a chaque demarrage depuis l onglet Configuration d AMP.\n'
    '         Toute autre cle de NETWORKING.md ajoutee ici est gardee. -->\n\n'
)


class Refus(Exception):
    pass


def lire_reglages(chemin):
    if not os.path.isfile(chemin):
        raise Refus('%s absent : AMP l ecrit au demarrage a partir de AMP_reglages.txt, lance Update.' % chemin)
    valeurs = {}
    with io.open(chemin, encoding='utf-8', errors='replace') as f:
        for ligne in f.read().splitlines():
            ligne = ligne.rstrip('\r')
            if not ligne or ligne.startswith('#') or '=' not in ligne:
                continue
            cle, valeur = ligne.split('=', 1)
            valeurs[cle.strip()] = valeur
    return valeurs


def encoder_stk(texte):
    """Comme StringUtils::xmlEncode de SuperTuxKart : tout ce qui n'est pas ASCII,
    et & < > ", devient &#xNN; (le jeu le decode avec xmlDecode)."""
    sortie = []
    for c in texte:
        o = ord(c)
        if o < 32 or o == 127:
            continue
        if o >= 128 or c in '&<>"':
            sortie.append('&#x%X;' % o)
        else:
            sortie.append(c)
    return ''.join(sortie)


def encoder_xml_simple(texte):
    """Pour le mot de passe : le jeu ne le passe PAS dans xmlDecode, seules les
    entites nommees (decodees par irrXML) sont sures."""
    return (texte.replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def entier(valeur, nom, mini, maxi):
    v = (valeur or '').strip()
    if not re.fullmatch(r'\d+', v) or not (mini <= int(v) <= maxi):
        raise Refus('%s : %r, il faut un nombre entre %d et %d.' % (nom, valeur, mini, maxi))
    return int(v)


def oui_non(valeur, nom):
    v = (valeur or '').strip().lower()
    if v in ('oui', 'true'):
        return True
    if v in ('non', 'false'):
        return False
    raise Refus('%s : %r, il faut oui ou non.' % (nom, valeur))


def construire(r, port, decouverte, joueurs_max, wan):
    """Retourne (cles du XML -> valeur deja encodee, message d'accueil, resume)."""
    nom = ' '.join((r.get('nom') or '').split())
    if not nom:
        nom = NOM_PAR_DEFAUT
    accueil = ' '.join((r.get('accueil') or '').split())
    mdp = r.get('mot_de_passe') or ''
    if mdp != mdp.strip():
        raise Refus('mot de passe du serveur : pas d espace au debut ni a la fin.')
    if mdp and not re.fullmatch(r'[\x21-\x7e]+', mdp):
        raise Refus('mot de passe du serveur : lettres sans accent, chiffres et signes du clavier '
                    'seulement, sans espace (le jeu compare les octets, un accent ne passerait pas).')
    mode = (r.get('mode') or '').strip()
    if mode not in MODES:
        raise Refus('mode de jeu %r inconnu.' % mode)
    diff = (r.get('difficulte') or '').strip()
    if diff not in DIFFICULTES:
        raise Refus('difficulte %r inconnue.' % diff)
    pistes = entier(r.get('pistes_gp'), 'pistes par grand prix', 1, 20)
    depart = entier(r.get('joueurs_depart'), 'joueurs pour lancer la partie', 1, 255)
    sans_proprio = oui_non(r.get('sans_proprietaire'), 'serveur sans proprietaire')
    foot_buts = oui_non(r.get('foot_buts'), 'football aux buts')
    joueurs = entier(joueurs_max, 'nombre de joueurs (AMP)', 1, 255)
    if depart > joueurs:
        depart = joueurs
    cles = {
        'server-name': encoder_stk(nom),
        'server-port': str(entier(port, 'port du jeu', 1, 65535)),
        'server-mode': mode,
        'server-difficulty': diff,
        'gp-track-count': str(pistes),
        'soccer-goal-target': 'true' if foot_buts else 'false',
        'wan-server': 'true' if wan else 'false',
        'server-max-players': str(joueurs),
        'private-server-password': encoder_xml_simple(mdp),
        'motd': ACCUEIL_FICHIER if accueil else '',
        'owner-less': 'true' if sans_proprio else 'false',
        'min-start-game-players': str(depart),
    }
    entier(decouverte, 'port de decouverte', 1, 65535)
    resume = ('TeamKit : serveur "%s", %s, difficulte %s, %d joueurs maximum, %s, %s.' % (
        nom, MODES[mode], DIFFICULTES[diff], joueurs,
        'mot de passe actif' if mdp else 'sans mot de passe',
        'liste publique officielle' if wan else 'joignable par adresse IP'))
    return cles, accueil, resume


def versions_serveur(dossier_data):
    """server-version min/max de stk_config.xml : un serveur.xml hors de cette
    plage serait efface par le jeu et recree avec ses valeurs par defaut."""
    with io.open(os.path.join(dossier_data, 'stk_config.xml'), encoding='utf-8', errors='replace') as f:
        texte = f.read()
    m = re.search(r'<server-version\s+min="(\d+)"\s+max="(\d+)"', texte)
    if not m:
        raise Refus('stk_config.xml du jeu illisible (server-version introuvable) : relance Update.')
    return int(m.group(1)), int(m.group(2)), texte


def ecrire_stk_config(texte, dossier_data, decouverte):
    """Copie de stk_config.xml avec le port de decouverte d'AMP. Le jeu exige trois
    ports differents (client, serveur, decouverte) : on decale client-port si besoin."""
    m = re.search(r'<network-ports\s+server-discovery-port="\d+"\s+client-port="(\d+)"\s+server-port="(\d+)"\s*/>', texte)
    if not m:
        raise Refus('stk_config.xml du jeu : ligne network-ports introuvable.')
    serveur = int(m.group(2))
    client = int(m.group(1))
    while client in (decouverte, serveur):
        client = client + 1 if client < 65535 else 1024
    ligne = '<network-ports server-discovery-port="%d" client-port="%d" server-port="%d"/>' % (decouverte, client, serveur)
    nouveau = texte[:m.start()] + ligne + texte[m.end():]
    chemin = os.path.join(dossier_data, 'stk_config_teamkit.xml')
    with io.open(chemin + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
        f.write(nouveau)
    os.replace(chemin + '.tmp', chemin)


def mettre_a_jour_xml(chemin, cles, vmin, vmax):
    texte = None
    if os.path.isfile(chemin):
        with io.open(chemin, encoding='utf-8', errors='replace') as f:
            texte = f.read()
        m = re.search(r'<server-config\s+version="(\d+)"', texte)
        if not m or '</server-config>' not in texte:
            print('TeamKit : serveur.xml illisible, il est recree (ancienne copie : serveur.xml.illisible).')
            os.replace(chemin, chemin + '.illisible')
            texte = None
        elif not (vmin <= int(m.group(1)) <= vmax):
            print('TeamKit : serveur.xml en version %s, le jeu attend %d a %d : il est recree '
                  '(ancienne copie : serveur.xml.ancien).' % (m.group(1), vmin, vmax))
            os.replace(chemin, chemin + '.ancien')
            texte = None
    if texte is None:
        texte = EN_TETE % vmax + '</server-config>\n'
    for cle, valeur in cles.items():
        # Ligne ENTIERE : en s'arretant, le jeu reecrit ce fichier avec les valeurs
        # brutes, sans les echapper (essai du 10/10/2026 : un mot de passe a"b<c
        # revient tel quel, guillemet compris). On remplace donc toute la ligne.
        motif = re.compile(r'^([ \t]*)<%s[ \t]+value=.*$' % re.escape(cle), re.M)
        nouvelle = '<%s value="%s" />' % (cle, valeur)
        trouves = list(motif.finditer(texte))
        if trouves:
            # La premiere est remplacee, les doublons eventuels sont retires.
            for m in reversed(trouves[1:]):
                fin = m.end() + 1 if texte[m.end():m.end() + 1] == '\n' else m.end()
                texte = texte[:m.start()] + texte[fin:]
            m = trouves[0]
            texte = texte[:m.start()] + m.group(1) + nouvelle + texte[m.end():]
        else:
            fin = texte.rindex('</server-config>')
            texte = texte[:fin] + '    <!-- AMP -->\n    ' + nouvelle + '\n\n' + texte[fin:]
    with io.open(chemin + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
        f.write(texte)
    os.replace(chemin + '.tmp', chemin)
    return texte


def principal(argv):
    if len(argv) != 8:
        raise Refus('usage : reglages_stk.py <reglages> <serveur.xml> <jeu/data> <port> <decouverte> <joueurs> <wan oui|non>')
    _, reglages, xml, data, port, decouverte, joueurs, wan = argv
    r = lire_reglages(reglages)
    cles, accueil, resume = construire(r, port, decouverte, joueurs, wan == 'oui')
    vmin, vmax, stk_config = versions_serveur(data)
    ecrire_stk_config(stk_config, data, int(decouverte))
    dossier = os.path.dirname(os.path.abspath(xml))
    chemin_accueil = os.path.join(dossier, ACCUEIL_FICHIER)
    if accueil:
        with io.open(chemin_accueil, 'w', encoding='utf-8', newline='\n') as f:
            f.write(accueil + '\n')
    elif os.path.exists(chemin_accueil):
        os.remove(chemin_accueil)
    mettre_a_jour_xml(xml, cles, vmin, vmax)
    print(resume)


if __name__ == '__main__':
    try:
        principal(sys.argv)
    except Refus as e:
        print('ERREUR : %s' % e)
        print('Corrige ce reglage dans l onglet Configuration d AMP, puis relance.')
        sys.exit(1)
