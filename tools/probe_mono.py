#!/usr/bin/env python3
"""Sonde exploratoire — lire la mémoire de Hearthstone sous Wine, depuis Linux.

NE FAIT PAS PARTIE DE CAIRN. C'est une expérience isolée, en LECTURE SEULE,
destinée à répondre à une seule question avant d'investir dans le module
« MindVision natif » du cahier des charges (§4.3) :

    la marche des structures de Mono tient-elle à travers Wine ?

Elle procède par étapes, et s'arrête à la première qui échoue — l'endroit où
elle s'arrête EST le résultat.

    M1  lire un octet de la mémoire du jeu        (le verrou ptrace)
    M2  localiser mono-2.0-bdwgc.dll dans /proc   (le module est-il mappé ?)
    M3  parser ses en-têtes PE DEPUIS LA RAM      (Wine mappe-t-il comme Windows ?)
    M4  trouver mono_get_root_domain et en tirer
        l'adresse du domaine racine               (le point d'entrée de tout)
    M5  vérifier que ce pointeur mène quelque part de plausible

Aucune écriture, aucune injection, aucun appel de fonction dans le jeu : on
lit des octets, rien d'autre.

Prérequis : Hearthstone doit tourner, et le noyau doit autoriser la lecture
(cf. le message d'erreur de M1, qui explique quoi faire).

Usage :  python tools/probe_mono.py [pid]
"""

from __future__ import annotations

import ctypes
import os
import re
import struct
import subprocess
import sys
from dataclasses import dataclass

MONO_DLL = "mono-2.0-bdwgc.dll"

_libc = ctypes.CDLL("libc.so.6", use_errno=True)


class _IOVec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("len", ctypes.c_size_t)]


_libc.process_vm_readv.restype = ctypes.c_ssize_t
_libc.process_vm_readv.argtypes = [
    ctypes.c_int, ctypes.POINTER(_IOVec), ctypes.c_ulong,
    ctypes.POINTER(_IOVec), ctypes.c_ulong, ctypes.c_ulong,
]


# ---- affichage --------------------------------------------------------------

def etape(n: int, titre: str) -> None:
    print(f"\n\033[1mM{n} — {titre}\033[0m")


def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def ko(msg: str) -> None:
    print(f"  \033[31m✗\033[0m {msg}")


def info(msg: str) -> None:
    print(f"    {msg}")


def abandon(msg: str, conseil: str = "") -> None:
    ko(msg)
    if conseil:
        print(f"\n\033[33m{conseil}\033[0m")
    sys.exit(1)


# ---- lecture mémoire --------------------------------------------------------

class Memoire:
    """Lecture seule de la mémoire d'un autre process, par process_vm_readv."""

    def __init__(self, pid: int):
        self.pid = pid
        self.lectures = 0

    def lire(self, adresse: int, taille: int) -> bytes | None:
        tampon = (ctypes.c_char * taille)()
        local = _IOVec(ctypes.cast(tampon, ctypes.c_void_p), taille)
        distant = _IOVec(ctypes.c_void_p(adresse), taille)
        n = _libc.process_vm_readv(
            self.pid, ctypes.byref(local), 1, ctypes.byref(distant), 1, 0
        )
        self.lectures += 1
        if n != taille:
            return None
        return bytes(tampon)

    def pointeur(self, adresse: int) -> int | None:
        brut = self.lire(adresse, 8)
        return struct.unpack("<Q", brut)[0] if brut else None

    def u32(self, adresse: int) -> int | None:
        brut = self.lire(adresse, 4)
        return struct.unpack("<I", brut)[0] if brut else None

    def chaine(self, adresse: int, maxi: int = 128) -> str:
        brut = self.lire(adresse, maxi)
        if not brut:
            return ""
        return brut.split(b"\0", 1)[0].decode("utf-8", "replace")


@dataclass
class Region:
    debut: int
    fin: int
    perms: str
    chemin: str

    @property
    def taille(self) -> int:
        return self.fin - self.debut


def regions(pid: int) -> list[Region]:
    out = []
    with open(f"/proc/{pid}/maps", encoding="utf-8", errors="replace") as f:
        for ligne in f:
            m = re.match(r"([0-9a-f]+)-([0-9a-f]+) (\S+) \S+ \S+ \S+\s*(.*)", ligne)
            if m:
                out.append(Region(int(m.group(1), 16), int(m.group(2), 16),
                                  m.group(3), m.group(4).strip()))
    return out


