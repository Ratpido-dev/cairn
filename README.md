# Cairn

**The Hearthstone tracker that runs *natively* on Linux.** No Electron, no Overwolf, no
Wine on the tracker's side: Cairn reads the logs the game writes on its own, from Linux,
in **~170 MB of private memory / 260 MB RSS** — measured, with ten windows open and a
full game loaded. Expect more after a long session. For comparison, Firestone under Wine
sits around 4 GB.

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/PySide6-Qt%20Quick-41CD52?logo=qt&logoColor=white)
[![tests](https://github.com/Ratpido-dev/cairn/actions/workflows/tests.yml/badge.svg)](https://github.com/Ratpido-dev/cairn/actions/workflows/tests.yml)
![Tests](https://img.shields.io/badge/tests-402%20passing-10B981)
![License](https://img.shields.io/badge/license-MIT-F59E0B)
![Platform](https://img.shields.io/badge/Linux-Wayland%20%7C%20X11-0B0F17?logo=linux&logoColor=white)

**English** · [Français](README.fr.md)

<p align="center">
  <img src="docs/captures/apercu-en-jeu.jpg" alt="Cairn over Hearthstone" width="900">
</p>

<p align="center">
  <img src="docs/captures/apercu-panneau-deck.png" alt="Deck panel" height="420">
  <img src="docs/captures/apercu-panneau-adversaire.png" alt="Opponent panel" height="420">
  <img src="docs/captures/apercu-compteurs.png" alt="Contextual counters" height="130">
</p>

---

## Why this one rather than another

There are excellent Hearthstone trackers. None of them is designed for Linux.

| | Cairn | HDT | Firestone |
|---|---|---|---|
| Platform | **native Linux** | Windows (via Wine) | Windows / Overwolf (via Wine) |
| Memory measured here | **~170 MB private** | not measured | **1.5 to 4.2 GB** |
| Second Wine prefix to run | **no** | yes | yes |
| Reads game memory / injects | **no** | yes | yes |
| Ships Wayland window rules | **yes** | no | no |
| Account, telemetry | **none** | optional | yes |

Running a Windows tracker under Wine, next to a Hearthstone that already runs under
Wine, means paying twice. On an 8 GB laptop, Firestone caused **OOM kills of the game
itself** on my machine: that is what started this project.

Cairn never talks to the game. It reads a text file Hearthstone writes of its own
accord, and displays what it finds there. Nothing to inject, nothing to work around,
nothing that can break at Blizzard's next update.

## What it takes to work on Linux — and what nobody tells you

Two obstacles make game tracking hard on Linux. Both are solved.

**1. Hearthstone caps its logs at 10 MB.** Past that, it writes `Truncating log…` and
then **closes the file descriptor**. On Windows it recreates the file and carries on;
under Wine that step fails and tracking goes permanently blind — usually in the middle
of your third game. The fix is a single line, `FileSizeLimit.Int=-1` in the
`client.config` of the install folder, and Cairn writes it for you (launcher button, or
`cairn-doctor --fix`).

**2. Under Wayland, a client cannot place itself.** Coordinates are ignored and the
compositor centers everything. Cairn installs KWin rules `cairn-pos-*` in *Remember*
mode, one per widget, and above all a `layer=overlay` rule — the only layer that draws
**on top of an exclusive-fullscreen game**. On other desktops, the windows carry stable
titles and the app_id `cairn`: enough to target them from GNOME Extensions, Hyprland,
Sway or `wmctrl`.

## Installation

```bash
git clone https://github.com/Ratpido-dev/cairn.git
cd cairn
./install.sh            # --desktop for a desktop icon
```

No `sudo`, no system package: everything goes into `~/.local`, following the XDG spec.
The script creates an isolated Python environment, downloads the card database,
configures Hearthstone (logging + size cap) and installs the shortcut. **Cairn** is then
in your application menu.

Requirements: Python ≥ 3.10 and its `venv` module (`python3-venv` on Debian/Ubuntu,
`python3-virtualenv` on Fedora, bundled with `python` on Arch). PySide6 brings Qt along
by itself.

```bash
cairn                   # the tracker
cairn-doctor [--fix]    # full diagnosis of the installation
cairn-cards --check     # is the card database up to date?
./install.sh --uninstall  # your games and settings are kept
```

The Wine/Proton prefix is **detected** (Lutris, Steam/Proton, Heroic, Bottles,
PlayOnLinux, plain wine). If in doubt: `export CAIRN_HS_PREFIX=/path/to/the/prefix`.

## What Cairn shows

<p align="center">
  <img src="docs/captures/apercu-launcher.png" alt="Launcher" width="460">
</p>

**A deck that stays alive.** Remaining, drawn, draw odds — and above all **what enters**
the deck mid-game: bombs, plagues, Rafaam's gifts, Azalina's copies. Every row carries
its card's artwork.

**Top and bottom of deck.** Hearthstone does not log deck order: every card that enters
it gets `ZONE_POSITION value=0`. The only way to know a card sits at the bottom is to
know the effect that put it there — Cairn infers this from the cards' **text** at
download time, so there is no per-expansion list to maintain.

**Counters that only appear when they matter.** Rafaam, corpses, Zarimi's dragons,
Yogg's spell cycle — a counter shows up only if the card justifying it has been seen, or
if the opposing class could play it. And they are **symmetric**: when Azalina copies the
other side's opening, the counter appears on your side too.

**Godfrey's Atlas**, the queue of overdrawn cards in the order they will come back, at
their reduced cost, on both sides. **Resurrection pools** on hover: what a card can
*actually* bring back, not the theoretical list. **The opponent's hand**, with the turn
each card arrived and where it came from. **Secret candidates** for the class of the
secret that was played — not the opposing hero's class, which is not the same thing.

Plus: game and turn timers, thinking time per player, potential damage on each side
(summoning sickness included), automatic deck import from `Decks.log`, local history and
winrates per deck and per class.

<p align="center">
  <img src="docs/captures/apercu-widgets.png" alt="Floating widgets: counters, timer, potential damage, opponent's hand" width="420">
</p>

## Your winrate against *that deck*, not against its class

A per-class win rate mixes together decks that have nothing in common. Measured on my
own archives: **39% against Warlock on average — but 29% against a Rafaam deck and 75%
against the rest.** The class average hid two opposite matchups, and that is exactly the
information that was missing.

So Cairn identifies the opposing archetype during the game, and keeps statistics per
archetype. Two mechanisms, strongest first:

- **the reference lists you paste.** You give it a deck code, Cairn decodes it and
  compares every card seen leaving the opponent's deck against every known list for that
  class. Seven unremarkable cards that all appear in the same list amount to a
  signature;
- **hard-coded signature cards**, as a fallback, when no list is known for that class.

**82% of archived games get a label, and 0% false positives** over 6,000 simulated
draws. Three deliberate choices explain those numbers:

1. **The label is the signature card or the name of the pasted list, never a meta
   archetype name.** "Warlock · Rafaam", not "Rafaamlock": it is verifiable, it does not
   go stale at the next patch, and it requires following no meta reports.
2. **A generated card proves nothing.** A Rafaam obtained from a Discover does not make
   a Rafaam deck — otherwise a Thief Priest, who plays other people's cards, would be
   filed under its victim's archetype.
3. **No proof means "unknown".** An opponent who concedes on turn 2 has shown nothing:
   they count toward their class, not toward an archetype. Guessing would corrupt the
   one number we are after.

Nothing is scraped: HSGuru explicitly forbids automated agents, and depending on a
third-party site would have made Cairn stop working the day their page changed. Pasting
a code works offline and lets you choose when to refresh.

## Spectating, and launching

**Spectator mode.** Hearthstone logs a spectated game exactly like your own — same
format, same tags, both hands revealed. Without a guard, those games entered your
history and skewed your winrates. Cairn learns your account id on its own, recognises
the games where you are neither player, and **displays them without recording them**.

**Launching the game from the launcher.** There is no single way to launch Hearthstone
on Linux, so Cairn does not look for a game *called* Hearthstone: it looks for the one
that **lives in the prefix it already watches**. Lutris and `.desktop` entries are found
that way; for a homemade script, a hand-rolled `umu-run` or Bottles, the launcher's
"launch command" field always wins. A shortcut for the common cases, a manual mechanism
for all the others.

## It does not go stale in silence

A balance patch changes costs and effects. A tracker that fails to notice displays lies
— and does not say so.

At every start, Cairn compares the HTTP fingerprint of its card database against
HearthstoneJSON's (one `HEAD` request, at most every 12 h) and re-downloads if the game
was patched. And because a patch can change not the *data* but the **effect** of a card
whose behaviour the code assumes, the download also compares the text of the cards wired
into the engine, and warns when one of them has been reworded. `cairn-doctor` keeps the
warning visible until it has been dealt with.

## Privacy

Cairn talks to nobody. There is no account, no telemetry, no server: everything lives in
`~/.local/share/cairn`. The only network requests are for the card database and the
artwork, from HearthstoneJSON.

Game sharing exists, but it is **off by default** and asked once, explicitly. A
`Power.log` contains two identifiers per player — the battletag and the `GameAccountId`
— which the GDPR counts as personal data. The hard part is not the user, who consents
for themselves, but **their opponent**, who never asked for any of this: identifiers are
therefore replaced with stable tokens, salted per installation, before anything leaves.
A test verifies that a pseudonymised game **replays identically** — the protection costs
nothing, which is what makes it sustainable.

**This is not a setting.** There is no way to send a raw log: a "do not anonymise"
option could only ever have been ticked at the expense of someone who was not there to
have a say.

Once sharing is accepted, games are sent on their own between matches, in the
background, resuming after failures — never while you are playing. The reasoning is in
[`docs/COLLECTE.md`](docs/COLLECTE.md) (French), and the service that receives them — a
ready-to-deploy Cloudflare Worker — in [`collecte/`](collecte/).

The reference games in this repository went through that same anonymiser.

## Why this opt-in to keep games exists

It is the only feature in Cairn that sends anything anywhere, so it deserves to say why
it exists rather than existing quietly.

**A log parser only gets fixed by games it did not anticipate.** The parser does not
break on the cards I tested: it breaks on the expansion that shipped yesterday, on an
effect nobody had run into, on a card that moves entities in a way never seen before.
The engine's nastiest cases — Godfrey's Atlas, Azalina's copies, cards sent to the
bottom of the deck — were all written against real games, never against imagined ones.
And I play one class, one format, one rank: my own games are a tiny, biased sample.

**There is no open corpus of Hearthstone games.** The data exists — the big trackers
have been collecting it for years — but it stays with them. A question as simple as "on
average, on which turn is this card played at this rank?" has no public answer. A rules
simulator, an AI project, a meta study have nothing to build on.

**Nobody is obliged.** Sharing is off by default, the question is asked once, the answer
can be changed at any time from the launcher, and whatever was queued is then deleted.
Cairn is strictly identical either way: no feature is reserved for those who accept,
there is no account, no leaderboard, no reminder.

### What you actually get out of it

No feature is reserved for those who accept — that would contradict everything above.
But saying "it's free and gets you nothing" would be false, so here is what it actually
gives you:

**A backup of your games somewhere other than your disk.** Hearthstone keeps only a
handful of session folders and deletes the rest without warning — measured here: **out
of 239 games played, only 92 still had their log.** Cairn archives them locally, but a
failing disk takes the archive down with everything else. Since the corpus is public to
read, `tools/corpus.py --installation <your-id>` hands yours back, from any machine,
with no account and no password.

**The tracker you use improves on games it did not anticipate.** The engine's nastiest
cases — Godfrey's Atlas, Azalina's copies, cards sent to the bottom of the deck — were
all written against real games, never against imagined ones. A game where Cairn gets it
wrong is exactly the one needed to fix it, and the fix comes back to you at the next
update. You play one class, one format, one rank: together, the sample stops being tiny.

**Access to the data, instead of handing it to someone else for free.** This is the deep
difference with proprietary trackers: they collect your games too, but you never see
them again. Here the corpus downloads whole, by anyone, without a key. A question like
"on average, on which turn is this card played at this rank?" today has **no public
answer** — that is what a rules simulator, an AI project or a meta study is missing, and
that is exactly what an open corpus unlocks.

**And it costs you nothing visible.** About 500 KB per session, sent in the background
between games — never while you play. No account, no leaderboard, no reminder. You
change your mind whenever you want from the launcher, and whatever was queued is
deleted.

The one real cost is written below, and it is final: **what is published cannot be taken
back.** That is why pseudonymisation is not optional.

### Why the corpus is open

The collection point **serves what it received**, to whoever asks, with no account and
no key:

```bash
curl https://<collect>/parties                         # the index, as JSON
python tools/corpus.py --url https://<collect> --extraire   # everything, unpacked
```

This was not the case at first — the endpoint was write-only — and the reasoning that
changed my mind fits in one sentence: **keeping this corpus closed would have protected
nobody.** What arrives there is already pseudonymised on the player's machine,
unconditionally; there is nothing left to protect once it has left. A closed endpoint
would therefore have added nothing to anyone's privacy — it would merely have asked
players to give their games to **someone** rather than to everyone. That is exactly the
deal the other trackers already offer, and precisely what this project has no wish to
repeat.

Open, the deal becomes honest: you contribute to a resource you can use.
`tools/corpus.py --installation <your-id>` also hands back your own uploads: the id is
displayed — and copyable — in the launcher, under *Game sharing*. It is also what makes
a deletion request actionable: without it, "erase my data" would be an untreatable
sentence.

Two things worth knowing before saying yes, because they are true:

- the `install_id` **groups** the games of a single installation. That is what makes the
  corpus useful — a run of games is richer than a pile — and it is also what makes it
  possible to say "these 400 games come from the same person", without ever being able
  to say which one. Since the pseudonymisation salt is per-installation, two
  contributors can never be cross-referenced with each other;
- **publishing is irreversible in practice.** A file downloaded by a third party cannot
  be recalled. Deletion on request empties the endpoint, not the copies.

Contributing does not require running Linux, by the way: `tools/windows/` archives the
sessions of a Windows machine as a scheduled task, with a README and `.bat` shortcuts for
anyone who would rather not see a terminal.

Whoever hosts their own collection point decides: `OUVERT = "oui"` in
[`collecte/wrangler.toml`](collecte/wrangler.toml) opens reading, any other value closes
it again.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e . -r requirements.txt
.venv/bin/python -m pytest                  # 402 tests
.venv/bin/python tools/panel.py --replay    # demo without playing, throwaway history
.venv/bin/python tools/screenshot.py        # reproducible screenshots, offscreen
.venv/bin/python tools/stats.py             # winrates and recent games
.venv/bin/python tools/corpus.py --liste    # what the public corpus contains
```

The reference games are versioned **compressed and pseudonymised** (1.3 MB instead of
21) and decompressed on demand: the tests run on a fresh clone, downloading nothing but
the card database.

**The CI refuses to lie.** Most tests need the card database; without it they do not
fail, they *skip* — 202 out of 386 — and pytest still prints green. A CI that announces
"all is well" after running 43% of the suite is worse than a red one. So the workflow
downloads the database before the tests, then `tools/ci_check_skips.py` reads the JUnit
report back and **fails beyond 10 skipped tests**. Two Python versions, both ends of the
advertised range (3.10 and 3.13).

**Architecture.** `power_log.py` (tokenizer, reads only
`GameState.DebugPrint(Power|Game)` lines) → `game_state.py` (state machine) →
`deck_view.py` (**a pure function recomputed at every poll**, never fragile incremental
state) → `ui/bridge.py` (Qt bridge) → QML. The counters are a declarative registry with
triggers (`counters.py`), not a stack of `if`s.

Details and decisions in [`docs/CAHIER_DES_CHARGES.md`](docs/CAHIER_DES_CHARGES.md) and
[`docs/COMPARAISON-FIRESTONE.md`](docs/COMPARAISON-FIRESTONE.md) (both in French);
version history in [`CHANGELOG.md`](CHANGELOG.md).

## License

[MIT](LICENSE) — © 2026 Ratpido.

An independent project, **not affiliated with Blizzard Entertainment**. Hearthstone is a
trademark of Blizzard Entertainment, Inc. Cairn merely reads the logs the game writes
itself: it injects nothing, reads no process memory and does not modify the game.

Card data and artwork: [HearthstoneJSON](https://hearthstonejson.com/), downloaded on
demand and not redistributed here. Interface built on PySide6 / Qt (LGPLv3).
