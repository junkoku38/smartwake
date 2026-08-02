#!/usr/bin/env python3
"""Génère des captures d'écran du README pour SmartWAKE et SmartWAKE Card.

Produit des maquettes en SVG converties en PNG, reproduisant le rendu de la
carte Lovelace et de la page de l'intégration dans Home Assistant.
"""

from __future__ import annotations

from pathlib import Path

import cairosvg

# Couleurs HA (thème sombre)
BG = "#111418"
CARD_BG = "#1c1c1c"
TEXT = "#e1e1e1"
SUBTEXT = "#9a9a9a"
AMBER = "#ef9f27"
AMBER_BG = "rgba(239, 159, 39, 0.16)"
TEAL = "#0f6e56"
RED = "#a32d2d"
DIVIDER = "#2a2a2a"
RADIUS = 12

W = 420
PAD = 20

def _card(content: str, h: int = 200) -> str:
    return f'''<rect x="0" y="0" width="{W}" height="{h}" fill="{BG}"/>
<rect x="{PAD}" y="{PAD}" width="{W-2*PAD}" height="{h-2*PAD}" rx="{RADIUS}" fill="{CARD_BG}"/>
{content}'''

def _text(x: float, y: float, s: str, size: int = 13, color: str = TEXT, weight: str = "normal") -> str:
    return f'<text x="{x}" y="{y}" font-family="Segoe UI, Roboto, sans-serif" font-size="{size}" fill="{color}" font-weight="{weight}">{s}</text>'

def _circle(cx: float, cy: float, r: float, fill: str) -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>'

def _round_rect(x: float, y: float, w: float, h: float, r: float, fill: str) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"/>'

def _icon(cx: float, cy: float, path: str, size: int = 20, color: str = AMBER) -> str:
    return f'<g transform="translate({cx-size/2},{cy-size/2}) scale({size/24})"><path d="{path}" fill="{color}"/></g>'

# Icônes Material Design (simplifiées)
ICON_ALARM = "M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4M12.5,7L12.5,12.25L17,14.92L16.25,16.15L11,13V7L12.5,7Z"
ICON_BELL = "M14,17H7V15H14A3,3 0 0,0 17,12V8H5V6H19V12A6,6 0 0,1 14,17M12,2A2,2 0 0,1 14,4H10A2,2 0 0,1 12,2Z"
ICON_SKIP = "M6,5V19L10,12L6,5M10,5V19L14,12L10,5M14,5V19L18,12L14,5Z"
ICON_RESET = "M12,5V1L7,6L12,11V7A5,5 0 0,1 17,12A5,5 0 0,1 12,17A5,5 0 0,1 7,12H5A7,7 0 0,0 12,19A7,7 0 0,0 19,12A7,7 0 0,0 12,5Z"
ICON_BRIEFING = "M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4M7,13L9,15L13,11L12,10L9,13L8,12L7,13Z"

