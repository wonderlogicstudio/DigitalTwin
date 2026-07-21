"""Safe local asset loading for the Streamlit presentation UI."""

from __future__ import annotations

from pathlib import Path

from config import settings


ASSETS_DIR = settings.BASE_DIR / "assets"
LOGO_SVG_PATH = ASSETS_DIR / "financial_path_twin_logo.svg"
HERO_SVG_PATH = ASSETS_DIR / "financial_path_twin_hero.svg"
CSS_PATH = ASSETS_DIR / "styles.css"


FALLBACK_LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" aria-labelledby="fallback-logo-title fallback-logo-desc">
  <title id="fallback-logo-title">Branching path mark</title>
  <desc id="fallback-logo-desc">A simple local fallback mark showing one financial path splitting into two outcomes.</desc>
  <circle cx="48" cy="48" r="42" fill="#f8fafc" stroke="#cbd5e1" stroke-width="4"/>
  <path d="M22 58 C36 58 42 48 50 48 C61 48 66 35 76 32" fill="none" stroke="#1f5f8b" stroke-width="7" stroke-linecap="round"/>
  <path d="M50 48 C61 48 67 61 77 65" fill="none" stroke="#d95f02" stroke-width="7" stroke-linecap="round"/>
  <circle cx="50" cy="48" r="7" fill="#ffffff" stroke="#1f5f8b" stroke-width="4"/>
</svg>"""


FALLBACK_HERO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 300" role="img" aria-labelledby="fallback-hero-title fallback-hero-desc">
  <title id="fallback-hero-title">Financial path fallback illustration</title>
  <desc id="fallback-hero-desc">A quiet fallback illustration of one current financial path splitting into stable and risky future paths.</desc>
  <rect width="960" height="300" rx="24" fill="#f8fafc"/>
  <path d="M80 168 C210 168 290 150 395 150" fill="none" stroke="#1f5f8b" stroke-width="8" stroke-linecap="round"/>
  <path d="M395 150 C520 130 635 82 820 78" fill="none" stroke="#1b9e77" stroke-width="7" stroke-linecap="round"/>
  <path d="M395 150 C535 158 640 148 820 142" fill="none" stroke="#4daf4a" stroke-width="7" stroke-linecap="round" stroke-dasharray="14 14"/>
  <path d="M395 150 C520 184 650 218 820 232" fill="none" stroke="#d95f02" stroke-width="7" stroke-linecap="round" stroke-dasharray="4 16"/>
  <circle cx="395" cy="150" r="13" fill="#ffffff" stroke="#d95f02" stroke-width="5"/>
</svg>"""


def read_text_asset(path: Path) -> str:
    """Read a UTF-8 text asset and return an empty string if unavailable."""

    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_svg_asset(path: Path, fallback_svg: str) -> str:
    """Load a local SVG asset, falling back to an inline safe SVG."""

    content = read_text_asset(path)
    if content.strip():
        return content
    return fallback_svg


def load_logo_svg(path: Path = LOGO_SVG_PATH) -> str:
    """Load the Financial Path Twin logo SVG."""

    return load_svg_asset(path, FALLBACK_LOGO_SVG)


def load_hero_svg(path: Path = HERO_SVG_PATH) -> str:
    """Load the Financial Path Twin hero SVG."""

    return load_svg_asset(path, FALLBACK_HERO_SVG)


def load_css_asset(path: Path = CSS_PATH) -> str:
    """Load the app CSS without making UI startup depend on the file."""

    return read_text_asset(path)
