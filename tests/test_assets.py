"""Tests for local visual identity assets and safe asset loading."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from config import settings
from src.assets import (
    CSS_PATH,
    HERO_SVG_PATH,
    LOGO_SVG_PATH,
    load_css_asset,
    load_hero_svg,
    load_logo_svg,
)
from src.ui_components import load_css


def _svg_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_svg_has_title(path: Path) -> None:
    root = ET.parse(path).getroot()
    titles = root.findall(".//{*}title")
    assert titles
    assert any((title.text or "").strip() for title in titles)


def _assert_svg_has_no_external_reference(path: Path) -> None:
    text = _svg_text(path).lower().replace("http://www.w3.org/2000/svg", "")
    forbidden_fragments = ("https://", "http://", "href=", "url(")
    assert not any(fragment in text for fragment in forbidden_fragments)


def test_svg_files_exist_and_parse_as_xml() -> None:
    for path in (LOGO_SVG_PATH, HERO_SVG_PATH):
        assert path.exists()
        assert path.suffix == ".svg"
        assert ET.parse(path).getroot().tag.endswith("svg")


def test_svg_assets_have_titles_and_no_external_urls() -> None:
    for path in (LOGO_SVG_PATH, HERO_SVG_PATH):
        _assert_svg_has_title(path)
        _assert_svg_has_no_external_reference(path)


def test_css_file_exists_and_loads() -> None:
    assert CSS_PATH.exists()
    assert ".fpt-hero" in load_css_asset(CSS_PATH)


def test_asset_paths_use_pathlib() -> None:
    assert isinstance(LOGO_SVG_PATH, Path)
    assert isinstance(HERO_SVG_PATH, Path)
    assert isinstance(CSS_PATH, Path)
    assert LOGO_SVG_PATH.parent == settings.BASE_DIR / "assets"


def test_logo_and_hero_loading_return_svg() -> None:
    logo = load_logo_svg()
    hero = load_hero_svg()

    assert "<svg" in logo
    assert "<title" in logo
    assert "<svg" in hero
    assert "<title" in hero


def test_missing_svg_assets_use_inline_fallback(tmp_path: Path) -> None:
    missing_logo = tmp_path / "missing_logo.svg"
    missing_hero = tmp_path / "missing_hero.svg"

    assert "fallback-logo-title" in load_logo_svg(missing_logo)
    assert "fallback-hero-title" in load_hero_svg(missing_hero)


def test_missing_css_does_not_break_app_loading(tmp_path: Path) -> None:
    missing_css = tmp_path / "missing.css"

    assert load_css_asset(missing_css) == ""
    assert load_css(missing_css) == ""


def test_app_does_not_hardcode_absolute_paths() -> None:
    app_source = (settings.BASE_DIR / "app.py").read_text(encoding="utf-8")

    assert "C:\\" not in app_source
    assert "C:/" not in app_source
    assert "/Users/" not in app_source


def test_streamlit_theme_config_matches_local_identity() -> None:
    config_path = settings.BASE_DIR / ".streamlit" / "config.toml"
    config_text = config_path.read_text(encoding="utf-8")

    assert 'base = "light"' in config_text
    assert 'primaryColor = "#1f5f8b"' in config_text
    assert "gatherUsageStats = false" in config_text