def _generate_normal() -> str:
    """Carte en état normal (idle)."""
    y = PAD + 10
    content = ""

    # Badge ambre
    content += _circle(PAD+28, y+10, 18, AMBER_BG)
    content += _icon(PAD+28, y+10, ICON_ALARM, 18, AMBER)

    # Nom + sous-titre
    content += _text(PAD+58, y+8, "Réveil semaine", 14, TEXT, "600")
    content += _text(PAD+58, y+24, "Sonne aujourd'hui · weekend", 12, SUBTEXT)

    # Toggle
    content += _round_rect(W-PAD-44, y, 36, 20, 10, AMBER)
    content += _circle(W-PAD-16, y+10, 8, "#fff")

    # Heure
    y2 = y + 50
    content += _text(PAD+8, y2+20, "07:00", 40, TEXT, "600")
    content += _text(PAD+120, y2+6, "dans 8 h 12 min", 13, SUBTEXT)

    # Jours
    y3 = y2 + 40
    jours = [("L", True), ("Ma", True), ("Me", True), ("J", True), ("V", True), ("S", False), ("D", False)]
    for i, (label, on) in enumerate(jours):
        cx = PAD + 8 + i * 42
        fill = AMBER_BG if on else "#2a2a2a"
        color = "#b87514" if on else SUBTEXT
        content += _circle(cx + 16, y3 + 16, 16, fill)
        content += _text(cx + 10, y3 + 20, label, 11, color, "600")

    # Chips
    y4 = y3 + 50
    chips = [("Weekend", TEAL), ("Vacances sco", None)]
    cx = PAD + 8
    for label, color in chips:
        fill = f"rgba(29, 158, 117, 0.15)" if color else "#2a2a2a"
        text_color = "#0f6e56" if color else SUBTEXT
        w_chip = len(label) * 7 + 24
        content += _round_rect(cx, y4, w_chip, 26, 13, fill)
        content += _text(cx + 12, y4 + 17, label, 11, text_color)
        cx += w_chip + 8

    # Actions rapides
    y5 = y4 + 36
    actions = [("Skip 1×", ICON_SKIP), ("Briefing", ICON_BRIEFING), ("Bilan", ICON_BRIEFING)]
    cx = PAD + 8
    for label, icon in actions:
        w_chip = len(label) * 7 + 28
        content += _round_rect(cx, y5, w_chip, 26, 13, "#2a2a2a")
        content += _icon(cx + 14, y5 + 13, icon, 14, SUBTEXT)
        content += _text(cx + 24, y5 + 17, label, 11, SUBTEXT)
        cx += w_chip + 8

    # Reset discret
    content += _icon(W - PAD - 20, y5 + 13, ICON_RESET, 14, "#555")

    # Footer
    y6 = y5 + 40
    content += f'<line x1="{PAD}" y1="{y6}" x2="{W-PAD}" y2="{y6}" stroke="{DIVIDER}" stroke-width="1"/>'
    content += _text(PAD+8, y6+18, "🔊 35%", 12, SUBTEXT)
    content += _text(PAD+70, y6+18, "🔥 −30 min", 12, SUBTEXT)
    content += _text(PAD+160, y6+18, "🌅 20 min", 12, SUBTEXT)

    # Stats
    y7 = y6 + 30
    stats = [("142", "Réveils"), ("28", "Snoozes"), ("142", "Stops")]
    for i, (val, label) in enumerate(stats):
        cx = PAD + 8 + i * 125
        content += _round_rect(cx, y7, 115, 40, 8, "#2a2a2a")
        content += _text(cx + 40, y7 + 18, val, 17, TEXT, "600")
        content += _text(cx + 20, y7 + 33, label, 9, SUBTEXT)

    h = y7 + 50 + PAD
    return _card(content, h)

def _generate_ringing() -> str:
    """Carte en état sonnerie (ringing)."""
    y = PAD + 10
    content = ""

    # Bordure pulsée
    content += f'<rect x="{PAD-2}" y="{PAD-2}" width="{W-2*PAD+4}" height="200" rx="{RADIUS+2}" fill="none" stroke="{AMBER}" stroke-width="2" opacity="0.6"/>'

    # Badge plein
    content += _circle(PAD+28, y+10, 18, AMBER)
    content += _icon(PAD+28, y+10, ICON_BELL, 18, "#fff")

    # Nom
    content += _text(PAD+58, y+8, "Ça sonne", 14, "#b87514", "600")
    content += _text(PAD+58, y+24, "Debout !", 12, SUBTEXT)

    # Heure
    y2 = y + 50
    content += _text(PAD+8, y2+20, "07:00", 40, TEXT, "600")

    # Boutons Snooze / Stop
    y3 = y2 + 60
    # Snooze
    content += _round_rect(PAD+8, y3, 180, 50, 10, "#2a2a2a")
    content += _icon(PAD+50, y3+25, ICON_BELL, 24, "#b87514")
    content += _text(PAD+70, y3+22, "Snooze", 13, "#b87514", "600")
    content += _text(PAD+70, y3+38, "5 min", 11, SUBTEXT)

    # Stop
    content += _round_rect(PAD+200, y3, 180, 50, 10, "rgba(226, 75, 74, 0.12)")
    content += _icon(PAD+242, y3+25, ICON_BELL, 24, RED)
    content += _text(PAD+262, y3+30, "Stop", 13, RED, "600")

    # Escalade
    y4 = y3 + 65
    content += _text(PAD+8, y4, "⏱ Escalade après 5 min · lumières 100% + volume max", 11, SUBTEXT)

    h = y4 + 20 + PAD
    return _card(content, h)

