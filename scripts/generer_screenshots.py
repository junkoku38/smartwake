#!/usr/bin/env python3
"""Génère des captures d'écran propres pour SmartWAKE Card.

Reproduit fidèlement le rendu de la carte Lovelace en SVG, avec des positions
calculées pour éviter tout chevauchement de texte.
"""

from __future__ import annotations

import math
from pathlib import Path

import cairosvg

# ── Palette (thème sombre HA) ──────────────────────────────────
BG = "#111418"
CARD_BG = "#1c1c1c"
TEXT = "#e1e1e1"
SUBTEXT = "#9a9a9a"
AMBER = "#ef9f27"
AMBER_BG = "rgba(239, 159, 39, 0.16)"
AMBER_TEXT = "#b87514"
TEAL_BG = "rgba(29, 158, 117, 0.15)"
TEAL_TEXT = "#0f6e56"
RED_BG = "rgba(226, 75, 74, 0.12)"
RED_TEXT = "#a32d2d"
DIVIDER = "#2a2a2a"
RADIUS = 12
W = 440
PAD = 20
FONT = "Segoe UI, Roboto, -apple-system, sans-serif"

def _rrect(x, y, w, h, r, fill, stroke=None, sw=0):
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{sw}"'
    s += "/>"
    return s

def _circle(cx, cy, r, fill):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>'

def _text(x, y, s, size=13, color=TEXT, weight="normal", anchor="start"):
    import html
    s = html.escape(s)
    return f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{s}</text>'

def _icon_path(cx, cy, d, size=20, color=AMBER):
    scale = size / 24
    tx = cx - size / 2
    ty = cy - size / 2
    return f'<g transform="translate({tx},{ty}) scale({scale})"><path d="{d}" fill="{color}"/></g>'

# Icônes MDI simplifiées
I_ALARM = "M7,2L9,4V2H15V4L17,2H18V8H6V2H7M6,10H18V22H6V10M8,12V14H16V12H8M8,16V18H16V16H8Z"
I_BELL = "M14,17H7V15H14A3,3 0 0,0 17,12V8H5V6H19V12A6,6 0 0,1 14,17M12,2A2,2 0 0,1 14,4H10A2,2 0 0,1 12,2Z"
I_SKIP = "M6,5V19L10,12L6,5M10,5V19L14,12L10,5M14,5V19L18,12L14,5Z"
I_RESET = "M12,5V1L7,6L12,11V7A5,5 0 0,1 17,12A5,5 0 0,1 12,17A5,5 0 0,1 7,12H5A7,7 0 0,0 12,19A7,7 0 0,0 19,12A7,7 0 0,0 12,5Z"
I_VOICE = "M9,2A3,3 0 0,1 12,5V11A3,3 0 0,1 6,11V5A3,3 0 0,1 9,2M19,12A8,8 0 0,1 11,20V22H7V20A8,8 0 0,1 15,12H19M19,12A8,8 0 0,1 11,20V22H7V20A8,8 0 0,1 15,12H19Z"
I_BED = "M7,9A2,2 0 0,1 9,11A2,2 0 0,1 7,13A2,2 0 0,1 5,11A2,2 0 0,1 7,9M21,6V20H19V18H3V20H1V14H3V6H21M19,8H3V14H19V8Z"
I_VOLUME = "M14,3.23V5.29C16.89,6.15 19,8.83 19,12C19,15.17 16.89,17.85 14,18.71V20.77C18,19.86 21,16.28 21,12C21,7.72 18,4.14 14,3.23M16.5,12C16.5,10.23 15.5,8.71 14,7.97V16C15.5,15.29 16.5,13.76 16.5,12Z"
I_FIRE = "M17,4C17,6 16,7 15,8C14,9 13,10 13,12C13,14 14,15 15,15C16,15 17,14 17,12C17,10 16,9 17,4M7,4C7,6 8,7 9,8C10,9 11,10 11,12C11,14 10,15 9,15C8,15 7,14 7,12C7,10 8,9 7,4M12,2C12,4 13,5 14,6C15,7 16,8 16,10C16,12 15,13 14,13C13,13 12,12 12,10C12,8 13,7 12,2M12,14C14,14 16,15 16,17C16,19 14,22 12,22C10,22 8,19 8,17C8,15 10,14 12,14Z"
I_SUN = "M12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,2L14,5H10L12,2M12,22L10,19H14L12,22Z"

