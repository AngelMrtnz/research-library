"""LaTeX in titles: kept as-is in BibTeX, shown as Unicode, flattened for filenames.

Titles are stored the way they go into BibTeX: Unicode letters (``León``) plus
LaTeX for math and symbols (``$\\mathbb{R}^n$``).
"""

from __future__ import annotations

import re

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ",
    "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ",
    "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = {
    "times": "×", "otimes": "⊗", "oplus": "⊕", "wedge": "∧", "infty": "∞",
    "partial": "∂", "nabla": "∇", "to": "→", "rightarrow": "→", "mapsto": "↦",
    "leq": "≤", "geq": "≥", "neq": "≠", "cdot": "·", "circ": "∘", "in": "∈",
    "subset": "⊂", "ltimes": "⋉", "rtimes": "⋊", "ell": "ℓ", "hbar": "ℏ",
    "sim": "∼", "simeq": "≃", "cong": "≅", "pm": "±", "star": "⋆",
}
# Symbols whose name keeps the meaning in a filename: $L_\infty$ -> L-infinity.
WORDS = {"infty": "infinity", "partial": "partial", "nabla": "nabla", "hbar": "hbar",
         "ell": "ell"}
BB = {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}
SUP = dict(zip("0123456789+-=()nijkmrst*", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱʲᵏᵐʳˢᵗ*", strict=True))
SUB = dict(zip("0123456789+-=()aeijkmnoprstux", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢⱼₖₘₙₒₚᵣₛₜᵤₓ", strict=True))

_CMD = re.compile(r"\\([A-Za-z]+)\s*")
_FONT = re.compile(r"\\(mathbb|mathfrak|mathcal|mathrm|mathbf|mathit|mathsf|text|textrm|"
                   r"textit|textbf|emph|operatorname)\s*\{([^{}]*)\}")
_SCRIPT = re.compile(r"([\^_])(\{([^{}]*)\}|\\?[A-Za-z0-9*+\-])")
_ESCAPE = re.compile(r"(?<!\\)([&%#])")


def _script(m: re.Match) -> str:
    body = m.group(3) if m.group(3) is not None else m.group(2)
    table = SUP if m.group(1) == "^" else SUB
    if body and all(c in table for c in body):
        return "".join(table[c] for c in body)
    return m.group(1) + body


def _font(m: re.Match) -> str:
    kind, body = m.groups()
    if kind == "mathbb":
        return "".join(BB.get(c, c) for c in body)
    return body


def to_unicode(text: str) -> str:
    """``$\\mathbb{R}^n$`` -> ``ℝⁿ``, for display. Unknown commands lose the backslash."""
    text = text.replace("---", "—").replace("--", "–")
    if "\\" not in text and "$" not in text:
        return text
    out = _FONT.sub(_font, text)
    out = _CMD.sub(lambda m: GREEK.get(m[1]) or SYMBOLS.get(m[1]) or m[1], out)
    out = _SCRIPT.sub(_script, out)
    out = re.sub(r"\\([&%#$_{}])", r"\1", out)
    return out.replace("$", "").replace("{", "").replace("}", "")


def to_plain(text: str) -> str:
    """Filename form: ``$\\mathfrak{g}$-x`` -> ``g-x``, ``$\\alpha$`` -> ``alpha``."""
    if "\\" not in text and "$" not in text:
        return text
    out = _FONT.sub(lambda m: m.group(2), text)
    out = _CMD.sub(lambda m: m.group(1) if m.group(1) in GREEK
                   else "\0" + WORDS[m.group(1)] if m.group(1) in WORDS else "", out)
    out = re.sub(r"[\^_]\{?\0", "-", out).replace("\0", "")  # L_\infty -> L-infinity
    out = re.sub(r"\\([&%#$_{}])", r"\1", out)
    out = re.sub(r"[\^_]", "", out)
    return out.replace("$", "").replace("{", "").replace("}", "")


# Capitalized words that start compounds rather than name a person ("Non-Abelian").
PREFIXES = {"non", "anti", "semi", "quasi", "pre", "post", "multi", "co", "bi", "sub",
            "super", "pseudo", "self", "higher", "well", "left", "right", "first", "second",
            "third", "time", "gauge", "half", "all", "one", "two", "three", "low", "high"}
_PAIR = re.compile(r"([^\W\d_]+)(?:--|-|–|—)(?=([^\W\d_]+))")


def _is_name(word: str) -> bool:
    return word[0].isupper() and any(c.islower() for c in word[1:])


def name_dashes(text: str) -> str:
    """``Hamilton-Jacobi`` / ``Hamilton–Jacobi`` -> ``Hamilton--Jacobi`` (LaTeX en dash).

    Only between two capitalized words, outside math; ``Non-Abelian`` stays as is.
    """
    def fix(m: re.Match) -> str:
        first, second = m.groups()
        if _is_name(first) and _is_name(second) and first.lower() not in PREFIXES:
            return first + "--"
        return m.group(0)

    parts = re.split(r"(\$[^$]*\$)", text)
    return "".join(p if p.startswith("$") else _PAIR.sub(fix, p) for p in parts)


def escape(text: str) -> str:
    """Escape ``& % #`` outside math so BibTeX/LaTeX compiles; leave LaTeX alone."""
    parts = re.split(r"(\$[^$]*\$)", text)
    return "".join(p if p.startswith("$") else _ESCAPE.sub(r"\\\1", p) for p in parts)