def _generate_prewake() -> str:
    """Carte en état pré-réveil (prewake) avec anneau de progression."""
    y = PAD + 10
    content = ""

    # Badge ambre
    content += _circle(PAD+28, y+10, 18, AMBER_BG)
    content += _icon(PAD+28, y+10, ICON_ALARM, 18, AMBER)

    # Anneau de progression (cercle partiel)
    cx_ring = PAD + 28
    cy_ring = y + 10
    r_ring = 22
    # Fond de l'anneau
    content += f'<circle cx="{cx_ring}" cy="{cy_ring}" r="{r_ring}" fill="none" stroke="{AMBER_BG}" stroke-width="3"/>'
    # Progression (60%)
    import math
    angle = 0.6 * 2 * math.pi - math.pi/2
    ex = cx_ring + r_ring * math.cos(angle)
    ey = cy_ring + r_ring * math.sin(angle)
    content += f'<path d="M {cx_ring} {cy_ring-r_ring} A {r_ring} {r_ring} 0 1 1 {ex:.1f} {ey:.1f}" fill="none" stroke="{AMBER}" stroke-width="3" stroke-linecap="round"/>'

    # Nom + sous-titre
    content += _text(PAD+58, y+8, "Réveil semaine", 14, TEXT, "600")
    content += _text(PAD+58, y+24, "Préparation · 12 min avant sonnerie", 12, SUBTEXT)

    # Toggle
    content += _round_rect(W-PAD-44, y, 36, 20, 10, AMBER)
    content += _circle(W-PAD-16, y+10, 8, "#fff")

    # Heure
    y2 = y + 50
    content += _text(PAD+8, y2+20, "07:00", 40, TEXT, "600")
    content += _text(PAD+120, y2+6, "dans 12 min", 13, SUBTEXT)

    # Barre de progression
    y3 = y2 + 40
    content += _round_rect(PAD+8, y3, W-2*PAD-16, 6, 3, "#2a2a2a")
    content += _round_rect(PAD+8, y3, (W-2*PAD-16)*0.6, 6, 3, AMBER)
    content += _text(PAD+8, y3+20, "60% · 12 min restantes", 11, SUBTEXT)
    content += _text(W-PAD-100, y3+20, "aube 20 min · chauffe 30 min", 11, SUBTEXT)

    # Jours
    y4 = y3 + 40
    jours = [("L", True), ("Ma", True), ("Me", True), ("J", True), ("V", True), ("S", False), ("D", False)]
    for i, (label, on) in enumerate(jours):
        cx = PAD + 8 + i * 42
        fill = AMBER_BG if on else "#2a2a2a"
        color = "#b87514" if on else SUBTEXT
        content += _circle(cx + 16, y4 + 16, 16, fill)
        content += _text(cx + 10, y4 + 20, label, 11, color, "600")

    h = y4 + 40 + PAD
    return _card(content, h)

