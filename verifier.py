# -*- coding: utf-8 -*-
"""
Controle du template avant de le pousser (meme role que ceux de Wesnoth, Mumble, DDNet).

    python verifier.py

1. tous les JSON se parsent ;
2. le .kvp ne reference que des fichiers presents, les ports existent, le bloc
   Console.* / Limits.* est complet, la console d'AMP ecrit dans le jeu ;
3. chaque reglage expose dans AMP arrive quelque part (modele AMP_reglages.txt,
   variable d'environnement, etape d'Update ou {{$MaxUsers}}), et chaque cle du
   modele est lue par reglages_stk.py ; les listes de choix correspondent au script ;
4. aller-retour : rendu du modele comme AMP (remplacement brut), passage dans
   reglages_stk.py, puis relecture du XML COMME LE JEU (irrXML ne decode que les
   entites nommees, puis xmlDecode les &#x..; du nom) : valeur vide, espaces,
   accents, guillemets, &, <, {, #, emoji. Et le cas vecu : le jeu reecrit le
   fichier en s'arretant avec le mot de passe brut, non echappe ;
5. les fichiers telecharges a l'Update existent dans scripts/, a l'URL du depot ;
6. le lanceur : fins de ligne LF, aucun {{, options indispensables, mot de passe
   du compte jamais affiche, `bash -n` s'il y a un bash ;
7. les regex de console reconnaissent les vraies lignes de SuperTuxKart 1.5
   (relevees le 10 oct. 2026 dans un conteneur jetable cubecoders/ampbase:debian).
"""
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
NOM = 'supertuxkart'
MODELE = 'scripts/AMP_reglages.txt'
LANCEUR = 'scripts/lancer-stk.sh'
SCRIPT = 'scripts/reglages_stk.py'
soucis = []


def lire(nom, binaire=False):
    chemin = os.path.join(ICI, nom)
    if binaire:
        with open(chemin, 'rb') as f:
            return f.read()
    with io.open(chemin, encoding='utf-8') as f:
        return f.read()


def py(motif):
    # AMP est en C# : (?<nom>...) ; Python veut (?P<nom>...)
    return re.compile(motif.replace('(?<', '(?P<'))


# -- 1. JSON -------------------------------------------------------------------
data = {}
for nom in ('manifest.json', NOM + 'config.json', NOM + 'metaconfig.json', NOM + 'ports.json', NOM + 'updates.json'):
    try:
        data[nom] = json.loads(lire(nom))
        print('ok   %-28s JSON valide' % nom)
    except Exception as e:
        soucis.append('%s : JSON invalide (%s)' % (nom, e))
if soucis:
    print('\n'.join('NON  ' + s for s in soucis))
    sys.exit(1)
config = data[NOM + 'config.json']
updates = data[NOM + 'updates.json']
ports = data[NOM + 'ports.json']

# -- 2. kvp --------------------------------------------------------------------
kvp = lire(NOM + '.kvp')
cles = dict(l.split('=', 1) for l in kvp.splitlines() if '=' in l)
for ref in re.findall(r'@IncludeJson\[([^\]]+)\]', kvp):
    if not os.path.isfile(os.path.join(ICI, ref)):
        soucis.append('@IncludeJson[%s] : fichier absent' % ref)
for cle in ('Meta.ConfigManifest', 'Meta.MetaConfigManifest'):
    if not os.path.isfile(os.path.join(ICI, cles.get(cle, '?'))):
        soucis.append('%s pointe sur un fichier absent' % cle)
refs = {p['Ref'] for p in ports}
if cles.get('App.PrimaryApplicationPortRef') not in refs:
    soucis.append('PrimaryApplicationPortRef ne correspond a aucun port')
cmd = cles.get('App.CommandLineArgs', '')
for r in re.findall(r'\{\{\$(\w+)\}\}', cmd):
    if r not in refs and r not in ('FullBaseDir', 'MaxUsers'):
        soucis.append('{{$%s}} : aucun port ne porte ce Ref' % r)
