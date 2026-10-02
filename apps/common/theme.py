"""Validated portal palette and CSS overrides for the existing utility classes."""
import re


PALETTE_DEFAULTS = {
    "primary": "#4f46e5",
    "accent": "#7c3aed",
    "background": "#030712",
    "surface": "#111827",
    "raised_surface": "#1f2937",
    "text": "#f9fafb",
    "muted_text": "#9ca3af",
    "border": "#374151",
    "inverse_text": "#ffffff",
    "success": "#10b981",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "info": "#3b82f6",
    "invoice_background": "#ffffff",
    "invoice_surface": "#f8fafc",
    "invoice_text": "#1e293b",
    "invoice_muted_text": "#64748b",
    "invoice_border": "#e2e8f0",
}

FIELD_NAMES = {
    "primary": "primary_color",
    "accent": "accent_color",
    "background": "background_color",
    "surface": "surface_color",
    "raised_surface": "raised_surface_color",
    "text": "text_color",
    "muted_text": "muted_text_color",
    "border": "border_color",
    "inverse_text": "inverse_text_color",
    "success": "success_color",
    "warning": "warning_color",
    "error": "error_color",
    "info": "info_color",
    "invoice_background": "invoice_background_color",
    "invoice_surface": "invoice_surface_color",
    "invoice_text": "invoice_text_color",
    "invoice_muted_text": "invoice_muted_text_color",
    "invoice_border": "invoice_border_color",
}


