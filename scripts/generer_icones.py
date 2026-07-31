#!/usr/bin/env python3
"""Génère les images de marque de SmartWAKE.

Depuis Home Assistant 2026.3, une intégration personnalisée embarque ses images
dans `custom_components/<domain>/brand/`, et elles priment sur le CDN
brands.home-assistant.io. Aucune contribution externe n'est donc nécessaire.

Contraintes du dépôt home-assistant/brands, reprises ici :
  - PNG, fond transparent de préférence
  - icône carrée 256x256, version hDPI 512x512
  - logo paysage, plus petit côté entre 128 et 256 px (256-512 en hDPI)
  - image détourée, sans marge superflue

Le dessin est fait en supersampling x4 puis réduit, faute de moteur SVG.

Usage : python3 scripts/generer_icones.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Palette — l'ambre reprend l'accent de la carte Lovelace
AMBRE = (239, 159, 39, 255)
AMBRE_FONCE = (216, 122, 22, 255)
SOLEIL = (255, 209, 102, 255)
CADRAN = (255, 251, 242, 255)
NUIT = (58, 42, 20, 255)

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "custom_components" / "smartwake" / "brand"

SS = 4  # facteur de supersampling


def _degrade_vertical(taille: int, haut: tuple, bas: tuple) -> Image.Image:
    """Dégradé vertical, utilisé comme remplissage via masque."""
    grad = Image.new("RGBA", (1, taille))
    px = grad.load()
    for y in range(taille):
        t = y / max(1, taille - 1)
        px[0, y] = tuple(round(h + (b - h) * t) for h, b in zip(haut, bas))
    return grad.resize((taille, taille))


def dessiner_icone(taille: int) -> Image.Image:
    """Réveil stylisé : cadran clair, soleil levant, cloches et pieds."""
    n = taille * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx = n / 2
    r_corps = n * 0.36          # rayon du boîtier
    cy = n * 0.56               # centre, décalé pour loger les cloches

    # ── Cloches ──────────────────────────────────────────────
    r_cloche = n * 0.115
    for signe in (-1, 1):
        bx = cx + signe * r_corps * 0.78
        by = cy - r_corps * 0.74
        d.ellipse([bx - r_cloche, by - r_cloche, bx + r_cloche, by + r_cloche],
                  fill=AMBRE_FONCE)

    # ── Pieds ────────────────────────────────────────────────
    l_pied, h_pied = n * 0.075, n * 0.13
    for signe in (-1, 1):
        px = cx + signe * r_corps * 0.62
        d.rounded_rectangle(
            [px - l_pied / 2, cy + r_corps * 0.72,
             px + l_pied / 2, cy + r_corps * 0.72 + h_pied],
            radius=l_pied / 2, fill=AMBRE_FONCE,
        )

    # ── Boîtier, en dégradé ──────────────────────────────────
    masque = Image.new("L", (n, n), 0)
    ImageDraw.Draw(masque).ellipse(
        [cx - r_corps, cy - r_corps, cx + r_corps, cy + r_corps], fill=255
    )
    img.paste(_degrade_vertical(n, AMBRE, AMBRE_FONCE), (0, 0), masque)

    # ── Cadran ───────────────────────────────────────────────
    r_cadran = r_corps * 0.78
    d.ellipse([cx - r_cadran, cy - r_cadran, cx + r_cadran, cy + r_cadran],
              fill=CADRAN)

    # ── Soleil levant, découpé par la ligne d'horizon ────────
    horizon = cy + r_cadran * 0.30
    calque = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    cd = ImageDraw.Draw(calque)

    r_soleil = r_cadran * 0.44
    sy = horizon - r_soleil * 0.30
    cd.ellipse([cx - r_soleil, sy - r_soleil, cx + r_soleil, sy + r_soleil],
               fill=SOLEIL)

    # Rayons obliques
    ep = max(1, int(n * 0.022))
    for angle in (-62, -34, -8, 18, 44):
        a = math.radians(angle - 90)
        x0 = cx + math.cos(a) * r_soleil * 1.30
        y0 = sy + math.sin(a) * r_soleil * 1.30
        x1 = cx + math.cos(a) * r_soleil * 1.80
        y1 = sy + math.sin(a) * r_soleil * 1.80
        cd.line([x0, y0, x1, y1], fill=SOLEIL, width=ep, joint="curve")

    # Tout ce qui dépasse sous l'horizon est retiré
    cd.rectangle([0, horizon, n, n], fill=(0, 0, 0, 0))
    img.alpha_composite(calque)

    # Ligne d'horizon
    demi = r_cadran * 0.82
    d.line([cx - demi, horizon, cx + demi, horizon], fill=NUIT,
           width=max(1, int(n * 0.019)))

    # Le cadran est redécoupé : les rayons ne doivent pas déborder du boîtier
    decoupe = Image.new("L", (n, n), 0)
    ImageDraw.Draw(decoupe).ellipse(
        [cx - r_corps, cy - r_corps, cx + r_corps, cy + r_corps], fill=255
    )
    fond = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    fond.paste(img, (0, 0))
    hors = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    hors.paste(img, (0, 0), Image.eval(decoupe, lambda v: 255 - v))
    # On conserve cloches et pieds, dessinés hors du boîtier
    img = Image.alpha_composite(hors, Image.composite(
        img, Image.new("RGBA", (n, n), (0, 0, 0, 0)), decoupe))

    # Détourage : le dépôt brands demande le minimum d'espace vide sur les
    # bords. On recadre sur le contenu, puis on rétablit un carré exact.
    boite = img.getbbox()
    if boite:
        img = img.crop(boite)
        cote = max(img.width, img.height)
        carre = Image.new("RGBA", (cote, cote), (0, 0, 0, 0))
        carre.alpha_composite(img, ((cote - img.width) // 2,
                                    (cote - img.height) // 2))
        img = carre

    return img.resize((taille, taille), Image.LANCZOS)


def _police(taille: int) -> ImageFont.FreeTypeFont:
    for chemin in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(chemin).exists():
            return ImageFont.truetype(chemin, taille)
    return ImageFont.load_default()


def dessiner_logo(hauteur: int) -> Image.Image:
    """Logo paysage : icône suivie du nom."""
    icone = dessiner_icone(hauteur)
    ecart = int(hauteur * 0.14)

    police = _police(int(hauteur * 0.42))
    mesure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    boite = mesure.textbbox((0, 0), "SmartWAKE", font=police)
    l_texte, h_texte = boite[2] - boite[0], boite[3] - boite[1]

    largeur = hauteur + ecart + l_texte
    img = Image.new("RGBA", (largeur, hauteur), (0, 0, 0, 0))
    img.alpha_composite(icone, (0, 0))

    d = ImageDraw.Draw(img)
    d.text((hauteur + ecart - boite[0], (hauteur - h_texte) / 2 - boite[1]),
           "SmartWAKE", font=police, fill=AMBRE_FONCE)
    return img


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)

    fichiers = {
        "icon.png": dessiner_icone(256),
        "icon@2x.png": dessiner_icone(512),
        "logo.png": dessiner_logo(256),
        "logo@2x.png": dessiner_logo(512),
    }
    for nom, image in fichiers.items():
        chemin = SORTIE / nom
        # Interlacé et optimisé, comme recommandé pour le web
        image.save(chemin, "PNG", optimize=True, interlace=1)
        print(f"  {nom:<14} {image.width}x{image.height}  "
              f"{chemin.stat().st_size / 1024:.1f} Ko")

    print(f"\nÉcrit dans {SORTIE.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