if cmd != '"{{$FullBaseDir}}lancer-stk.sh" demarrer {{$ServerPort}} {{$DiscoveryPort}} {{$MaxUsers}}':
    soucis.append('ligne de commande inattendue (le lanceur attend : demarrer <port> <decouverte> <joueurs>) : %s' % cmd)
for p in ports:
    if p['Protocol'] != 'UDP':
        soucis.append('port %s : SuperTuxKart est en UDP seulement' % p['Ref'])
if {p['Ref']: p['Port'] for p in ports} != {'ServerPort': 2759, 'DiscoveryPort': 2757}:
    soucis.append('ports par defaut : 2759 (serveur) et 2757 (decouverte), comme stk_config.xml')
print('ok   ports                        %s' % ', '.join('%s %s/%s' % (p['Ref'], p['Port'], p['Protocol']) for p in ports))
ATTENDUES = ['App.SupportsUniversalSleep', 'App.WakeupMode', 'App.ApplicationReadyMode', 'Console.FilterMatchRegex', 'Console.FilterMatchReplacement', 'Console.ThrowawayMessageRegex', 'Console.AppReadyRegex', 'Console.UserJoinRegex', 'Console.UserLeaveRegex', 'Console.UserChatRegex', 'Console.UpdateAvailableRegex', 'Console.PreConnectRegex', 'Console.ConnectIPRegex', 'Console.MetricsRegex', 'Console.HideFromConsoleRegex', 'Console.SuppressLogAtStart', 'Console.UserActions', 'Limits.SleepMode', 'Limits.SleepOnStart', 'Limits.SleepDelayMinutes', 'Limits.DozeDelay', 'Limits.AutoRetryCount', 'Limits.SleepStartThresholdSeconds']
absentes = [c for c in ATTENDUES if c not in cles]
if absentes:
    soucis.append('cles absentes du .kvp : ' + ', '.join(absentes))
else:
    print('ok   kvp complet                  les %d cles Console/Limits sont la' % len(ATTENDUES))
if cles.get('App.ApplicationReadyMode') == 'RegexMatch' and not cles.get('Console.AppReadyRegex'):
    soucis.append('RegexMatch sans AppReadyRegex : l instance ne serait jamais declaree prete')
if cles.get('App.HasWriteableConsole') != 'True' or cles.get('App.AdminMethod') != 'STDIO':
    soucis.append('la console d AMP doit ecrire dans le jeu (HasWriteableConsole=True, AdminMethod=STDIO)')
if cles.get('App.ExitMethod') != 'SIGTERM':
    soucis.append('App.ExitMethod doit etre SIGTERM : le jeu s arrete proprement dessus (main_abort)')
if cles.get('Meta.URL') != data['manifest.json']['url']:
    soucis.append('Meta.URL et manifest.json ne designent pas le meme depot')
env = json.loads(cles.get('App.EnvironmentVariables', '{}'))

# -- 3. reglages <-> modele, script, environnement -----------------------------
modele = lire(MODELE)
script = lire(SCRIPT)
lanceur = lire(LANCEUR)
dans_modele = re.findall(r'\{\{([A-Za-z0-9_]+)\}\}', modele)
cle_modele = dict(re.findall(r'^([a-z_]+)=\{\{([A-Za-z0-9_]+)\}\}$', modele, re.M))
params = {}
for c in config:
    p = c.get('ParamFieldName')
    champ = c['FieldName']
    if p in params:
        soucis.append('reglage en double : %s' % p)
    params[p] = c
    if champ.startswith('$'):
        if '{{%s}}' % champ not in cmd:
            soucis.append('%s : pas passe au lanceur' % champ)
        continue
    if champ != p:
        soucis.append('%s : FieldName et ParamFieldName differents (%s)' % (p, champ))
    ou = []
    if p in dans_modele:
        ou.append('modele')
    if '{{%s}}' % p in env.values():
        ou.append('environnement')
    if any('{{%s}}' % p in e.get('UpdateSourceArgs', '') for e in updates):
        ou.append('Update')
    if len(ou) != 1:
        soucis.append('reglage %s : doit arriver a un seul endroit, trouve : %s' % (p, ou or 'nulle part'))
    if dans_modele.count(p) > 1:
        soucis.append('{{%s}} ecrit deux fois dans le modele' % p)
    if c['InputType'] == 'number' and not str(c.get('DefaultValue', '')).isdigit():
        soucis.append('%s : valeur par defaut non numerique' % p)
    if c['InputType'] == 'enum' and str(c.get('DefaultValue')) not in c['EnumValues']:
        soucis.append('%s : valeur par defaut hors de la liste' % p)