def trouver_pid() -> int | None:
    r = subprocess.run(["pgrep", "-f", r"Hearthstone\.exe"],
                       capture_output=True, text=True)
    for ligne in r.stdout.split():
        pid = int(ligne)
        if pid == os.getpid():
            continue
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "replace")
        except OSError:
            continue
        # écarte les shells qui contiennent juste la chaîne dans leur ligne
        if "Hearthstone.exe" in cmd and "pgrep" not in cmd:
            return pid
    return None


# ---- PE : en-têtes lus depuis la mémoire vive -------------------------------

@dataclass
class Exports:
    base: int
    noms: dict[str, int]      # nom -> adresse absolue


def lire_exports(mem: Memoire, base: int) -> Exports | None:
    """Parse le répertoire d'exports d'un PE **tel qu'il est mappé en RAM**.

    C'est la vraie question de M3 : Wine charge-t-il les DLL comme Windows,
    c'est-à-dire avec des RVA utilisables tels quels depuis le début du module ?
    """
    entete = mem.lire(base, 2)
    if entete != b"MZ":
        info(f"pas de signature MZ à 0x{base:x} (lu : {entete!r})")
        return None
    e_lfanew = mem.u32(base + 0x3C)
    if e_lfanew is None or e_lfanew > 0x1000:
        info("e_lfanew absurde — en-tête illisible")
        return None
    pe = base + e_lfanew
    if mem.lire(pe, 4) != b"PE\0\0":
        info(f"pas de signature PE à 0x{pe:x}")
        return None

    magic = struct.unpack("<H", mem.lire(pe + 24, 2))[0]
    if magic == 0x20B:        # PE32+ (64 bits)
        rep = pe + 24 + 112
        bits = 64
    elif magic == 0x10B:      # PE32
        rep = pe + 24 + 96
        bits = 32
    else:
        info(f"magic d'en-tête optionnel inconnu : 0x{magic:x}")
        return None
    info(f"PE valide, {bits} bits")

    export_rva = mem.u32(rep)
    if not export_rva:
        info("pas de répertoire d'exports")
        return None

    d = base + export_rva
    nb_noms = mem.u32(d + 24)
    rva_fonctions = mem.u32(d + 28)
    rva_noms = mem.u32(d + 32)
    rva_ordinaux = mem.u32(d + 36)
    if None in (nb_noms, rva_fonctions, rva_noms, rva_ordinaux) or nb_noms > 100_000:
        info("répertoire d'exports incohérent")
        return None

    noms: dict[str, int] = {}
    table_noms = mem.lire(base + rva_noms, 4 * nb_noms)
    table_ord = mem.lire(base + rva_ordinaux, 2 * nb_noms)
    if not table_noms or not table_ord:
        info("tables d'exports illisibles")
        return None
    for i in range(nb_noms):
        rva_nom = struct.unpack_from("<I", table_noms, 4 * i)[0]
        nom = mem.chaine(base + rva_nom, 96)
        ordinal = struct.unpack_from("<H", table_ord, 2 * i)[0]
        rva_fn = mem.u32(base + rva_fonctions + 4 * ordinal)
        if nom and rva_fn:
            noms[nom] = base + rva_fn
    return Exports(base=base, noms=noms)


def domaine_racine(mem: Memoire, adresse_fonction: int) -> tuple[int | None, bytes]:
    """Extrait l'adresse du domaine racine de ``mono_get_root_domain``.

    Sur x86-64 cette fonction se réduit presque toujours à deux instructions :

        48 8b 05 <disp32>    mov rax, [rip + disp32]   ; la variable statique
        c3                   ret

    On décode le déplacement plutôt que d'appeler la fonction : appeler
    supposerait d'injecter du code, ce que cette sonde s'interdit.
    """
    code = mem.lire(adresse_fonction, 16)
    if not code:
        return None, b""
    if code[0:3] == b"\x48\x8b\x05":
        disp = struct.unpack_from("<i", code, 3)[0]
        variable = adresse_fonction + 7 + disp     # RIP pointe après l'instruction
        return mem.pointeur(variable), code
    return None, code


def _lisible(cartes: list[Region], adresse: int) -> bool:
    return any(r.debut <= adresse < r.fin and "r" in r.perms for r in cartes)


def _nom_plausible(txt: str) -> bool:
    """Un nom d'assembly, pas un chemin.

    MonoAssembly place ``basedir`` (« C:\\Program Files… ») AVANT ``aname.name``
    dans la structure : s'arrêter à la première chaîne lisible ramène le chemin
    et jamais le nom. On écarte donc explicitement ce qui ressemble à un chemin.
    """
    return (
        2 < len(txt) < 64
        and all(32 <= ord(c) < 127 for c in txt)
        and "/" not in txt
        and "\\" not in txt
        and ":" not in txt
    )