def get_portal_colors(config):
    """Return only safe six-digit hex colors from a settings record or fallback map."""
    palette = {}
    for token, field in FIELD_NAMES.items():
        if isinstance(config, dict):
            candidate = config.get(field, PALETTE_DEFAULTS[token])
        else:
            candidate = getattr(config, field, PALETTE_DEFAULTS[token])
        palette[token] = candidate if isinstance(candidate, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", candidate) else PALETTE_DEFAULTS[token]
    return palette


def _class_selector(class_name):
    return f'[class~="{class_name}"]'


def build_portal_theme_css(palette):
    """Theme common Tailwind color utilities and states without changing layout classes."""
    variables = ";".join(f"--portal-{name.replace('_', '-')}: {value}" for name, value in palette.items())
    rules = [f":root{{{variables}}}"]

    neutral_bg = {
        "bg-gray-50": "background", "bg-gray-950": "background",
        "bg-gray-900": "surface", "bg-gray-800": "raised_surface", "bg-gray-700": "border",
        "bg-white": "surface", "bg-black": "background",
    }
    for utility, token in neutral_bg.items():
        rules.append(f"{_class_selector(utility)}{{background-color:var(--portal-{token.replace('_', '-')})!important}}")
    for utility in ("bg-gray-100", "bg-gray-200", "bg-gray-300", "bg-gray-400", "bg-gray-500", "bg-gray-600"):
        rules.append(f"{_class_selector(utility)}{{background-color:var(--portal-raised-surface)!important}}")

    opacity_values = (5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90)
    for family, token in (("gray-950", "background"), ("gray-900", "surface"), ("gray-800", "raised_surface"), ("gray-700", "border")):
        for opacity in opacity_values:
            rules.append(
                f'{_class_selector(f"bg-{family}/{opacity}")}{{background-color:color-mix(in srgb,var(--portal-{token.replace("_", "-")}) {opacity}%,transparent)!important}}'
            )

    for utility in ("text-gray-100", "text-gray-50", "text-gray-200"):
        rules.append(f"{_class_selector(utility)}{{color:var(--portal-text)!important}}")
    for utility in ("text-gray-300", "text-gray-400", "text-gray-500", "text-gray-600", "text-gray-700", "text-gray-800", "text-gray-900"):
        rules.append(f"{_class_selector(utility)}{{color:var(--portal-muted-text)!important}}")
    rules.append(f'{_class_selector("text-white")}{{color:var(--portal-inverse-text)!important}}')
    for utility in ("hover:text-white", "focus:text-white"):
        rules.append(f'{_class_selector(utility)}:hover{{color:var(--portal-inverse-text)!important}}')
    for utility in ("border-gray-700", "border-gray-800", "border-gray-900", "border-gray-600", "divide-gray-700", "divide-gray-800"):
        property_name = "border-color" if utility.startswith("border-") else "--tw-divide-opacity"
        if utility.startswith("divide-"):
            rules.append(f"{_class_selector(utility)}>*+*{{border-color:var(--portal-border)!important}}")
        else:
            rules.append(f"{_class_selector(utility)}{{{property_name}:var(--portal-border)!important}}")
    for utility in ("placeholder-gray-400", "placeholder-gray-500", "placeholder-gray-600"):
        rules.append(f"{_class_selector(utility)}::placeholder{{color:var(--portal-muted-text)!important}}")
    for family in ("gray-700", "gray-800", "gray-900"):
        for opacity in opacity_values:
            rules.append(f'{_class_selector(f"hover:bg-{family}/{opacity}")}:hover{{background-color:color-mix(in srgb,var(--portal-raised-surface) {opacity}%,transparent)!important}}')
        rules.append(f'{_class_selector(f"hover:bg-{family}")}:hover{{background-color:var(--portal-raised-surface)!important}}')

    primary_bg = tuple(f"bg-{family}-{shade}" for family in ("indigo", "purple", "brand") for shade in ("300", "400", "500", "600", "700", "800", "900"))
    for utility in primary_bg:
        rules.append(f"{_class_selector(utility)}{{background-color:var(--portal-primary)!important}}")
    for family, shades in (("brand", ("300", "400", "500", "600", "700", "800", "900")), ("indigo", ("300", "400", "500", "600", "700", "800", "900")), ("purple", ("300", "400", "500", "600", "700", "800", "900"))):
        for shade in shades:
            for opacity in opacity_values:
                rules.append(
                    f'{_class_selector(f"bg-{family}-{shade}/{opacity}")}{{background-color:color-mix(in srgb,var(--portal-primary) {opacity}%,transparent)!important}}'
                )
    for utility in ("hover:bg-indigo-500", "hover:bg-indigo-600", "hover:bg-purple-500", "hover:bg-purple-600", "hover:bg-brand-500", "hover:bg-brand-600"):
        rules.append(f'{_class_selector(utility)}:hover{{background-color:var(--portal-accent)!important}}')
    for utility in ("hover:from-purple-500", "hover:from-indigo-500"):
        rules.append(f'{_class_selector(utility)}:hover{{--tw-gradient-from:var(--portal-accent) var(--tw-gradient-from-position)!important}}')
    rules.append(f'{_class_selector("hover:to-indigo-500")}:hover{{--tw-gradient-to:var(--portal-primary) var(--tw-gradient-to-position)!important}}')
    for utility in ("text-indigo-300", "text-indigo-400", "text-brand-300", "text-brand-400", "text-brand-500", "text-brand-600", "text-purple-300", "text-purple-400", "text-purple-500", "text-purple-600"):
        rules.append(f"{_class_selector(utility)}{{color:var(--portal-accent)!important}}")
    for utility in ("hover:text-indigo-300", "hover:text-indigo-400", "hover:text-brand-300", "hover:text-brand-400", "hover:text-purple-300", "hover:text-purple-400"):
        rules.append(f'{_class_selector(utility)}:hover{{color:var(--portal-primary)!important}}')
    for utility in ("group-hover:text-brand-400", "group-hover:text-brand-300", "group-hover:text-purple-300"):
        rules.append(f'{_class_selector("group")}:hover {_class_selector(utility)}{{color:var(--portal-primary)!important}}')
    for utility in ("border-indigo-500", "border-indigo-600", "border-purple-500", "border-brand-500", "ring-brand-500", "ring-purple-500", "focus:ring-brand-500", "focus:ring-indigo-500"):
        if utility.startswith(("ring-", "focus:")):
            rules.append(f"{_class_selector(utility)}{{--tw-ring-color:var(--portal-primary)!important}}")
        else:
            rules.append(f"{_class_selector(utility)}{{border-color:var(--portal-primary)!important}}")
    # Dedicated portal gradient utilities without stomping on Tailwind's from-*/to-* stops
    rules.append(
        '.bg-gradient-portal{background-image:linear-gradient(to right,var(--portal-primary),var(--portal-accent))!important}'
    )
    for utility in ("shadow-brand-500/10", "shadow-brand-500/20", "shadow-brand-500/25", "shadow-purple-500/20", "shadow-purple-500/25"):
        rules.append(f"{_class_selector(utility)}{{--tw-shadow-color:var(--portal-primary)!important}}")
    for family in ("brand", "indigo", "purple"):
        for opacity in (20, 30):
            rules.append(
                f'{_class_selector(f"border-{family}-500/{opacity}")}{{border-color:color-mix(in srgb,var(--portal-primary) {opacity}%,transparent)!important}}'
            )

    semantic_families = {
        "success": ("green", "emerald"),
        "warning": ("yellow", "amber", "orange"),
        "error": ("red", "rose"),
        "info": ("blue", "sky", "cyan"),
    }
    for token, families in semantic_families.items():
        for family in families:
            for shade in ("300", "400", "500", "600", "700"):
                rules.append(f'{_class_selector(f"text-{family}-{shade}")}{{color:var(--portal-{token})!important}}')
                rules.append(f'{_class_selector(f"border-{family}-{shade}")}{{border-color:var(--portal-{token})!important}}')
                rules.append(f'{_class_selector(f"hover:text-{family}-{shade}")}:hover{{color:var(--portal-{token})!important}}')
            for shade in ("300", "400", "500", "600", "700", "800", "900"):
                rules.append(f'{_class_selector(f"bg-{family}-{shade}")}{{background-color:var(--portal-{token})!important}}')
            for color_shade in ("300", "400", "500", "600", "700", "800", "900"):
                for opacity in opacity_values:
                    rules.append(
                        f'{_class_selector(f"bg-{family}-{color_shade}/{opacity}")}{{background-color:color-mix(in srgb,var(--portal-{token}) {opacity}%,transparent)!important}}'
                    )
            for shade in ("20", "30"):
                rules.append(
                    f'{_class_selector(f"border-{family}-500/{shade}")}{{border-color:color-mix(in srgb,var(--portal-{token}) {shade}%,transparent)!important}}'
                )

    return "\n".join(rules)