orphelins = set(dans_modele) - set(params)
if orphelins:
    soucis.append('{{...}} sans reglage dans AMP : %s' % ', '.join(sorted(orphelins)))
for cle_txt, p in cle_modele.items():
    if cle_txt == 'visibilite':
        if "s/^visibilite=//p" not in lanceur:
            soucis.append('visibilite : le lanceur doit la lire dans reglages-amp.txt')
    elif "r.get('%s')" % cle_txt not in script:
        soucis.append('cle %s du modele jamais lue par reglages_stk.py' % cle_txt)
for v in env:
    if '$%s' % v not in lanceur:
        soucis.append('variable %s jamais lue par le lanceur' % v)
for p in ('MotDePasseSTK',):
    if params[p]['InputType'] != 'password' or '{{%s}}' % p not in env.values():
        soucis.append('le mot de passe du compte STK doit etre un champ masque passe par l environnement, jamais dans un fichier')
meta = data[NOM + 'metaconfig.json'][0]
racine = cles['App.RootDir'].strip('./').strip('/')
if meta.get('ConfigType') != 'template' or meta.get('ConfigFileTemplate') != racine + '/AMP_reglages.txt':
    soucis.append('metaconfig : ConfigFileTemplate devrait etre %s/AMP_reglages.txt' % racine)
if meta.get('ConfigFile') != 'reglages-amp.txt' or 'reglages-amp.txt' not in lanceur:
    soucis.append('le fichier rendu par AMP (ConfigFile) n est pas celui que lit le lanceur')
accueil_def = params['MessageAccueil']['DefaultValue']
if 'TeamKit.fr' not in accueil_def or 'discord.gg/EuAjGMYPHY' not in accueil_def:
    soucis.append('le message d accueil par defaut doit citer TeamKit.fr et le Discord')
if 'TeamKit' not in params['NomServeur']['DefaultValue']:
    soucis.append('le nom du serveur par defaut doit citer TeamKit')

# Le script lui-meme, charge comme module.
spec = importlib.util.spec_from_file_location('reglages_stk', os.path.join(ICI, SCRIPT))
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)
if set(params['ModeJeu']['EnumValues']) != set(rs.MODES):
    soucis.append('modes de jeu : liste AMP %s, script %s' % (sorted(params['ModeJeu']['EnumValues']), sorted(rs.MODES)))
if set(params['Difficulte']['EnumValues']) != set(rs.DIFFICULTES):
    soucis.append('difficultes : liste AMP et script differentes')
for p in ('FootAuxButs', 'SansProprietaire'):
    if set(params[p]['EnumValues']) != {'oui', 'non'}:
        soucis.append('%s : choix oui / non attendus (lus par oui_non)' % p)
if set(params['Visibilite']['EnumValues']) != {'public', 'ip'} or '"$visibilite" = "public"' not in lanceur:
    soucis.append('Visibilite : choix public / ip, et le lanceur teste "public"')
print('ok   correspondance               %d reglages, chacun a un seul endroit' % len(params))


# -- 4. aller-retour AMP -> reglages_stk.py -> lecture comme le jeu -------------
def rendre(valeurs):
    t = modele
    for p, v in valeurs.items():
        t = t.replace('{{%s}}' % p, v)
    return t