def _chip(x, y, label, icon=None, fill="#2a2a2a", color=SUBTEXT, icon_color=None):
    w = len(label) * 6.5 + (28 if icon else 16)
    s = _rrect(x, y, w, 26, 13, fill)
    if icon:
        s += _icon_path(x + 13, y + 13, icon, 14, icon_color or color)
        s += _text(x + 24, y + 17, label, 11, color)
    else:
        s += _text(x + 12, y + 17, label, 11, color)
    return s, w

def _day(cx, cy, label, on):
    fill = AMBER_BG if on else "#2a2a2a"
    color = AMBER_TEXT if on else SUBTEXT
    return _circle(cx, cy, 16, fill) + _text(cx, cy + 4, label, 11, color, "600", "middle")

def _stepper(x, y, label, value, unit=""):
    s = _text(x, y + 14, label, 12, SUBTEXT)
    val_x = x + 180
    s += _rrect(val_x, y, 28, 28, 8, "#2a2a2a")
    s += _text(val_x + 14, y + 19, "−", 16, TEXT, "600", "middle")
    s += _text(val_x + 48, y + 19, f"{value}{unit}", 13, TEXT, "600", "middle")
    s += _rrect(val_x + 68, y, 28, 28, 8, "#2a2a2a")
    s += _text(val_x + 82, y + 19, "+", 16, TEXT, "600", "middle")
    return s

