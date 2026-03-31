"""
8-bit style SVG icons for plant types. Muted palette for modern panel UI.
Each icon is 24x24 viewBox, pixel-grid style. Each plant slug gets a stable icon via get_icon_svg(slug).
"""
# Muted palette
_FILL = "#8b9a7a"      # sage
_STROKE = "#6b7b5c"   # darker green
_POT = "#a09888"      # warm gray

_GENERIC = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="10" rx="6" ry="5"/><rect x="10" y="16" width="4" height="4"/><rect x="9" y="20" width="6" height="2"/></svg>"""

# icon_id -> inline SVG (24x24). Many plant slugs use deterministic fallback to one of these.
ICONS = {
    "golden-torch": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><rect x="9" y="4" width="2" height="2"/><rect x="8" y="6" width="4" height="2"/><rect x="8" y="8" width="4" height="10"/><rect x="7" y="18" width="6" height="2"/><rect x="6" y="20" width="8" height="2"/></svg>""",
    "bunny-ear": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="8" cy="10" rx="5" ry="6"/><ellipse cx="16" cy="10" rx="5" ry="6"/><rect x="8" y="16" width="8" height="4"/><rect x="7" y="20" width="10" height="2"/></svg>""",
    "barrel-cactus": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><rect x="6" y="4" width="12" height="3"/><rect x="5" y="7" width="14" height="3"/><rect x="4" y="10" width="16" height="4"/><rect x="5" y="14" width="14" height="3"/><rect x="6" y="17" width="12" height="3"/><rect x="8" y="20" width="8" height="2"/></svg>""",
    "mammillaria": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><circle cx="12" cy="6" r="3"/><circle cx="7" cy="12" r="2.5"/><circle cx="17" cy="12" r="2.5"/><circle cx="12" cy="16" r="2.5"/><rect x="9" y="19" width="6" height="2"/><rect x="8" y="21" width="8" height="1"/></svg>""",
    "small-column-cactus": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><rect x="10" y="2" width="2" height="4"/><rect x="9" y="6" width="4" height="12"/><rect x="8" y="18" width="6" height="2"/><rect x="7" y="20" width="8" height="2"/></svg>""",
    "fiddle-leaf-fig": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="8" rx="8" ry="6"/><rect x="10" y="14" width="4" height="8"/><rect x="9" y="20" width="6" height="2"/></svg>""",
    "money-tree": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><rect x="10" y="20" width="4" height="2"/><rect x="11" y="14" width="2" height="6"/><circle cx="12" cy="6" r="4"/><circle cx="8" cy="10" r="2.5"/><circle cx="16" cy="10" r="2.5"/><circle cx="12" cy="12" r="2"/></svg>""",
    "bonsai": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><rect x="3" y="19" width="18" height="2" fill="#a09888"/><rect x="5" y="17" width="14" height="2" fill="#a09888"/><path d="M12 17 L12 12" fill="none"/><path d="M12 12 Q9 10 8 7 Q10 9 12 11" fill="none"/><path d="M12 12 Q15 9 17 6 Q14 8 12 10" fill="none"/><ellipse cx="8" cy="6" rx="3" ry="2.5"/><ellipse cx="16" cy="5" rx="2.5" ry="2"/><ellipse cx="12" cy="4" rx="2" ry="2"/></svg>""",
    # Extra variants so each plant gets a deterministic unique icon
    "houseplant": _GENERIC,
    "foliage-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M12 4 L14 10 L12 16 L10 10 Z"/><rect x="10" y="18" width="4" height="3"/><rect x="9" y="21" width="6" height="1"/></svg>""",
    "foliage-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="9" rx="7" ry="5"/><rect x="11" y="14" width="2" height="6"/><rect x="9" y="20" width="6" height="2"/></svg>""",
    "foliage-3": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><circle cx="12" cy="8" r="5"/><rect x="10" y="13" width="4" height="8"/><rect x="8" y="21" width="8" height="1"/></svg>""",
    "foliage-4": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M12 2 L15 8 L12 14 L9 8 Z"/><path d="M8 12 L12 18 L16 12 L12 6 Z"/><rect x="10" y="20" width="4" height="2"/></svg>""",
    "foliage-5": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="10" cy="7" rx="4" ry="3"/><ellipse cx="14" cy="9" rx="4" ry="3"/><rect x="10" y="14" width="4" height="6"/><rect x="9" y="20" width="6" height="2"/></svg>""",
    "trailing-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M4 8 Q8 6 12 8 Q16 10 20 8"/><path d="M6 14 Q10 12 14 14 Q18 16 22 14"/><rect x="10" y="18" width="4" height="4"/></svg>""",
    "trailing-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="6" cy="6" rx="3" ry="2"/><ellipse cx="12" cy="10" rx="4" ry="3"/><ellipse cx="18" cy="14" rx="3" ry="2"/><rect x="9" y="18" width="6" height="3"/></svg>""",
    "fern-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M12 2 L12 22"/><path d="M12 4 L8 10 L12 8 L16 10"/><path d="M12 10 L8 16 L12 14 L16 16"/><path d="M12 16 L8 20 L12 18 L16 20"/><rect x="10" y="20" width="4" height="2"/></svg>""",
    "fern-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M12 3 L10 8 L12 7 L14 8"/><path d="M12 8 L9 14 L12 12 L15 14"/><path d="M12 14 L9 20 L12 18 L15 20"/><rect x="10" y="20" width="4" height="2"/></svg>""",
    "palm-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M12 2 L12 8"/><path d="M12 4 L8 12 M12 4 L16 12"/><path d="M12 8 L6 18 M12 8 L18 18"/><rect x="10" y="18" width="4" height="4"/></svg>""",
    "palm-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="5" rx="6" ry="3"/><rect x="11" y="8" width="2" height="12"/><rect x="9" y="20" width="6" height="2"/></svg>""",
    "succulent-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><circle cx="12" cy="8" r="4"/><circle cx="8" cy="14" r="3"/><circle cx="16" cy="14" r="3"/><rect x="9" y="19" width="6" height="2"/></svg>""",
    "succulent-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="10" rx="5" ry="4"/><rect x="10" y="14" width="4" height="6"/><rect x="8" y="20" width="8" height="2"/></svg>""",
    "succulent-3": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><rect x="9" y="6" width="6" height="4"/><rect x="8" y="10" width="8" height="6"/><rect x="9" y="16" width="6" height="3"/><rect x="8" y="19" width="8" height="2"/></svg>""",
    "flower-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><circle cx="12" cy="8" r="3"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="12" cy="14" r="2"/><rect x="11" y="16" width="2" height="6"/><rect x="9" y="22" width="6" height="1"/></svg>""",
    "flower-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><circle cx="12" cy="9" r="4"/><rect x="11" y="13" width="2" height="8"/><rect x="9" y="21" width="6" height="1"/></svg>""",
    "herb-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M12 20 L12 6"/><path d="M12 8 L8 12 L12 10 L16 12"/><path d="M12 12 L9 16 L12 14 L15 16"/><rect x="10" y="20" width="4" height="2"/></svg>""",
    "herb-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="8" rx="5" ry="3"/><rect x="11" y="11" width="2" height="10"/><rect x="9" y="21" width="6" height="1"/></svg>""",
    "veg-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="10" rx="6" ry="5"/><rect x="10" y="15" width="4" height="6"/><rect x="9" y="21" width="6" height="1"/></svg>""",
    "veg-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><circle cx="12" cy="9" r="5"/><path d="M7 14 Q12 18 17 14"/><rect x="10" y="18" width="4" height="3"/></svg>""",
    "tree-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="6" rx="5" ry="4"/><ellipse cx="12" cy="12" rx="6" ry="4"/><ellipse cx="12" cy="18" rx="5" ry="3"/><rect x="11" y="20" width="2" height="2"/></svg>""",
    "tree-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M12 2 L14 8 L12 7 L10 8"/><path d="M12 8 L15 14 L12 12 L9 14"/><path d="M12 14 L14 20 L12 18 L10 20"/><rect x="11" y="20" width="2" height="2"/></svg>""",
    "grass-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M6 22 L8 10 M12 22 L12 8 M18 22 L16 10"/><rect x="10" y="20" width="4" height="2"/></svg>""",
    "grass-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M4 20 L12 6 L20 20"/><rect x="10" y="20" width="4" height="2"/></svg>""",
    "bulb-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="10" rx="4" ry="5"/><rect x="11" y="15" width="2" height="6"/><rect x="9" y="21" width="6" height="1"/></svg>""",
    "shrub-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="8" rx="6" ry="4"/><ellipse cx="12" cy="16" rx="5" ry="4"/><rect x="11" y="20" width="2" height="2"/></svg>""",
    "climber-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><path d="M8 20 L10 14 L12 18 L14 10 L16 4"/><rect x="10" y="20" width="4" height="2"/></svg>""",
    "easy-1": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><ellipse cx="12" cy="9" rx="6" ry="5"/><rect x="10" y="14" width="4" height="6"/><rect x="9" y="20" width="6" height="2"/></svg>""",
    "easy-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="{fill}" stroke="{stroke}" stroke-width="0.5"><rect x="9" y="6" width="6" height="4"/><rect x="8" y="10" width="8" height="8"/><rect x="7" y="18" width="10" height="3"/></svg>""",
}