def irrxml_attribut(brut):
    # irrXML : seulement les 5 entites nommees (les &#x..; restent tels quels).
    for a, b in (('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&apos;', "'"), ('&amp;', '&')):
        brut = brut.replace(a, b)
    return brut


def xml_decode(s):
    # StringUtils::xmlDecode : &#xHH; et &#DD; ; un & seul reste un &.
    return re.sub(r'&#(x[0-9A-Fa-f]+|\d+);',
                  lambda m: chr(int(m.group(1)[1:], 16) if m.group(1)[0] == 'x' else int(m.group(1))), s)


def valeur_xml(texte, cle):
    m = re.findall(r'^[ \t]*<%s value="(.*)" />$' % re.escape(cle), texte, re.M)
    return m


defauts = {p: str(c.get('DefaultValue', '')) for p, c in params.items() if not c['FieldName'].startswith('$')}
n = 0
dossier = tempfile.mkdtemp(prefix='verif-stk-')
try:
    data_dir = os.path.join(dossier, 'data')
    os.mkdir(data_dir)
    with io.open(os.path.join(data_dir, 'stk_config.xml'), 'w', encoding='utf-8') as f:
        f.write('<config>\n  <server-version min="6" max="6"/>\n'
                '  <network-ports server-discovery-port="2757" client-port="2758" server-port="2759"/>\n</config>\n')
    xml = os.path.join(dossier, 'serveur.xml')
    reg = os.path.join(dossier, 'reglages-amp.txt')

    def passer(valeurs, port='2759', dec='2757', joueurs='8', wan='non'):
        with io.open(reg, 'w', encoding='utf-8', newline='\n') as f:
            f.write(rendre(valeurs))
        try:
            rs.principal(['x', reg, xml, data_dir, port, dec, joueurs, wan])
        except rs.Refus as e:
            return 'REFUS: %s' % e
        with io.open(xml, encoding='utf-8') as f:
            return f.read()

    import contextlib
    silence = io.StringIO()
    NOMS = ['', '   ', 'TeamKit.fr — Serveur francophone', 'Été "chez" l\'équipe & <amis> {ici} #1 · 100 %', 'Course 🏎️ rapide']
    with contextlib.redirect_stdout(silence):
        for v in NOMS:
            vals = dict(defauts)
            vals['NomServeur'] = v
            t = passer(vals)
            lu = valeur_xml(t, 'server-name')
            attendu = ' '.join(v.split()) or rs.NOM_PAR_DEFAUT
            n += 1
            if len(lu) != 1 or xml_decode(irrxml_attribut(lu[0])) != attendu or '"' in lu[0]:
                soucis.append('aller-retour nom %r : relu %r' % (v, lu))
        for v in ['', 'Bienvenue !', accueil_def, 'Règles : {pas} de "triche" & <respect> #fairplay']:
            vals = dict(defauts)
            vals['MessageAccueil'] = v
            t = passer(vals)
            n += 1
            fichier = os.path.join(dossier, 'accueil.txt')
            if v:
                with io.open(fichier, encoding='utf-8') as f:
                    contenu = f.read()
                if valeur_xml(t, 'motd') != ['accueil.txt'] or contenu != v + '\n':
                    soucis.append('message d accueil %r : %r / %r' % (v, valeur_xml(t, 'motd'), contenu))
            elif valeur_xml(t, 'motd') != [''] or os.path.exists(fichier):
                soucis.append('message d accueil vide : motd doit etre vide et accueil.txt absent')
        for v in ['', 'simple', 'Mot2Passe&<>"x', "a'b{c}#d"]:
            vals = dict(defauts)
            vals['MotDePasseServeur'] = v
            t = passer(vals)
            lu = valeur_xml(t, 'private-server-password')
            n += 1
            if len(lu) != 1 or irrxml_attribut(lu[0]) != v:
                soucis.append('aller-retour mot de passe %r : relu %r' % (v, lu))
            # Le jeu reecrit le fichier en s'arretant, valeur brute (essai du 10/10/2026)
            with io.open(xml, 'w', encoding='utf-8') as f:
                f.write(t.replace('<private-server-password value="%s" />' % lu[0],
                                  '<private-server-password value="%s" />' % v))
            t2 = passer(vals)
            lu2 = valeur_xml(t2, 'private-server-password')
            n += 1
            if len(lu2) != 1 or irrxml_attribut(lu2[0]) != v or t2.count('private-server-password') != 1:
                soucis.append('mot de passe %r apres reecriture brute par le jeu : %r' % (v, lu2))
        for v in ['été', ' debut', 'fin ', 'a b']:
            vals = dict(defauts)
            vals['MotDePasseServeur'] = v
            n += 1
            if not passer(vals).startswith('REFUS'):
                soucis.append('mot de passe %r : aurait du etre refuse' % v)
        for p, v in [('ModeJeu', '5'), ('ModeJeu', ''), ('Difficulte', '4'), ('PistesGrandPrix', 'abc'),
                     ('PistesGrandPrix', '0'), ('JoueursPourLancer', ''), ('SansProprietaire', 'peut-etre')]:
            vals = dict(defauts)
            vals[p] = v
            n += 1
            if not passer(vals).startswith('REFUS'):
                soucis.append('%s=%r : aurait du etre refuse' % (p, v))
        # cle ajoutee a la main : gardee ; cles gerees : une seule fois chacune
        with io.open(xml, 'a', encoding='utf-8') as f:
            pass
        t = passer(dict(defauts))
        t = t.replace('</server-config>', '    <kick-idle-player-seconds value="123" />\n</server-config>')
        with io.open(xml, 'w', encoding='utf-8') as f:
            f.write(t)
        t = passer(dict(defauts), port='27015', dec='27016', joueurs='12', wan='oui')
        n += 1
        if 'kick-idle-player-seconds value="123"' not in t:
            soucis.append('une cle ajoutee a la main dans serveur.xml a ete perdue')
        attendu = {'server-port': '27015', 'server-max-players': '12', 'wan-server': 'true',
                   'server-mode': defauts['ModeJeu'], 'owner-less': 'true'}
        for k, v in attendu.items():
            if valeur_xml(t, k) != [v]:
                soucis.append('serveur.xml : %s = %r au lieu de %r' % (k, valeur_xml(t, k), v))
        with io.open(os.path.join(data_dir, 'stk_config_teamkit.xml'), encoding='utf-8') as f:
            sc = f.read()
        if 'server-discovery-port="27016"' not in sc:
            soucis.append('stk_config_teamkit.xml : port de decouverte non applique')
        # port de decouverte = client-port du jeu : le jeu exige trois ports differents
        passer(dict(defauts), dec='2758')
        with io.open(os.path.join(data_dir, 'stk_config_teamkit.xml'), encoding='utf-8') as f:
            sc = f.read()
        m = re.search(r'server-discovery-port="(\d+)" client-port="(\d+)" server-port="(\d+)"', sc)
        n += 1
        if not m or len(set(m.groups())) != 3:
            soucis.append('ports du stk_config : trois ports differents exiges par le jeu (%s)' % (m and m.groups()))
        # version de fichier hors plage : le jeu effacerait tout, le script recree
        with io.open(xml, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0"?>\n<server-config version="3" >\n</server-config>\n')
        t = passer(dict(defauts))
        n += 1
        if '<server-config version="6"' not in t:
            soucis.append('serveur.xml d une autre version : pas recree en version 6')
finally:
    shutil.rmtree(dossier, ignore_errors=True)
print('ok   aller-retour                 %d cas (nom, accueil, mot de passe, refus, cles gardees, ports)' % n)

# -- 5. fichiers telecharges a l'Update -----------------------------------------
depot = data['manifest.json']['url'].replace('https://github.com/', '')
fetch = [e for e in updates if e['UpdateSource'] == 'FetchURL']
for e in fetch:
    attendu = 'https://raw.githubusercontent.com/%s/main/scripts/%s' % (depot, e['UpdateSourceArgs'])
    if e['UpdateSourceData'] != attendu:
        soucis.append('URL inattendue pour %s : %s' % (e['UpdateSourceArgs'], e['UpdateSourceData']))
    elif not os.path.isfile(os.path.join(ICI, 'scripts', e['UpdateSourceArgs'])):
        soucis.append('scripts/%s absent du depot' % e['UpdateSourceArgs'])
    else:
        print('ok   telecharge a l Update        scripts/%s' % e['UpdateSourceArgs'])
if {e['UpdateSourceArgs'] for e in fetch} != {'AMP_reglages.txt', 'lancer-stk.sh', 'reglages_stk.py'}:
    soucis.append('l Update doit deposer AMP_reglages.txt, lancer-stk.sh et reglages_stk.py')
dernier = updates[-1]
if dernier.get('UpdateSource') != 'Executable' or 'lancer-stk.sh\\" installer' not in json.dumps(dernier.get('UpdateSourceArgs', '')) \
        and 'lancer-stk.sh" installer' not in dernier.get('UpdateSourceArgs', ''):
    soucis.append('la derniere etape d Update doit lancer « lancer-stk.sh installer » (apres le telechargement du lanceur)')

# -- 6. lanceur -----------------------------------------------------------------
for nom in (LANCEUR, MODELE, SCRIPT):
    if b'\r' in lire(nom, binaire=True):
        soucis.append('%s : fins de ligne Windows (CRLF)' % nom)
if '{{' in lanceur or '{{' in script:
    soucis.append('le lanceur ou le script contient {{ : AMP pourrait le remplacer')
for besoin, pourquoi in [
    ('--server-config="$ICI/serveur.xml" --network-console --log=nocolor', 'console d AMP -> jeu, et sans --log=nocolor des codes couleur ANSI partout'),
    ('exec "$BIN" --server-config=', 'le jeu doit remplacer le lanceur (SIGTERM direct)'),
    ('--pdeathsig KILL', 'le relais de la console disparait avec le jeu'),
    ("cat; exec sleep infinity", 'entree jamais fermee : sinon 100 % CPU'),
    ('--init-user --no-graphics', 'sans --no-graphics, --init-user plante sans ecran'),
    ('--stk-config=stk_config_teamkit.xml', 'port de decouverte d AMP'),
    ('releases/latest', 'derniere version stable par defaut'),
    ('unset STK_MOT_DE_PASSE', 'le mot de passe ne doit pas suivre le jeu'),
]:
    if besoin not in lanceur:
        soucis.append('lanceur : %s (%s)' % (besoin, pourquoi))
for l in lanceur.splitlines():
    if re.search(r'\b(echo|printf)\b', l) and 'STK_MOT_DE_PASSE' in l:
        soucis.append('lanceur : le mot de passe du compte STK ne doit jamais etre affiche : %s' % l.strip())
appel = re.search(r'python3 "\$ICI/reglages_stk.py" (.*?) \|\| exit 1', lanceur)
if not appel or len(appel.group(1).split()) != 7:
    soucis.append('lanceur : reglages_stk.py attend 7 arguments')
bash = shutil.which('bash')
if bash:
    r = subprocess.run([bash, '-n', os.path.join(ICI, LANCEUR)], capture_output=True, text=True)
    if r.returncode:
        soucis.append('bash -n %s : %s' % (LANCEUR, r.stderr.strip()))
    else:
        print('ok   bash -n                      %s' % LANCEUR)
else:
    print('--   bash -n                      pas de bash ici, syntaxe non verifiee')

# -- 7. regex de console sur de vraies lignes (SuperTuxKart 1.5, 10/10/2026) ----
D = 'Sat Oct 10 17:53:53 2026 '
ESSAIS = [
    ('Console.AppReadyRegex', 'Sat Oct 10 17:53:44 2026 [info   ] STKHost: Listening has been started.', {}),
    ('Console.UserJoinRegex', D + '[info   ] ServerLobby: New player Bot 1 with online id 0 from 127.0.0.1:45266 with AI.', {'username': 'Bot 1'}),
    # format du code (server_lobby.cpp + getUserAgentString) : joueur humain, compte en ligne
    ('Console.UserJoinRegex', D + '[info   ] ServerLobby: New player Kévin_42 with online id 123456 from 203.0.113.7:2758 with SuperTuxKart/1.5 (Windows).', {'username': 'Kévin_42'}),
    ('Console.UserLeaveRegex', 'Sat Oct 10 17:54:18 2026 [info   ] ServerLobby: Bot 1 disconnected', {'username': 'Bot 1'}),
    ('Console.ThrowawayMessageRegex', D + '[info   ] ServerLobby: Message of type 1 received.', {}),
    ('Console.ThrowawayMessageRegex', 'Sat Oct 10 17:38:42 2026 [info   ] NetworkPlayerController: New network player controller.', {}),
    ('Console.ThrowawayMessageRegex', 'Sat Oct 10 17:38:42 2026 [info   ] ProtocolManager: A 12GameProtocol protocol has been started.', {}),
    ('Console.ThrowawayMessageRegex', "[info   ] [FileManager]: Asset 16 will be loaded from '/AMP/supertuxkart/jeu/data/tracks/'.", {}),
    ('Console.ThrowawayMessageRegex', '[info   ] Singleton: Destroyed singleton.', {}),
]
for cle, ligne, attendu in ESSAIS:
    m = py(cles.get(cle) or '^$').search(ligne)
    if not m or any(m.group(k) != v for k, v in attendu.items()):
        soucis.append('%s ne reconnait pas : %r' % (cle, ligne))
PIEGES = [
    ('Console.UserJoinRegex', 'Sat Oct 10 17:53:53 2026 [info   ] STKHost: 127.0.0.1:45266 has just connected. There are now 1 peers.'),
    ('Console.UserJoinRegex', '1: 127.0.0.1:45266 AI'),
    ('Console.UserLeaveRegex', 'Sat Oct 10 17:54:18 2026 [info   ] STKHost: 127.0.0.1:45266 has just disconnected. There are now 0 peers.'),
    ('Console.UserLeaveRegex', 'Sat Oct 10 17:54:18 2026 [info   ] ServerLobby: Resetting the server to its initial state.'),
    ('Console.AppReadyRegex', 'Sat Oct 10 17:53:44 2026 [info   ] STKHost: Host initialized.'),
    ('Console.AppReadyRegex', 'Sat Oct 10 17:54:21 2026 [info   ] STKHost: Listening has been stopped.'),
    ('Console.ThrowawayMessageRegex', D + '[info   ] ServerLobby: New player Bot 1 with online id 0 from 127.0.0.1:45266 with AI.'),
    ('Console.ThrowawayMessageRegex', 'Sat Oct 10 17:54:18 2026 [info   ] ServerLobby: Bot 1 disconnected'),
    ('Console.ThrowawayMessageRegex', 'Sat Oct 10 17:53:44 2026 [info   ] main: Creating a LAN server \'TeamKit\'.'),
]
for cle, ligne in PIEGES:
    if py(cles[cle]).search(ligne):
        soucis.append('%s attrape une ligne qui n est pas pour lui : %r' % (cle, ligne))
print('ok   console                      %d lignes reelles, %d pieges' % (len(ESSAIS), len(PIEGES)))

print()
if soucis:
    print('%d probleme(s) :' % len(soucis))
    print('\n'.join('  NON  ' + s for s in soucis))
    sys.exit(1)
print('Tout est bon.')
