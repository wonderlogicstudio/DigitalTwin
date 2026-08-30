"""Shared visual design tokens for the Streamlit UI."""

from __future__ import annotations

from src.labels import STATUS_COLORS


DESIGN_TOKENS = {
    # Original Financial Path Twin banking palette.  It intentionally uses
    # broadly familiar financial-service blue/teal cues without borrowing a
    # bank's logo, wordmark, or proprietary visual assets.
    "background": "#f4f7fb",
    "page_background": "#f4f7fb",
    "card": "#ffffff",
    "card_background": "#ffffff",
    "primary": "#005eb8",
    "primary_dark": "#003b70",
    "accent": "#008a78",
    "text": "#102a43",
    "muted_text": "#526476",
    "border": "#d5dfea",
    "stable": STATUS_COLORS["healthy"],
    "recovered": STATUS_COLORS["recovered"],
    "watch": STATUS_COLORS["watch"],
    "stress": STATUS_COLORS["stress"],
    "delinquent": STATUS_COLORS["delinquent"],
    "baseline": "#6b7c93",
    "current_customer": "#005eb8",
    "future_band": "#eaf4ff",
    "breakpoint": "#c43d3d",
    "card_radius": "6px",
    "section_gap": "20px",
    "card_padding": "16px",
    # Keep the product offline-safe: preferred locally installed fonts first,
    # followed by dependable Korean Windows/system fallbacks.
    "font_family": 'Inter, "Pretendard Variable", Pretendard, "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", Arial, sans-serif',
}