# Keys used for deterministic fallback when icon_id is a plant slug not in ICONS
_ICON_VARIANT_KEYS = [
    "golden-torch", "bunny-ear", "barrel-cactus", "mammillaria", "small-column-cactus",
    "fiddle-leaf-fig", "money-tree", "foliage-1", "foliage-2", "foliage-3", "foliage-4", "foliage-5",
    "trailing-1", "trailing-2", "fern-1", "fern-2", "palm-1", "palm-2",
    "succulent-1", "succulent-2", "succulent-3", "flower-1", "flower-2",
    "herb-1", "herb-2", "veg-1", "veg-2", "tree-1", "tree-2", "grass-1", "grass-2",
    "bulb-1", "shrub-1", "climber-1", "easy-1", "easy-2",
]


# Slug aliases: library slug -> preferred icon key (so new cacti use the right shape)
_ICON_ALIASES = {
    "clustered-column-cactus": "golden-torch",
    "bunny-ear-cactus": "bunny-ear",
    "mammillaria-cluster-cactus": "mammillaria",
    "ficus-bonsai": "bonsai",
    "juniper-bonsai": "bonsai",
    "japanese-maple-bonsai": "bonsai",
    "jade-bonsai": "bonsai",
    "pine-bonsai": "bonsai",
    "indoor-bonsai-general": "bonsai",
}


def get_icon_svg(icon_id: str) -> str:
    """Return inline SVG for icon_id. Each plant slug gets a stable icon via deterministic fallback."""
    icon_id = _ICON_ALIASES.get(icon_id, icon_id)
    tpl = ICONS.get(icon_id)
    if not tpl:
        n = len(_ICON_VARIANT_KEYS)
        idx = hash(icon_id) % n
        if idx < 0:
            idx += n
        tpl = ICONS.get(_ICON_VARIANT_KEYS[idx], _GENERIC)
    return tpl.format(fill=_FILL, stroke=_STROKE)