def _generate_snoozed() -> str:
    """Carte en état snoozed avec compte à rebours."""
    y = PAD + 10
    content = ""

    # Badge teal (snooze)
    content += _circle(PAD+28, y+10, 18, "rgba(29, 158, 117, 0.15)")
    content += _icon(PAD+28, y+10, ICON_BELL, 18, TEAL)

    # Nom + sous-titre
    content += _text(PAD+58, y+8, "Réveil semaine", 14, TEXT, "600")
    content += _text(PAD+58, y+24, "Re-sonne dans 3 min 42 s", 12, TEAL)

    # Toggle
    content += _round_rect(W-PAD-44, y, 36, 20, 10, AMBER)
    content += _circle(W-PAD-16, y+10, 8, "#fff")

    # Heure
    y2 = y + 50
    content += _text(PAD+8, y2+20, "07:00", 40, TEXT, "600")

    # Jours
    y3 = y2 + 40
    jours = [("L", True), ("Ma", True), ("Me", True), ("J", True), ("V", True), ("S", False), ("D", False)]
    for i, (label, on) in enumerate(jours):
        cx = PAD + 8 + i * 42
        fill = AMBER_BG if on else "#2a2a2a"
        color = "#b87514" if on else SUBTEXT
        content += _circle(cx + 16, y3 + 16, 16, fill)
        content += _text(cx + 10, y3 + 20, label, 11, color, "600")

    # Snooze restants
    y4 = y3 + 50
    content += _round_rect(PAD+8, y4, 120, 26, 13, "#2a2a2a")
    content += _icon(PAD+22, y4+13, ICON_BELL, 14, AMBER)
    content += _text(PAD+32, y4+17, "1/2 snoozes", 11, AMBER)

    h = y4 + 40 + PAD
    return _card(content, h)

def _generate_integration() -> str:
    """Maquette de la page de l'intégration dans HA."""
    h = 280
    content = f'''<rect x="0" y="0" width="{W}" height="{h}" fill="{BG}"/>
<rect x="{PAD}" y="{PAD}" width="{W-2*PAD}" height="{h-2*PAD}" rx="{RADIUS}" fill="{CARD_BG}"/>'''

    # Logo
    content += _circle(PAD+30, PAD+30, 20, AMBER)
    content += _icon(PAD+30, PAD+30, ICON_ALARM, 24, "#fff")

    # Nom
    content += _text(PAD+62, PAD+28, "SmartWAKE", 16, TEXT, "600")
    content += _text(PAD+62, PAD+46, "Réveil progressif", 12, SUBTEXT)

    # Entités
    y = PAD + 70
    entities = [
        ("switch.reveil_actif", "on", AMBER),
        ("sensor.reveil_statut", "idle", SUBTEXT),
        ("sensor.reveil_prochain_reveil", "demain 07:00", SUBTEXT),
        ("time.reveil_heure", "07:00", SUBTEXT),
        ("select.reveil_jours", "tous", SUBTEXT),
        ("number.reveil_snooze_min", "5", SUBTEXT),
    ]
    for eid, state, color in entities:
        content += _text(PAD+20, y, eid, 12, SUBTEXT)
        content += _text(W-PAD-80, y, state, 12, color, "600")
        content += f'<line x1="{PAD+10}" y1="{y+8}" x2="{W-PAD-10}" y2="{y+8}" stroke="{DIVIDER}" stroke-width="1"/>'
        y += 25

    return content

def main() -> None:
    screens = {
        "normal": _generate_normal(),
        "ringing": _generate_ringing(),
        "prewake": _generate_prewake(),
        "snoozed": _generate_snoozed(),
        "integration": _generate_integration(),
    }

    # Carte
    card_dir = Path("/tmp/opencode/smartwake-card/screenshots")
    card_dir.mkdir(exist_ok=True)
    for name in ("normal", "ringing", "prewake", "snoozed"):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{screens[name].split(chr(10))[-1]}">' + screens[name] + '</svg>'
        # Hauteur calculée
        h = 200
        if name == "normal": h = 320
        elif name == "ringing": h = 200
        elif name == "prewake": h = 240
        elif name == "snoozed": h = 200
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}">' + screens[name] + '</svg>'
        out = card_dir / f"{name}.png"
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(out), output_width=W*2, output_height=h*2)
        print(f"  {name}.png  {out.stat().st_size/1024:.0f} Ko")

    # Intégration
    integ_dir = Path("/tmp/opencode/smartwake/screenshots")
    integ_dir.mkdir(exist_ok=True)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="280">' + screens["integration"] + '</svg>'
    out = integ_dir / "integration.png"
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(out), output_width=W*2, output_height=280*2)
    print(f"  integration.png  {out.stat().st_size/1024:.0f} Ko")

if __name__ == "__main__":
    main()