ASSEMBLIES_CONNUES = ("mscorlib", "System", "Assembly-CSharp", "UnityEngine",
                      "System.Core", "Mono.Security")


def chercher_assemblies(
    mem: Memoire, domaine: int, cartes: list[Region], fenetre: int = 0x1200
) -> tuple[int, list[str]] | None:
    """Retrouve ``MonoDomain->domain_assemblies`` sans coder son offset en dur.

    UnitySpy fige cet offset par version de Mono, ce qui casse à chaque montée
    d'Unity. On le DÉCOUVRE plutôt : on essaie chaque pointeur de la structure
    comme tête de GSList, et on retient celui dont les maillons mènent à des
    objets portant des noms d'assemblies reconnaissables (« mscorlib »…).
    Le jour où Blizzard change de version, la sonde retrouve l'offset seule.
    """
    tete_struct = mem.lire(domaine, fenetre)
    if not tete_struct:
        return None

    for offset in range(0, fenetre - 8, 8):
        maillon = struct.unpack_from("<Q", tete_struct, offset)[0]
        if not maillon or not _lisible(cartes, maillon):
            continue
        noms: list[str] = []
        vus = set()
        courant = maillon
        # GSList : { gpointer data; GSList *next; }
        while courant and courant not in vus and len(noms) < 200:
            vus.add(courant)
            noeud = mem.lire(courant, 16)
            if not noeud:
                break
            donnee, suivant = struct.unpack("<QQ", noeud)
            if donnee and _lisible(cartes, donnee):
                # MonoAssembly : on relève TOUTES les chaînes atteignables du
                # début de la structure. S'arrêter à la première ramènerait
                # « basedir » et jamais « aname.name ».
                entete = mem.lire(donnee, 0x60)
                if entete:
                    for o in range(0, 0x60, 8):
                        champ = struct.unpack_from("<Q", entete, o)[0]
                        if champ and _lisible(cartes, champ):
                            txt = mem.chaine(champ, 64)
                            if _nom_plausible(txt):
                                noms.append(txt)
            courant = suivant
        # une liste d'assemblies contient forcément le cœur de la BCL
        if sum(1 for n in noms if n in ASSEMBLIES_CONNUES) >= 2:
            # dédoublonne en gardant l'ordre de parcours
            uniques = list(dict.fromkeys(noms))
            return offset, uniques
    return None


# ---- déroulé ----------------------------------------------------------------