# ── Carte : État normal ────────────────────────────────────────
def gen_normal():
    h = 340
    y = PAD
    s = ""

    # En-tête
    s += _circle(PAD + 22, y + 22, 18, AMBER_BG)
    s += _icon_path(PAD + 22, y + 22, I_ALARM, 18, AMBER)
    s += _text(PAD + 52, y + 18, "Réveil semaine", 14, TEXT, "600")
    s += _text(PAD + 52, y + 36, "Sonne aujourd'hui · weekend", 12, SUBTEXT)
    # Toggle
    s += _rrect(W - PAD - 40, y + 12, 36, 20, 10, AMBER)
    s += _circle(W - PAD - 16, y + 22, 8, "#fff")

    # Heure
    y2 = y + 56
    s += _text(PAD + 6, y2 + 28, "07:00", 40, TEXT, "600")
    s += _text(PAD + 128, y2 + 16, "dans 8 h 12 min", 13, SUBTEXT)

    # Jours
    y3 = y2 + 50
    for i, (lab, on) in enumerate([("L",1),("Ma",1),("Me",1),("J",1),("V",1),("S",0),("D",0)]):
        s += _day(PAD + 18 + i * 44, y3 + 16, lab, on)

    # Chips contextuelles
    y4 = y3 + 44
    chip, w1 = _chip(PAD + 6, y4, "Weekend", I_BED, TEAL_BG, TEAL_TEXT, TEAL_TEXT)
    s += chip
    chip2, w2 = _chip(PAD + 6 + w1 + 8, y4, "Vacances sco")
    s += chip2

    # Actions rapides
    y5 = y4 + 36
    chip3, w3 = _chip(PAD + 6, y5, "Skip 1×", I_SKIP)
    s += chip3
    chip4, w4 = _chip(PAD + 6 + w3 + 8, y5, "Briefing", I_VOICE)
    s += chip4
    chip5, w5 = _chip(PAD + 6 + w3 + w4 + 16, y5, "Bilan", I_BED)
    s += chip5
    # Reset discret à droite
    s += _icon_path(W - PAD - 16, y5 + 13, I_RESET, 14, "#555")

    # Footer
    y6 = y5 + 38
    s += f'<line x1="{PAD}" y1="{y6}" x2="{W-PAD}" y2="{y6}" stroke="{DIVIDER}" stroke-width="1"/>'
    specs_x = PAD + 6
    for icon, label in [(I_VOLUME, "35%"), (I_FIRE, "−30 min"), (I_SUN, "20 min")]:
        s += _icon_path(specs_x + 8, y6 + 18, icon, 14, SUBTEXT)
        s += _text(specs_x + 22, y6 + 22, label, 12, SUBTEXT)
        specs_x += len(label) * 7 + 50

    # Stats
    y7 = y6 + 32
    stats = [("142", "RÉVEILS"), ("28", "SNOOZES"), ("142", "STOPS")]
    sw = (W - 2 * PAD - 16) // 3
    for i, (val, lab) in enumerate(stats):
        sx = PAD + 6 + i * (sw + 8)
        s += _rrect(sx, y7, sw, 42, 8, "#2a2a2a")
        s += _text(sx + sw // 2, y7 + 20, val, 17, TEXT, "600", "middle")
        s += _text(sx + sw // 2, y7 + 34, lab, 9, SUBTEXT, "normal", "middle")

    h = y7 + 52 + PAD
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}"><rect width="{W}" height="{h}" fill="{BG}"/><rect x="{PAD}" y="{PAD}" width="{W-2*PAD}" height="{h-2*PAD}" rx="{RADIUS}" fill="{CARD_BG}"/>{s}</svg>'

# ── Carte : État sonnerie ──────────────────────────────────────
def gen_ringing():
    h = 220
    y = PAD
    s = ""

    # Bordure ambre
    s += f'<rect x="{PAD-2}" y="{PAD-2}" width="{W-2*PAD+4}" height="{h-2*PAD+4}" rx="{RADIUS+2}" fill="none" stroke="{AMBER}" stroke-width="2" opacity="0.5"/>'

    # Badge plein
    s += _circle(PAD + 22, y + 22, 18, AMBER)
    s += _icon_path(PAD + 22, y + 22, I_BELL, 18, "#fff")
    s += _text(PAD + 52, y + 18, "Ça sonne", 14, AMBER_TEXT, "600")
    s += _text(PAD + 52, y + 36, "Debout !", 12, SUBTEXT)

    # Heure
    y2 = y + 60
    s += _text(PAD + 6, y2 + 28, "07:00", 40, TEXT, "600")

    # Boutons
    y3 = y2 + 60
    bw = (W - 2 * PAD - 20) // 2
    # Snooze
    s += _rrect(PAD + 6, y3, bw, 54, 10, "#2a2a2a")
    s += _icon_path(PAD + 6 + bw // 2, y3 + 20, I_BELL, 24, AMBER_TEXT)
    s += _text(PAD + 6 + bw // 2, y3 + 44, "Snooze 5 min", 13, AMBER_TEXT, "600", "middle")
    # Stop
    s += _rrect(PAD + 12 + bw, y3, bw, 54, 10, RED_BG)
    s += _icon_path(PAD + 12 + bw + bw // 2, y3 + 20, I_BELL, 24, RED_TEXT)
    s += _text(PAD + 12 + bw + bw // 2, y3 + 44, "Stop", 13, RED_TEXT, "600", "middle")

    # Escalade
    y4 = y3 + 70
    s += _text(PAD + 6, y4, "⏱ Escalade après 5 min · lumières 100% + volume max", 11, SUBTEXT)

    h = y4 + 20 + PAD
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}"><rect width="{W}" height="{h}" fill="{BG}"/><rect x="{PAD}" y="{PAD}" width="{W-2*PAD}" height="{h-2*PAD}" rx="{RADIUS}" fill="{CARD_BG}"/>{s}</svg>'

# ── Carte : État pré-réveil ────────────────────────────────────
def gen_prewake():
    y = PAD
    s = ""

    # Badge + anneau
    cx = PAD + 22
    cy = y + 22
    s += _circle(cx, cy, 18, AMBER_BG)
    s += _icon_path(cx, cy, I_ALARM, 18, AMBER)
    # Anneau
    r = 24
    s += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{AMBER_BG}" stroke-width="3"/>'
    pct = 0.6
    angle = pct * 2 * math.pi - math.pi / 2
    ex = cx + r * math.cos(angle)
    ey = cy + r * math.sin(angle)
    s += f'<path d="M {cx} {cy-r} A {r} {r} 0 1 1 {ex:.1f} {ey:.1f}" fill="none" stroke="{AMBER}" stroke-width="3" stroke-linecap="round"/>'

    s += _text(PAD + 60, y + 18, "Réveil semaine", 14, TEXT, "600")
    s += _text(PAD + 60, y + 36, "Préparation · 12 min avant sonnerie", 12, SUBTEXT)
    # Toggle
    s += _rrect(W - PAD - 40, y + 12, 36, 20, 10, AMBER)
    s += _circle(W - PAD - 16, y + 22, 8, "#fff")

    # Heure
    y2 = y + 56
    s += _text(PAD + 6, y2 + 28, "07:00", 40, TEXT, "600")
    s += _text(PAD + 128, y2 + 16, "dans 12 min", 13, SUBTEXT)

    # Barre de progression
    y3 = y2 + 52
    bar_w = W - 2 * PAD - 12
    s += _rrect(PAD + 6, y3, bar_w, 6, 3, "#2a2a2a")
    s += _rrect(PAD + 6, y3, int(bar_w * pct), 6, 3, AMBER)
    s += _text(PAD + 6, y3 + 22, "60% · 12 min restantes", 11, SUBTEXT)
    s += _text(W - PAD - 6, y3 + 22, "aube 20 min · chauffe 30 min", 11, SUBTEXT, "normal", "end")

    # Jours
    y4 = y3 + 38
    for i, (lab, on) in enumerate([("L",1),("Ma",1),("Me",1),("J",1),("V",1),("S",0),("D",0)]):
        s += _day(PAD + 18 + i * 44, y4 + 16, lab, on)

    h = y4 + 40 + PAD
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}"><rect width="{W}" height="{h}" fill="{BG}"/><rect x="{PAD}" y="{PAD}" width="{W-2*PAD}" height="{h-2*PAD}" rx="{RADIUS}" fill="{CARD_BG}"/>{s}</svg>'

# ── Carte : État snoozé ────────────────────────────────────────
def gen_snoozed():
    y = PAD
    s = ""

    # Badge teal
    s += _circle(PAD + 22, y + 22, 18, TEAL_BG)
    s += _icon_path(PAD + 22, y + 22, I_BELL, 18, TEAL_TEXT)
    s += _text(PAD + 52, y + 18, "Réveil semaine", 14, TEXT, "600")
    s += _text(PAD + 52, y + 36, "Re-sonne dans 3 min 42 s", 12, TEAL_TEXT)
    # Toggle
    s += _rrect(W - PAD - 40, y + 12, 36, 20, 10, AMBER)
    s += _circle(W - PAD - 16, y + 22, 8, "#fff")

    # Heure
    y2 = y + 56
    s += _text(PAD + 6, y2 + 28, "07:00", 40, TEXT, "600")

    # Jours
    y3 = y2 + 50
    for i, (lab, on) in enumerate([("L",1),("Ma",1),("Me",1),("J",1),("V",1),("S",0),("D",0)]):
        s += _day(PAD + 18 + i * 44, y3 + 16, lab, on)

    # Snooze restants
    y4 = y3 + 44
    chip, _ = _chip(PAD + 6, y4, "1/2 snoozes", I_BELL, "#2a2a2a", AMBER, AMBER)
    s += chip

    h = y4 + 40 + PAD
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}"><rect width="{W}" height="{h}" fill="{BG}"/><rect x="{PAD}" y="{PAD}" width="{W-2*PAD}" height="{h-2*PAD}" rx="{RADIUS}" fill="{CARD_BG}"/>{s}</svg>'

# ── Page d'intégration ─────────────────────────────────────────
def gen_integration():
    h = 300
    y = PAD
    s = ""

    # Logo
    s += _circle(PAD + 28, y + 28, 22, AMBER)
    s += _icon_path(PAD + 28, y + 28, I_ALARM, 26, "#fff")
    s += _text(PAD + 64, y + 24, "SmartWAKE", 16, TEXT, "600")
    s += _text(PAD + 64, y + 44, "Réveil progressif", 12, SUBTEXT)

    # Entités
    y2 = y + 70
    entities = [
        ("switch.reveil_actif", "on"),
        ("sensor.reveil_statut", "idle"),
        ("sensor.reveil_prochain_reveil", "demain 07:00"),
        ("time.reveil_heure", "07:00"),
        ("select.reveil_jours", "tous"),
        ("number.reveil_snooze_min", "5"),
        ("binary_sensor.reveil_sonne_aujourd_hui", "on"),
    ]
    for eid, state in entities:
        color = AMBER if state in ("on",) else SUBTEXT
        s += _text(PAD + 16, y2, eid, 12, SUBTEXT)
        s += _text(W - PAD - 16, y2, state, 12, color, "600", "end")
        s += f'<line x1="{PAD+10}" y1="{y2+8}" x2="{W-PAD-10}" y2="{y2+8}" stroke="{DIVIDER}" stroke-width="1"/>'
        y2 += 26

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}"><rect width="{W}" height="{h}" fill="{BG}"/><rect x="{PAD}" y="{PAD}" width="{W-2*PAD}" height="{h-2*PAD}" rx="{RADIUS}" fill="{CARD_BG}"/>{s}</svg>'

def main():
    out = Path("/tmp/opencode/smartwake-card")
    for name, gen in [("normal", gen_normal), ("ringing", gen_ringing),
                      ("prewake", gen_prewake), ("snoozed", gen_snoozed)]:
        svg = gen()
        p = out / f"{name}.png"
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(p), output_width=W * 2)
        print(f"  {name}.png  {p.stat().st_size/1024:.0f} Ko")

    out2 = Path("/tmp/opencode/smartwake")
    svg = gen_integration()
    p = out2 / "integration.png"
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(p), output_width=W * 2)
    print(f"  integration.png  {p.stat().st_size/1024:.0f} Ko")

if __name__ == "__main__":
    main()