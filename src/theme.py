"""Shared visual design tokens for the Streamlit UI."""

from __future__ import annotations

from src.labels import STATUS_COLORS


DESIGN_TOKENS = {
    "background": "#f5f7fa",
    "page_background": "#f5f7fa",
    "card": "#ffffff",
    "card_background": "#ffffff",
    "primary": "#1f5f8b",
    "primary_dark": "#183f63",
    "text": "#172033",
    "muted_text": "#5d6b7c",
    "border": "#d6dee8",
    "stable": STATUS_COLORS["healthy"],
    "recovered": STATUS_COLORS["recovered"],
    "watch": STATUS_COLORS["watch"],
    "stress": STATUS_COLORS["stress"],
    "delinquent": STATUS_COLORS["delinquent"],
    "baseline": "#667085",
    "current_customer": "#1f5f8b",
    "future_band": "#eef6ff",
    "breakpoint": "#d95f02",
    "card_radius": "8px",
    "section_gap": "18px",
    "card_padding": "15px",
    "font_family": 'Pretendard, "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif',
}