def main() -> int:
    print("\033[1mSonde Mono — lecture seule de Hearthstone sous Wine\033[0m")

    pid = int(sys.argv[1]) if len(sys.argv) > 1 else trouver_pid()
    if pid is None:
        abandon("Hearthstone.exe est introuvable.",
                "Lance le jeu, attends l'écran d'accueil, puis relance la sonde.")
    print(f"  process : {pid}")

    mem = Memoire(pid)
    cartes = regions(pid)
    print(f"  régions mémoire : {len(cartes)}")

    # ---- M1 : le verrou ptrace ---------------------------------------------
    etape(1, "lire la mémoire du jeu")
    lisible = next((r for r in cartes if "r" in r.perms and r.taille > 4096), None)
    if lisible is None or mem.lire(lisible.debut, 8) is None:
        err = ctypes.get_errno()
        scope = "?"
        try:
            scope = open("/proc/sys/kernel/yama/ptrace_scope").read().strip()
        except OSError:
            pass
        abandon(
            f"lecture refusée (errno {err} : {os.strerror(err)}) — ptrace_scope = {scope}",
            "Le noyau interdit de lire un process qui n'est pas ton descendant.\n"
            "Pour la durée de l'expérience seulement :\n\n"
            "    sudo sysctl kernel.yama.ptrace_scope=0\n\n"
            "Et pour remettre la protection ensuite (ou au prochain redémarrage,\n"
            "qui la rétablit tout seul) :\n\n"
            "    sudo sysctl kernel.yama.ptrace_scope=1",
        )
    ok(f"lecture autorisée (première région à 0x{lisible.debut:x})")

    # ---- M2 : le module Mono ------------------------------------------------
    etape(2, f"localiser {MONO_DLL}")
    mono = [r for r in cartes if MONO_DLL.lower() in r.chemin.lower()]
    if not mono:
        pe_charges = sorted({os.path.basename(r.chemin) for r in cartes
                             if r.chemin.lower().endswith(".dll")})
        abandon(f"{MONO_DLL} n'est pas mappé.",
                "DLL vues : " + (", ".join(pe_charges[:15]) or "aucune") +
                "\nLe jeu est peut-être encore au chargement — réessaie dans 30 s.")
    base = min(r.debut for r in mono)
    total = sum(r.taille for r in mono)
    ok(f"mappé en {len(mono)} région(s), base 0x{base:x}, {total // 1024} Ko")
    for r in mono[:6]:
        info(f"0x{r.debut:012x}-0x{r.fin:012x} {r.perms}")

    # ---- M3 : en-têtes PE lus en RAM ---------------------------------------
    etape(3, "parser les en-têtes PE depuis la RAM")
    exports = lire_exports(mem, base)
    if exports is None or not exports.noms:
        abandon("répertoire d'exports illisible.",
                "C'est la réponse recherchée : sous Wine le module n'est pas\n"
                "exploitable comme sous Windows, et l'approche UnitySpy ne\n"
                "transpose pas telle quelle.")
    ok(f"{len(exports.noms)} symboles exportés")
    interessants = [n for n in exports.noms
                    if n.startswith(("mono_get_root", "mono_domain", "mono_class_from",
                                     "mono_assembly", "mono_image", "mono_thread_attach"))]
    for n in sorted(interessants)[:10]:
        info(f"{n} → 0x{exports.noms[n]:x}")

    # ---- M4 : le domaine racine --------------------------------------------
    etape(4, "remonter au domaine racine")
    fn = exports.noms.get("mono_get_root_domain")
    if fn is None:
        abandon("mono_get_root_domain n'est pas exporté.",
                "Runtime différent de celui attendu.")
    domaine, code = domaine_racine(mem, fn)
    info("premiers octets : " + " ".join(f"{b:02x}" for b in code[:8]))
    if domaine is None:
        abandon("le prologue ne correspond pas au motif « mov rax,[rip+d32]; ret ».",
                "Pas rédhibitoire : il faudra désassembler pour de bon\n"
                "(capstone) au lieu de reconnaître un motif fixe.")
    ok(f"domaine racine = 0x{domaine:x}")

    # ---- M5 : le pointeur mène-t-il quelque part ? --------------------------
    etape(5, "vérifier que ce pointeur est plausible")
    hote = next((r for r in cartes if r.debut <= domaine < r.fin), None)
    if hote is None or "r" not in hote.perms:
        abandon("le pointeur ne tombe dans aucune région lisible.",
                "La variable statique n'a pas encore été initialisée : le jeu\n"
                "n'a peut-être pas fini de démarrer. Réessaie à l'écran d'accueil.")
    info(f"il pointe dans {hote.chemin or 'mémoire anonyme'} "
         f"({hote.perms}, {hote.taille // 1024} Ko)")
    tete = mem.lire(domaine, 64)
    if tete is None:
        abandon("structure du domaine illisible.")
    ok("structure lisible")
    info("64 premiers octets :")
    for i in range(0, 64, 16):
        mots = " ".join(f"{struct.unpack_from('<Q', tete, i + j)[0]:016x}"
                        for j in (0, 8))
        info(f"  +0x{i:02x}  {mots}")

    # ---- M6 : la liste des assemblies --------------------------------------
    etape(6, "trouver la liste des assemblies du domaine")
    trouve = chercher_assemblies(mem, domaine, cartes)
    if trouve is None:
        ko("aucune liste d'assemblies reconnue dans la structure du domaine.")
        info("Les quatre premières étapes suffisent à conclure : l'approche")
        info("est viable, seule la disposition exacte de MonoDomain reste à")
        info("établir pour cette version de Mono.")
    else:
        offset, noms = trouve
        ok(f"domain_assemblies à MonoDomain+0x{offset:x} — {len(noms)} assemblies")
        for n in noms[:18]:
            info(n)
        if len(noms) > 18:
            info(f"… et {len(noms) - 18} autres")
        if any("Assembly-CSharp" == n for n in noms):
            print("\n  \033[32mAssembly-CSharp atteint — c'est là que vit NetCache.\033[0m")

    if trouve is None:
        print(f"\n\033[33m\033[1mM1–M5 passent, M6 reste ouverte.\033[0m")
        print("L'approche est viable ; c'est la disposition de MonoDomain pour")
        print("cette version de Mono qui reste à établir.")
    else:
        print(f"\n\033[32m\033[1mLa chaîne tient de bout en bout.\033[0m")
    print(f"({mem.lectures} lectures mémoire, aucune écriture)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
