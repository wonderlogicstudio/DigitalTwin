"""Create a screen-based Korean operating manual for Financial Path Twin.

The generator is deliberately offline.  It starts a local Streamlit process only
for a bounded screenshot capture, stops that process in ``finally``, and never
changes canonical analytics, workflow, or source artifacts.

Usage
-----
    python scripts\\generate_operating_manual.py

Outputs are written below ``reports/operating_manual``:

* ``Financial_Path_Twin_운영_사용자_매뉴얼.docx``
* ``Financial_Path_Twin_운영_요약.xlsx``
* reusable PNG diagrams and current UI screenshots
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.drawing.image import Image as SpreadsheetImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image, ImageColor, ImageDraw, ImageFont
import websocket


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "reports" / "operating_manual"
ASSET_DIR = OUTPUT_DIR / "assets"
SCREEN_DIR = OUTPUT_DIR / "screens"

MANUAL_NAME = "Financial_Path_Twin_운영_사용자_매뉴얼.docx"
WORKBOOK_NAME = "Financial_Path_Twin_운영_요약.xlsx"

APP_MODE_GENERAL = "일반 모드"
APP_MODE_PRESENTATION = "발표 모드"
APP_MODE_RM = "RM 업무 모드"

NAVY = "17324D"
BLUE = "1F6FEB"
TEAL = "0F9D8A"
GOLD = "C68A00"
RED = "C23B4A"
LIGHT = "F4F8FC"
GRAY = "5D6B78"
LINE = "D8E1EA"


# Pillow accepts ``#RRGGBB`` whereas openpyxl expects ``RRGGBB``.  Keeping the
# shared palette in the latter form makes the workbook code straightforward;
# this small script-local adapter lets the drawing code accept the same values.
_PIL_GETRGB = ImageColor.getrgb


def _manual_getrgb(color: str | tuple[int, int, int]) -> tuple[int, int, int] | tuple[int, int, int, int]:
    if isinstance(color, str) and re.fullmatch(r"[0-9A-Fa-f]{6}", color):
        color = f"#{color}"
    return _PIL_GETRGB(color)


ImageColor.getrgb = _manual_getrgb  # type: ignore[assignment]


def project_git_reference() -> tuple[str, bool]:
    """Return the checked-out commit and whether the local tree is dirty."""

    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--short"],
                cwd=PROJECT_ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return head, dirty
    except (OSError, subprocess.CalledProcessError):
        return "확인 불가", True


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a Korean-capable Windows font, with a portable fallback."""

    candidates = (
        Path("C:/Windows/Fonts/malgunbd.ttf") if bold else Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/NanumGothicBold.ttf") if bold else Path("C:/Windows/Fonts/NanumGothic.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _wrapped_lines(text: str, max_chars: int) -> str:
    """Wrap readable Korean/English labels without hyphenating identifiers."""

    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=max_chars, break_long_words=False) or [""])
    return "\n".join(lines)


def _rounded_box(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    *,
    title: str,
    body: str,
    accent: str,
    title_size: int = 28,
    body_size: int = 19,
) -> None:
    x0, y0, x1, y1 = bounds
    draw.rounded_rectangle(bounds, radius=28, fill="FFFFFF", outline=LINE, width=2)
    draw.rounded_rectangle((x0, y0, x0 + 12, y1), radius=6, fill=accent)
    draw.text((x0 + 30, y0 + 22), title, fill=NAVY, font=_font(title_size, bold=True))
    draw.multiline_text(
        (x0 + 30, y0 + 70),
        _wrapped_lines(body, 26),
        fill=GRAY,
        font=_font(body_size),
        spacing=8,
    )


def _arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], *, color: str = BLUE) -> None:
    draw.line((start, end), fill=color, width=5)
    x, y = end
    draw.polygon([(x, y), (x - 18, y - 10), (x - 18, y + 10)], fill=color)


def create_mode_overview(path: Path) -> None:
    """Draw the three-mode map as a real PNG, not an ASCII diagram."""

    image = Image.new("RGB", (1800, 950), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1800, 145), fill=NAVY)
    draw.text((70, 42), "Financial Path Twin — 화면 모드 안내", fill="FFFFFF", font=_font(42, bold=True))
    draw.text(
        (72, 103),
        "같은 분석 기반을 목적별 화면으로 분리합니다. 계산 규칙은 화면에서 바꾸지 않습니다.",
        fill="DCEBFA",
        font=_font(20),
    )

    cards = (
        (
            (80, 235, 590, 655),
            "일반 모드",
            "분석을 자세히 확인하는 화면\n고객·지표를 바꾸며 현재 상태,\n유사 경로, landmark, What-if를\n세로 흐름으로 검토합니다.",
            TEAL,
        ),
        (
            (645, 235, 1155, 655),
            "발표 모드",
            "심사·발표용 5단계 스토리\n현재 상태 → 유사 경로 →\n과거 landmark → 대응 시나리오 →\n분석 요약을 같은 고객으로 보여줍니다.",
            BLUE,
        ),
        (
            (1210, 235, 1720, 655),
            "RM 업무 모드",
            "5,000명 전체를 먼저 보는 업무 화면\nPortfolio → Review Queue →\nCustomer Review → Activity/Audit.\n선정과 실제 업무량은 분리해 봅니다.",
            GOLD,
        ),
    )
    for bounds, title, body, color in cards:
        _rounded_box(draw, bounds, title=title, body=body, accent=color, title_size=34, body_size=23)

    draw.rounded_rectangle((235, 735, 1565, 860), radius=22, fill=LIGHT, outline=LINE, width=2)
    draw.text((285, 768), "공통 원칙", fill=NAVY, font=_font(26, bold=True))
    draw.multiline_text(
        (505, 752),
        "• 모든 화면은 합성 데이터 PoC입니다.\n• historical outcome share는 prediction probability가 아닙니다.\n• historical landmark는 현재 고객의 미래 예정일이 아닙니다.",
        fill=GRAY,
        font=_font(19),
        spacing=6,
    )
    image.save(path)


def create_operation_flow(path: Path) -> None:
    """Draw the analytical-to-RM boundary as a readable PNG."""

    image = Image.new("RGB", (1900, 1040), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 145), fill=NAVY)
    draw.text((65, 40), "분석에서 RM 검토까지 — 무엇이 자동이고 무엇이 사람의 판단인가", fill="FFFFFF", font=_font(39, bold=True))
    draw.text((67, 102), "합성 데이터 기반 P0 / Post-P0 준비 상태", fill="DCEBFA", font=_font(20))

    stages = (
        ("5,000명 합성 population", "관측 1–12개월 기준\n경로 특징과 유사 고객 분석", TEAL),
        ("정책 적격성", "prospective signal +\nversioned demo policy", BLUE),
        ("Triage·선정", "투명한 저장 순위와\n사람 입력 capacity 비교", GOLD),
        ("Alert / Case", "선정 또는 기존 case route만\nidempotent file workflow", RED),
        ("RM 후속조치·감사", "권장 후속조치 + 사람 기록\nappend-only audit", "7A5AF8"),
    )
    x_positions = (50, 410, 770, 1130, 1490)
    for index, (title, body, color) in enumerate(stages):
        x0 = x_positions[index]
        _rounded_box(draw, (x0, 290, x0 + 315, 610), title=title, body=body, accent=color, title_size=25, body_size=18)
        if index < len(stages) - 1:
            _arrow(draw, (x0 + 315, 450), (x_positions[index + 1] - 22, 450))

    draw.rounded_rectangle((50, 710, 890, 940), radius=26, fill="FFF8E9", outline="F0CF80", width=2)
    draw.text((85, 748), "시스템이 하지 않는 일", fill="815B00", font=_font(29, bold=True))
    draw.multiline_text(
        (85, 805),
        "• 적정 업무량/threshold를 자동 승인하지 않음\n• 고객 금융결정(승인·거절·상품판매)을 자동 실행하지 않음\n• 실제 외부 알림을 발송하지 않음 (Preview/Null만 제공)",
        fill="705C30",
        font=_font(20),
        spacing=8,
    )
    draw.rounded_rectangle((1010, 710, 1850, 940), radius=26, fill="EEF8F6", outline="9AD6CB", width=2)
    draw.text((1045, 748), "발표에서 분명히 말할 것", fill="0B6658", font=_font(29, bold=True))
    draw.multiline_text(
        (1045, 805),
        "• 1,522명은 unbounded demo 후보/선정 기준이며 일일 RM 업무량이 아님\n• capacity 값은 사람이 넣어 비교하는 draft scenario임\n• real anonymized data 검증은 governance·adapter·metric 준비만 됐고 미실행 상태임",
        fill="355D56",
        font=_font(19),
        spacing=8,
    )
    image.save(path)


def create_presentation_storyboard(path: Path) -> None:
    """Draw the recommended app-first demo sequence as a PNG."""

    image = Image.new("RGB", (1900, 1100), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 145), fill=NAVY)
    draw.text((65, 40), "권장 시연 흐름 — 앱 중심 2분", fill="FFFFFF", font=_font(42, bold=True))
    draw.text((67, 104), "60% 제품 흐름 · 25% 방법론/검증 · 15% 한계와 다음 검증", fill="DCEBFA", font=_font(21))

    sequence = (
        ("0:00–0:20", "RM Portfolio", "5,000 → 1,522\n→ Monitor 371\n→ No actionable 3,107", TEAL),
        ("0:20–0:40", "Human Capacity", "예: 3 입력\n3 selected / 1,519 deferred\n자동 권고 아님", GOLD),
        ("0:40–1:10", "Customer Review", "C000001\n왜 선정되었나 / 왜 지금인가\nprospective vs historical 분리", BLUE),
        ("1:10–1:30", "다중 고객 비교", "C000007 Review\nC000003 Monitor 비교\n대표 사례는 queue가 아님", "7A5AF8"),
        ("1:30–2:00", "Presentation 5 tabs", "C002608\nDigital Twin 분석 story\nlandmark는 과거 cohort 근거", RED),
    )
    x_positions = (45, 410, 775, 1140, 1505)
    for index, (time_label, title, body, color) in enumerate(sequence):
        x = x_positions[index]
        draw.rounded_rectangle((x, 245, x + 330, 740), radius=30, fill="FFFFFF", outline=LINE, width=2)
        draw.rounded_rectangle((x, 245, x + 330, 313), radius=30, fill=color)
        draw.text((x + 28, 266), time_label, fill="FFFFFF", font=_font(24, bold=True))
        draw.text((x + 28, 350), title, fill=NAVY, font=_font(27, bold=True))
        draw.multiline_text((x + 28, 415), _wrapped_lines(body, 17), fill=GRAY, font=_font(20), spacing=10)
        if index < len(sequence) - 1:
            _arrow(draw, (x + 330, 495), (x_positions[index + 1] - 15, 495), color="9CB7D1")

    draw.rounded_rectangle((120, 835, 1780, 990), radius=22, fill=LIGHT, outline=LINE, width=2)
    draw.text((165, 875), "보조 화면", fill=NAVY, font=_font(25, bold=True))
    draw.multiline_text(
        (370, 856),
        "C002082: 안정/근거 부족을 정직하게 보여주는 대비 사례 · C002672: 시각적 고위험 대비용(운영 선정 근거로 사용 금지)\nAction/Audit: 현재 기본 앱에는 case fixture가 없으므로, 격리된 synthetic dry-run 증거로만 제시하거나 별도 fixture 단계 후 시연",
        fill=GRAY,
        font=_font(19),
        spacing=8,
    )
    image.save(path)


def create_evidence_status_matrix(path: Path) -> None:
    """Visualise the boundary between demonstrated, conditional, and open work."""

    image = Image.new("RGB", (1900, 1160), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 145), fill=NAVY)
    draw.text((65, 40), "현재 무엇이 증명되었고, 무엇이 남아 있는가", fill="FFFFFF", font=_font(42, bold=True))
    draw.text(
        (67, 103),
        "발표에서는 세 영역을 섞지 않습니다. 합성 PoC의 증거, 사람의 운영 판단, 실제 검증의 미완료를 분리합니다.",
        fill="DCEBFA",
        font=_font(20),
    )
    columns = (
        (
            (55, 230, 610, 845),
            "현재 증명된 기능",
            "합성 PoC / 앱에서 재현 가능",
            "• 5,000명 전수 분석·정확한 reconciliation\n• deterministic triage와 다중 고객 비교\n• 선정 이유·Why Now·과거 landmark 분리\n• selected→Case→Audit prototype\n• leakage/circularity regression checks",
            TEAL,
            "발표 표현: ‘합성 데이터 PoC에서 확인했습니다.’",
        ),
        (
            (672, 230, 1227, 845),
            "사람의 승인·운영 판단 필요",
            "시스템이 자동 결정하지 않음",
            "• 1,522명은 unbounded 참조값\n• capacity 입력은 Selected/Deferred 비교\n• 적정 업무량·정책 승인 권한은 사람에게 있음\n• RM의 실제 후속 행동은 담당자가 기록\n• 파일럿 운영 여부는 조직이 결정",
            GOLD,
            "발표 표현: ‘비교 도구이며 자동 권고가 아닙니다.’",
        ),
        (
            (1289, 230, 1844, 845),
            "아직 검증되지 않음 / 범위 밖",
            "정직하게 open으로 유지",
            "• 실제 익명화 고객 데이터 검증\n• 실제 RM 성과·개입 효과\n• 외부 메시지 전송 및 SLA\n• DB/운영 시스템 연동\n• 자동 승인·거절·상품 제안",
            RED,
            "발표 표현: ‘준비 계약은 있으나 검증 완료가 아닙니다.’",
        ),
    )
    for bounds, title, subtitle, body, color, footer in columns:
        x0, y0, x1, y1 = bounds
        draw.rounded_rectangle(bounds, radius=28, fill="FFFFFF", outline=LINE, width=2)
        draw.rounded_rectangle((x0, y0, x1, y0 + 105), radius=28, fill=color)
        draw.text((x0 + 28, y0 + 26), title, fill="FFFFFF", font=_font(29, bold=True))
        draw.text((x0 + 30, y0 + 138), subtitle, fill=NAVY, font=_font(20, bold=True))
        draw.multiline_text((x0 + 30, y0 + 195), body, fill=GRAY, font=_font(20), spacing=14)
        draw.rounded_rectangle((x0 + 25, y1 - 115, x1 - 25, y1 - 28), radius=16, fill=LIGHT)
        draw.multiline_text((x0 + 43, y1 - 95), _wrapped_lines(footer, 28), fill=NAVY, font=_font(17, bold=True), spacing=4)
    draw.rounded_rectangle((135, 940, 1765, 1080), radius=24, fill="EAF2FB", outline="B7CEE5", width=2)
    draw.text((180, 978), "현재 공식 상태", fill=NAVY, font=_font(26, bold=True))
    draw.multiline_text(
        (445, 960),
        "READY_WITH_OPEN_REAL_DATA_VALIDATION\n합성 기반 방법론·전수 triage·RM 프로토타입은 보여주되, 실제 고객 성과나 실제 전달 체계로 과장하지 않습니다.",
        fill="355D56",
        font=_font(20),
        spacing=7,
    )
    image.save(path)


def create_rm_preparation_flow(path: Path) -> None:
    """Show what a team must prepare before an RM uses the workspace."""

    image = Image.new("RGB", (1900, 1180), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 145), fill=NAVY)
    draw.text((65, 40), "RM 업무 모드 전에 준비할 일", fill="FFFFFF", font=_font(42, bold=True))
    draw.text(
        (67, 103),
        "이 흐름은 업무량을 자동 승인하거나 고객에게 자동 행동하는 과정이 아닙니다. 준비·검토·기록의 책임을 구분합니다.",
        fill="DCEBFA",
        font=_font(19),
    )
    stages = (
        ("1", "분석 입력 준비", "01 설치 → 02 pipeline\nseed=42 canonical 5,000", TEAL, "Demo operator"),
        ("2", "품질 확인", "pytest / readiness\n5,000 reconciliation", BLUE, "Demo operator"),
        ("3", "근거·정책 확인", "policy/version/provenance\nWhy Now와 landmark 분리", "7A5AF8", "Policy owner"),
        ("4", "사람 입력 capacity", "비교값을 입력해\nSelected/Deferred를 검토", GOLD, "Human approver"),
        ("5", "Triage 결과 확인", "selected/routed만 queue\nMonitor/NoSignal은 제외", "B16B30", "Demo operator"),
        ("6", "RM 검토·기록", "근거 확인 → follow-up\nstate/action/audit 기록", RED, "RM"),
    )
    start_x, card_w, gap = 55, 272, 37
    for index, (number, title, body, color, owner) in enumerate(stages):
        x0 = start_x + index * (card_w + gap)
        y0 = 270
        draw.rounded_rectangle((x0, y0, x0 + card_w, y0 + 460), radius=27, fill="FFFFFF", outline=LINE, width=2)
        draw.ellipse((x0 + 24, y0 + 27, x0 + 92, y0 + 95), fill=color)
        draw.text((x0 + 47, y0 + 42), number, fill="FFFFFF", font=_font(28, bold=True))
        draw.multiline_text((x0 + 24, y0 + 130), _wrapped_lines(title, 14), fill=NAVY, font=_font(25, bold=True), spacing=6)
        draw.multiline_text((x0 + 24, y0 + 240), body, fill=GRAY, font=_font(19), spacing=10)
        draw.rounded_rectangle((x0 + 20, y0 + 380, x0 + card_w - 20, y0 + 430), radius=14, fill=LIGHT)
        draw.text((x0 + 38, y0 + 396), owner, fill=NAVY, font=_font(17, bold=True))
        if index < len(stages) - 1:
            _arrow(draw, (x0 + card_w, y0 + 230), (x0 + card_w + gap - 10, y0 + 230), color="9CB7D1")
    draw.rounded_rectangle((55, 810, 910, 1100), radius=26, fill="EEF8F6", outline="9AD6CB", width=2)
    draw.text((92, 850), "데모·합성 환경에서 바로 할 수 있는 일", fill="0B6658", font=_font(27, bold=True))
    draw.multiline_text(
        (92, 910),
        "• RM Portfolio에서 5,000명 funnel을 확인\n• C000001 / C000007 / C000003을 대표·비교 사례로 열기\n• capacity=3 같은 사람 입력 비교를 실행\n• selected pending과 open Case 0을 구분해 설명\n• 격리된 synthetic dry-run 증거를 별도로 제시",
        fill="355D56",
        font=_font(20),
        spacing=11,
    )
    draw.rounded_rectangle((990, 810, 1845, 1100), radius=26, fill="FFF8E9", outline="F0CF80", width=2)
    draw.text((1027, 850), "실제 운영 전에 조직이 결정해야 하는 일", fill="815B00", font=_font(27, bold=True))
    draw.multiline_text(
        (1027, 910),
        "• 승인된 capacity와 policy version\n• 실제 데이터 접근 governance·승인·adapter 검증\n• RM pilot의 대상, 기간, 측정 지표\n• 외부 notification / DB 통합의 별도 승인\n• 자동 금융결정을 하지 않는 운영 경계",
        fill="705C30",
        font=_font(20),
        spacing=11,
    )
    image.save(path)


def create_feedback_response_map(path: Path) -> None:
    """Turn evaluator feedback into a concise, honest demo response map."""

    image = Image.new("RGB", (1900, 1120), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 145), fill=NAVY)
    draw.text((65, 40), "평가 피드백을 앱·발표에서 어떻게 닫을 것인가", fill="FFFFFF", font=_font(41, bold=True))
    draw.text((67, 103), "강점은 실제 화면과 재현성으로 보여주고, 미검증 영역은 roadmap으로만 말합니다.", fill="DCEBFA", font=_font(20))
    rows = (
        (
            "피드백 1  합성 데이터·한 고객 데모",
            "앱에서 보여줄 근거\n5,000→1,522→selected funnel\nC000001 / C000007 / C000003 비교\n대표 cohort·no-cherry-picking provenance",
            "정직한 결론\n전수 synthetic PoC는 완주\n실제 익명화 데이터 검증은 open\nGovernance·adapter·metric 계약만 준비",
            TEAL,
        ),
        (
            "피드백 2  앱을 슬라이드보다 더 보여달라",
            "앱 우선 2분 흐름\nRM Portfolio → capacity → Customer Review\nPresentation 5 tabs로 방법론 연결",
            "정직한 결론\n영상/리허설은 별도 준비물\n현재 앱 화면을 녹화하고, 슬라이드는 근거 보조로만 사용",
            BLUE,
        ),
        (
            "피드백 3  Banker Workflow를 추가하라",
            "Policy → Triage → Alert/Case → RM action → Audit\nPreview only / idempotent / selected-only 경계",
            "정직한 결론\n프로토타입 흐름은 구현\n실제 RM 성과·외부 전달·SLA는 증명하지 않음",
            RED,
        ),
    )
    y_positions = (225, 500, 775)
    for (feedback, evidence, response, color), y0 in zip(rows, y_positions):
        draw.rounded_rectangle((55, y0, 1845, y0 + 205), radius=24, fill="FFFFFF", outline=LINE, width=2)
        draw.rounded_rectangle((55, y0, 470, y0 + 205), radius=24, fill=color)
        draw.multiline_text((85, y0 + 52), _wrapped_lines(feedback, 18), fill="FFFFFF", font=_font(24, bold=True), spacing=8)
        draw.multiline_text((520, y0 + 32), evidence, fill=NAVY, font=_font(19), spacing=9)
        draw.line((1175, y0 + 28, 1175, y0 + 177), fill=LINE, width=2)
        draw.multiline_text((1220, y0 + 32), response, fill=GRAY, font=_font(19), spacing=9)
    draw.rounded_rectangle((250, 1035, 1650, 1095), radius=18, fill="EAF2FB", outline="B7CEE5", width=2)
    draw.text(
        (300, 1054),
        "권장 발표 비중: 실제 앱 화면 60% · 방법론/검증 25% · 합성 한계와 다음 검증 15%", fill=NAVY, font=_font(22, bold=True)
    )
    image.save(path)


def create_capacity_comparison_example(path: Path) -> None:
    """Create an artifact-backed visual for the human-entered capacity example."""

    image = Image.new("RGB", (1900, 900), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 145), fill=NAVY)
    draw.text((65, 40), "용량 비교 예시: 1,522명은 업무량이 아니라 unbounded 참조값", fill="FFFFFF", font=_font(38, bold=True))
    draw.text(
        (67, 103),
        "저장된 투명 순위를 다시 계산하지 않고, 사람이 입력한 cutoff에서 Selected와 Deferred를 비교합니다.",
        fill="DCEBFA",
        font=_font(20),
    )
    cards = (
        (
            (110, 245, 835, 640),
            "Unbounded demo 참조",
            "입력값 없음 · status=demo",
            "1,522명\nSelected",
            "0명\nDeferred",
            BLUE,
        ),
        (
            (1065, 245, 1790, 640),
            "사람 입력 비교",
            "예시 입력: capacity = 3 · status=draft",
            "3명\nSelected",
            "1,519명\nDeferred",
            GOLD,
        ),
    )
    for bounds, title, subtitle, selected, deferred, color in cards:
        x0, y0, x1, y1 = bounds
        draw.rounded_rectangle(bounds, radius=28, fill="FFFFFF", outline=LINE, width=3)
        draw.rounded_rectangle((x0, y0, x1, y0 + 90), radius=28, fill=color)
        draw.text((x0 + 35, y0 + 25), title, fill="FFFFFF", font=_font(29, bold=True))
        draw.text((x0 + 35, y0 + 125), subtitle, fill=NAVY, font=_font(20, bold=True))
        draw.rounded_rectangle((x0 + 40, y0 + 200, x0 + 335, y1 - 45), radius=22, fill="EEF8F6", outline="9AD6CB", width=2)
        draw.rounded_rectangle((x0 + 390, y0 + 200, x1 - 40, y1 - 45), radius=22, fill="FFF8E9", outline="F0CF80", width=2)
        draw.multiline_text((x0 + 75, y0 + 245), selected, fill="0B6658", font=_font(32, bold=True), spacing=7)
        draw.multiline_text((x0 + 430, y0 + 245), deferred, fill="815B00", font=_font(32, bold=True), spacing=7)
    _arrow(draw, (865, 440), (1030, 440), color="9CB7D1")
    draw.rounded_rectangle((175, 720, 1725, 840), radius=22, fill="FFF1F3", outline="E9B6C0", width=2)
    draw.text((225, 752), "중요한 경계", fill=RED, font=_font(25, bold=True))
    draw.multiline_text(
        (445, 735),
        "이 비교는 적정 업무량을 자동으로 추천·승인하지 않습니다. 실제 운영 capacity, SLA, 담당자 배정은 조직의 별도 결정입니다.",
        fill="6C3940",
        font=_font(20),
        spacing=6,
    )
    image.save(path)


def create_default_vs_rehearsal_workflow(path: Path) -> None:
    """Explain why the default RM workspace intentionally contains zero Cases."""

    image = Image.new("RGB", (1900, 1080), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 145), fill=NAVY)
    draw.text((65, 40), "기본 RM 데모와 별도 synthetic workflow rehearsal의 차이", fill="FFFFFF", font=_font(39, bold=True))
    draw.text(
        (67, 103),
        "선정(Triage)과 Alert/Case 생성은 의도적으로 다른 단계입니다. 기본 화면은 읽기 전용이며 자동으로 Case를 만들지 않습니다.",
        fill="DCEBFA",
        font=_font(19),
    )
    panels = (
        (
            (60, 235, 895, 780),
            "A. 현재 기본 RM 화면 · 데모/읽기 전용",
            "5,000명 분석\n↓\n1,522명 triage selected\n↓\n‘선정됨 · Case 미생성’\n↓\n열린 Alert 0 / RM 업무 큐 Case 0",
            "정상 상태: selection evidence는 보이지만 workflow repository에는 기본 fixture가 없습니다. UI와 02_run_pipeline은 Case를 만들지 않습니다.",
            TEAL,
        ),
        (
            (1005, 235, 1840, 780),
            "B. 격리된 synthetic rehearsal · 별도 증거",
            "승인된 합성 TriageDecision 3건\n↓\nAlert cycle / idempotent Case\n↓\n3 synthetic Cases\n↓\n10 Audit events / Preview not sent",
            "별도 output path의 실험 증거입니다. 실제 고객·외부 메시지·DB·SLA·RM 성과가 아니며 기본 앱에 자동으로 합쳐지지 않습니다.",
            GOLD,
        ),
    )
    for bounds, title, body, footer, color in panels:
        x0, y0, x1, y1 = bounds
        draw.rounded_rectangle(bounds, radius=28, fill="FFFFFF", outline=LINE, width=3)
        draw.rounded_rectangle((x0, y0, x1, y0 + 98), radius=28, fill=color)
        draw.text((x0 + 30, y0 + 28), title, fill="FFFFFF", font=_font(27, bold=True))
        draw.multiline_text((x0 + 55, y0 + 145), body, fill=NAVY, font=_font(24, bold=True), spacing=9)
        draw.rounded_rectangle((x0 + 35, y1 - 145, x1 - 35, y1 - 35), radius=18, fill=LIGHT)
        draw.multiline_text((x0 + 58, y1 - 122), _wrapped_lines(footer, 43), fill=GRAY, font=_font(18), spacing=6)
    draw.rounded_rectangle((165, 860, 1735, 1005), radius=24, fill="FFF1F3", outline="E9B6C0", width=2)
    draw.text((210, 900), "중요", fill=RED, font=_font(27, bold=True))
    draw.multiline_text(
        (380, 880),
        "기본 RM 메뉴에서 Alert를 생성하는 숨은 작업은 없습니다. Action/Audit을 보여주기 위해 live 화면에서 Case를 억지로 만들지 말고,\n격리된 synthetic rehearsal 결과를 ‘별도 리허설 증거’로만 제시합니다.",
        fill="6C3940",
        font=_font(20),
        spacing=8,
    )
    image.save(path)


def create_workflow_demo_boundary_diagram(path: Path) -> None:
    """Draw the isolated Workflow Demo write boundary for the operating manual."""

    image = Image.new("RGB", (1900, 1200), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 150), fill=NAVY)
    draw.text(
        (65, 42),
        "Workflow Demo: RM action으로 바뀌는 것과 보호되는 것",
        fill="FFFFFF",
        font=_font(38, bold=True),
    )
    draw.text(
        (67, 104),
        "명시적으로 Demo를 열고 초기화한 뒤에만 별도 synthetic runtime이 바뀝니다. 분석 원본과 기본 RM 화면은 바뀌지 않습니다.",
        fill="DCEBFA",
        font=_font(19),
    )

    left = (65, 230, 900, 920)
    right = (1000, 230, 1835, 920)
    for bounds, title, accent in (
        (left, "A. Demo에서만 변경 가능", TEAL),
        (right, "B. 항상 보호되는 분석/운영 기준", RED),
    ):
        x0, y0, x1, y1 = bounds
        draw.rounded_rectangle(bounds, radius=28, fill="FFFFFF", outline=LINE, width=3)
        draw.rounded_rectangle((x0, y0, x1, y0 + 94), radius=28, fill=accent)
        draw.text((x0 + 34, y0 + 27), title, fill="FFFFFF", font=_font(29, bold=True))

    left_rows = (
        (
            "1. Demo runtime case",
            "artifacts/workflow_demo/runtime/workflow\nalert_cases.json\n\nNEW -> ACKNOWLEDGED -> IN_REVIEW -> FOLLOW_UP/CLOSED\n상태와 RM action 기록만 변경",
            "EEF8F6",
        ),
        (
            "2. Append-only audit",
            "artifacts/workflow_demo/runtime/audit\naudit_events.jsonl\n\n행동, 이전/새 상태, actor, policy/signal reference를 추가 기록",
            "EAF2FB",
        ),
        (
            "3. Demo session/preview",
            "rm_workflow_demo_* session key\n\n선택 Case, 화면 feedback, Preview request만 유지\nPreview는 not sent이며 network 호출이 없음",
            "FFF8E9",
        ),
    )
    for index, (title, body, fill) in enumerate(left_rows):
        y0 = 340 + index * 180
        draw.rounded_rectangle((115, y0, 850, y0 + 160), radius=18, fill=fill, outline=LINE, width=2)
        draw.text((145, y0 + 16), title, fill=NAVY, font=_font(22, bold=True))
        draw.multiline_text((145, y0 + 53), body, fill=GRAY, font=_font(16), spacing=4)

    right_rows = (
        "5,000명 원본/월별 synthetic data와 canonical CSV/JSON",
        "feature, matcher, historical outcome, breakpoint, What-if 계산",
        "policy eligibility, triage ranking, capacity, selection manifest, queue membership",
        "기본 artifacts/workflow 및 artifacts/audit, General/Presentation/RM 기본 상태",
        "외부 메시지, provider, credential, network, 실제 금융 의사결정",
    )
    for index, body in enumerate(right_rows):
        y0 = 330 + index * 112
        draw.rounded_rectangle((1050, y0, 1785, y0 + 92), radius=16, fill="FFF1F3", outline="E9B6C0", width=2)
        draw.text((1080, y0 + 26), f"{index + 1}", fill=RED, font=_font(23, bold=True))
        draw.multiline_text((1130, y0 + 19), _wrapped_lines(body, 42), fill="6C3940", font=_font(17), spacing=4)

    draw.rounded_rectangle((140, 990, 1760, 1140), radius=24, fill="EAF2FB", outline="B7CEE5", width=2)
    draw.text((190, 1028), "발표에서 반드시 말할 경계", fill=NAVY, font=_font(24, bold=True))
    draw.multiline_text(
        (500, 1026),
        "RM action demo는 Case 상태와 audit evidence를 보여줍니다. 고객의 savings/DSR/월별 거래,\n선정 순위, queue 포함 여부, 분석 결과를 다시 계산하거나 바꾸지 않습니다.",
        fill=GRAY,
        font=_font(18),
        spacing=5,
    )
    image.save(path)


def create_workflow_demo_presentation_flow(path: Path) -> None:
    """Draw the app-first internal presentation flow including the Workflow Demo."""

    image = Image.new("RGB", (1900, 1280), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1900, 150), fill=NAVY)
    draw.text((65, 42), "권장 발표 흐름: 5,000명 분석에서 RM action까지", fill="FFFFFF", font=_font(39, bold=True))
    draw.text(
        (67, 104),
        "앱을 먼저 보여주고, Method와 limitation은 근거로만 짧게 연결합니다. 모든 Case와 action은 synthetic demo입니다.",
        fill="DCEBFA",
        font=_font(19),
    )

    stages = (
        ("0", "시작 전", "기본 RM의 Alert 0 / Case 0은 정상\n03_run_app.bat 실행 후 기본 상태 캡처", TEAL),
        ("1", "Portfolio", "5,000 -> 1,522 eligible/selected\nMonitor 371, No actionable 3,107", BLUE),
        ("2", "Capacity", "capacity=3 비교: 3 selected\n1,519 deferred. 적정 인력 자동결정 아님", GOLD),
        ("3", "Customer Review", "C000001: 왜 선정되었나, 왜 지금인가\nprospective timing과 historical landmark 분리", TEAL),
        ("4", "Workflow Demo 열기", "RM 안의 별도 secondary context\nSynthetic / not live / not sent banner 확인", BLUE),
        ("5", "Action + Audit", "정확히 3 Case 초기화\nAcknowledge, Review, Follow-up, Close와 audit 확인", GOLD),
        ("6", "Preview + Return", "Notification Preview는 not sent / network 0\nReset/Back 후 기본 RM이 그대로인지 확인", TEAL),
    )
    positions = (
        (70, 245), (660, 245), (1250, 245),
        (70, 605), (660, 605), (1250, 605),
        (660, 920),
    )
    for (number, title, body, color), (x0, y0) in zip(stages, positions):
        x1, y1 = x0 + 535, y0 + 255
        draw.rounded_rectangle((x0, y0, x1, y1), radius=25, fill="FFFFFF", outline=LINE, width=3)
        draw.ellipse((x0 + 28, y0 + 28, x0 + 97, y0 + 97), fill=color)
        draw.text((x0 + 52, y0 + 40), number, fill="FFFFFF", font=_font(26, bold=True))
        draw.text((x0 + 123, y0 + 37), title, fill=NAVY, font=_font(26, bold=True))
        draw.multiline_text((x0 + 47, y0 + 126), _wrapped_lines(body, 28), fill=GRAY, font=_font(19), spacing=8)

    arrows = (
        ((605, 370), (640, 370)), ((1195, 370), (1230, 370)),
        ((1520, 510), (1520, 570)), ((1240, 730), (1210, 730)),
        ((650, 730), (620, 730)), ((1520, 875), (930, 900)),
    )
    for start, end in arrows:
        _arrow(draw, start, end, color="9CB7D1")

    draw.rounded_rectangle((145, 1165, 1755, 1235), radius=18, fill="FFF1F3", outline="E9B6C0", width=2)
    draw.text(
        (195, 1188),
        "권장 비중: 앱 화면 60% / 방법론·검증 25% / 한계와 다음 검증 15%. 실제 전달, 개입 효과, 실제 은행 성과는 주장하지 않습니다.",
        fill="6C3940",
        font=_font(18, bold=True),
    )
    image.save(path)


def create_capture_card(path: Path, *, mode: str, steps: tuple[str, ...], accent: str) -> None:
    """Create an honest visual placeholder for a user-session screenshot.

    The restricted execution environment cannot safely automate the browser.
    This card deliberately says that it is a capture guide rather than pretending
    to be a live application screen.
    """

    image = Image.new("RGB", (1440, 820), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1440, 120), fill=NAVY)
    draw.text((52, 35), f"{mode} — 화면 캡처 위치", fill="FFFFFF", font=_font(35, bold=True))
    draw.rounded_rectangle((65, 165, 1375, 730), radius=28, fill=LIGHT, outline=LINE, width=2)
    draw.rounded_rectangle((65, 165, 1375, 255), radius=28, fill=accent)
    draw.text((105, 191), "실제 화면을 이 자리에 넣으세요 (자동 캡처가 아닌 사용자 세션 캡처)", fill="FFFFFF", font=_font(23, bold=True))
    draw.rounded_rectangle((115, 315, 410, 645), radius=20, fill="FFFFFF", outline=LINE, width=2)
    draw.text((155, 360), "1", fill=accent, font=_font(64, bold=True))
    draw.text((145, 465), "03_run_app.bat\n실행", fill=NAVY, font=_font(25, bold=True), spacing=8)
    draw.rounded_rectangle((570, 315, 865, 645), radius=20, fill="FFFFFF", outline=LINE, width=2)
    draw.text((610, 360), "2", fill=accent, font=_font(64, bold=True))
    draw.multiline_text((600, 465), _wrapped_lines("1366×768 또는 1920×1080으로 브라우저 창을 고정", 14), fill=NAVY, font=_font(22, bold=True), spacing=8)
    draw.rounded_rectangle((1025, 315, 1320, 645), radius=20, fill="FFFFFF", outline=LINE, width=2)
    draw.text((1065, 360), "3", fill=accent, font=_font(64, bold=True))
    draw.multiline_text((1055, 455), _wrapped_lines("아래 순서로 화면을 연 뒤 Win+Shift+S", 14), fill=NAVY, font=_font(22, bold=True), spacing=8)
    y = 770
    draw.text((75, y), "캡처 순서: " + "  →  ".join(steps), fill=GRAY, font=_font(19))
    image.save(path)


def create_diagrams() -> dict[str, Path]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    diagram_paths = {
        "modes": ASSET_DIR / "01_modes_overview.png",
        "flow": ASSET_DIR / "02_analytics_to_rm_flow.png",
        "storyboard": ASSET_DIR / "03_recommended_demo_storyboard.png",
        "evidence_status": ASSET_DIR / "09_evidence_status_matrix.png",
        "rm_preparation": ASSET_DIR / "10_rm_preparation_workflow.png",
        "feedback_response": ASSET_DIR / "11_evaluator_feedback_response_map.png",
        "capacity_example": ASSET_DIR / "12_capacity_comparison_example.png",
        "default_vs_rehearsal": ASSET_DIR / "14_default_rm_vs_synthetic_rehearsal.png",
        "workflow_demo_boundary": ASSET_DIR / "20_workflow_demo_data_boundary.png",
        "workflow_demo_presentation": ASSET_DIR / "21_workflow_demo_presentation_flow.png",
    }
    create_mode_overview(diagram_paths["modes"])
    create_operation_flow(diagram_paths["flow"])
    create_presentation_storyboard(diagram_paths["storyboard"])
    create_evidence_status_matrix(diagram_paths["evidence_status"])
    create_rm_preparation_flow(diagram_paths["rm_preparation"])
    create_feedback_response_map(diagram_paths["feedback_response"])
    create_capacity_comparison_example(diagram_paths["capacity_example"])
    create_default_vs_rehearsal_workflow(diagram_paths["default_vs_rehearsal"])
    create_workflow_demo_boundary_diagram(diagram_paths["workflow_demo_boundary"])
    create_workflow_demo_presentation_flow(diagram_paths["workflow_demo_presentation"])
    return diagram_paths


def create_capture_cards() -> dict[str, Path]:
    """Make screen-capture instruction cards for the manual's visual sections."""

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    cards = {
        "presentation": ASSET_DIR / "04_capture_presentation.png",
        "general": ASSET_DIR / "05_capture_general.png",
        "rm": ASSET_DIR / "06_capture_rm.png",
    }
    create_capture_card(
        cards["presentation"],
        mode="발표 모드",
        steps=("C002608", "현재 상태", "유사 경로", "Historical Landmark", "What-if", "요약"),
        accent=BLUE,
    )
    create_capture_card(
        cards["general"],
        mode="일반 모드",
        steps=("C002608", "C002082 비교", "필요 시 C002672", "지표 변경"),
        accent=TEAL,
    )
    create_capture_card(
        cards["rm"],
        mode="RM 업무 모드",
        steps=("Portfolio", "Queue", "C000001", "C000007", "C000003 비교"),
        accent=GOLD,
    )
    return cards


def _pin(draw: ImageDraw.ImageDraw, center: tuple[int, int], number: int, *, color: str) -> None:
    x, y = center
    draw.ellipse((x - 34, y - 34, x + 34, y + 34), fill=color, outline="FFFFFF", width=4)
    label = str(number)
    bbox = draw.textbbox((0, 0), label, font=_font(30, bold=True))
    draw.text(
        (x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2 - 3),
        label,
        fill="FFFFFF",
        font=_font(30, bold=True),
    )


def create_general_input_annotation(source: Path, destination: Path) -> Path:
    """Annotate the real General-mode capture with its safe input workflow."""

    screenshot = Image.open(source).convert("RGB")
    crop = screenshot.crop((0, 0, screenshot.width, min(screenshot.height, 1160)))
    overlay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    boxes = (
        ((20, 260, 500, 360), 1, BLUE),
        ((20, 410, 500, 520), 2, TEAL),
        ((20, 600, 500, 720), 3, GOLD),
        ((20, 735, 500, 820), 4, "7A5AF8"),
        ((2010, 40, 2460, 180), 5, RED),
    )
    for bounds, number, color in boxes:
        draw_overlay.rounded_rectangle(bounds, radius=18, outline=f"#{color}", width=7, fill=f"#{color}20")
        _pin(draw_overlay, (bounds[2] - 28, bounds[1] + 28), number, color=f"#{color}")
    annotated_crop = Image.alpha_composite(crop.convert("RGBA"), overlay).convert("RGB")
    canvas = Image.new("RGB", (crop.width, crop.height + 355), "FFFFFF")
    canvas.paste(annotated_crop, (0, 0))
    draw = ImageDraw.Draw(canvas)
    panel_top = crop.height
    draw.rectangle((0, panel_top, canvas.width, canvas.height), fill=NAVY)
    draw.text((55, panel_top + 38), "일반 모드 입력 예시", fill="FFFFFF", font=_font(31, bold=True))
    instructions = (
        "1  화면 모드: 일반 모드 — 상세 분석·Q&A용",
        "2  고객 선택: C002608(메인) / C002082(안정·근거부족 대비) / C002672(고위험 시각 대비)",
        "3  표시 지표: 저축률부터 확인. 필요하면 DSR·고정지출 비중으로 바꿉니다.",
        "4  세부 궤적 표시: 질문이 있을 때만 켭니다. 발표 기본 화면에서는 숨깁니다.",
        "5  언어: 한국어/English 표기만 바뀌며 분석·queue 결과는 다시 계산하지 않습니다.",
    )
    for index, instruction in enumerate(instructions):
        draw.text((65, panel_top + 100 + index * 46), instruction, fill="E6EEF8", font=_font(20))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)
    return destination


def create_rm_alert_case_status_annotation(source: Path, destination: Path) -> Path:
    """Annotate the actual RM Portfolio status without manufacturing a Case."""

    screenshot = Image.open(source).convert("RGB")
    # The operational-status band is the part of the live Portfolio that can
    # otherwise look like a failure: alerts/cases are intentionally zero while
    # selected pending remains 1,522.  Crop it so the explanation stays legible.
    source_top = min(800, max(0, screenshot.height // 2))
    source_bottom = min(screenshot.height, source_top + 760)
    crop = screenshot.crop((0, source_top, screenshot.width, source_bottom))
    overlay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    callouts = (
        ((525, 170, 2320, 360), 1, RED),
        ((525, 390, 1010, 610), 2, TEAL),
        ((1340, 390, 1910, 610), 3, GOLD),
    )
    for bounds, number, color in callouts:
        draw_overlay.rounded_rectangle(bounds, radius=18, outline=f"#{color}", width=7, fill=f"#{color}20")
        _pin(draw_overlay, (bounds[2] - 28, bounds[1] + 28), number, color=f"#{color}")
    annotated = Image.alpha_composite(crop.convert("RGBA"), overlay).convert("RGB")
    canvas = Image.new("RGB", (crop.width, crop.height + 390), "FFFFFF")
    canvas.paste(annotated, (0, 0))
    draw = ImageDraw.Draw(canvas)
    panel_top = crop.height
    draw.rectangle((0, panel_top, canvas.width, canvas.height), fill=NAVY)
    draw.text((55, panel_top + 35), "RM 기본 화면의 Alert / Case 상태를 읽는 법", fill="FFFFFF", font=_font(31, bold=True))
    explanations = (
        "1  열린 Alert 0: 기본 workflow repository에 Case fixture가 없다는 뜻입니다. 오류나 실패가 아닙니다.",
        "2  RM 업무 큐 Case 0: Case를 자동 생성하지 않는 읽기 전용 기본 데모라서 정상입니다.",
        "3  Case 생성 대기 1,522: triage에서 검토 대상으로 선정되었지만 Alert/Case 단계는 아직 실행하지 않았다는 뜻입니다.",
        "중요: 02_run_pipeline.bat, RM 화면 클릭, capacity 비교만으로 Case가 생성되지는 않습니다.",
        "Action/Audit은 격리된 synthetic rehearsal(3 Cases / 10 Audit events) 증거로만 설명합니다.",
    )
    for index, explanation in enumerate(explanations):
        fill = "E6EEF8" if index < 3 else "FFD9DF"
        draw.text((65, panel_top + 100 + index * 49), explanation, fill=fill, font=_font(19, bold=index >= 3))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)
    return destination


def create_workflow_demo_before_after_annotation(
    before_source: Path,
    after_source: Path,
    destination: Path,
) -> Path:
    """Compare real Edge captures without implying an analytics-data change.

    The explanatory labels are intentionally separate from the captured UI.
    They make the state/audit boundary readable in an internal training room,
    while the accompanying full-size screenshots retain the original screen
    details.
    """

    before = Image.open(before_source).convert("RGB")
    after = Image.open(after_source).convert("RGB")
    before_crop = before.crop((0, min(390, before.height - 1), before.width, min(before.height, 1600)))
    after_crop = after.crop((0, min(80, after.height - 1), after.width, min(after.height, 1560)))

    canvas = Image.new("RGB", (2100, 1450), "FFFFFF")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, 160), fill=NAVY)
    draw.text((65, 37), "RM Action 전 · 후 — 실제 Edge 화면에서 바뀌는 것", fill="FFFFFF", font=_font(37, bold=True))
    draw.text(
        (68, 101),
        "화면 crop은 실제 합성 Workflow Demo 캡처이며, 색상 라벨은 교육용 설명입니다.",
        fill="DCEBFA",
        font=_font(19),
    )

    panels = (
        (
            (55, 225, 1020, 1025),
            before_crop,
            "전 · 초기화 직후",
            "C000001 · NEW · demo audit 0",
            GOLD,
        ),
        (
            (1080, 225, 2045, 1025),
            after_crop,
            "후 · Acknowledge 후",
            "C000001 · ACKNOWLEDGED · demo audit 1",
            TEAL,
        ),
    )
    for bounds, crop, title, status, accent in panels:
        x0, y0, x1, y1 = bounds
        draw.rounded_rectangle(bounds, radius=28, fill=LIGHT, outline=LINE, width=3)
        draw.rounded_rectangle((x0, y0, x1, y0 + 84), radius=28, fill=accent)
        draw.text((x0 + 28, y0 + 18), title, fill="FFFFFF", font=_font(28, bold=True))
        draw.text((x0 + 28, y0 + 110), status, fill=NAVY, font=_font(22, bold=True))
        image = crop.copy()
        image.thumbnail((x1 - x0 - 52, y1 - y0 - 190))
        image_x = x0 + (x1 - x0 - image.width) // 2
        image_y = y0 + 165
        draw.rounded_rectangle(
            (image_x - 4, image_y - 4, image_x + image.width + 4, image_y + image.height + 4),
            radius=12,
            fill="FFFFFF",
            outline=LINE,
            width=2,
        )
        canvas.paste(image, (image_x, image_y))

    draw.rounded_rectangle((55, 1080, 2045, 1385), radius=28, fill="F6F9FC", outline=LINE, width=3)
    draw.text((88, 1118), "교육 핵심: 무엇이 바뀌고, 무엇이 그대로인가", fill=NAVY, font=_font(28, bold=True))
    lines = (
        ("변경", "분리된 synthetic Case 상태(NEW → ACKNOWLEDGED)와 append-only demo audit 1건만 변경됩니다.", TEAL),
        ("그대로", "5,000명 population · 고객 재무 데이터 · matcher/outcome/breakpoint · triage/rank · 기본 RM workflow/audit", BLUE),
        ("Preview", "미리보기는 not sent이며 network=0입니다. Case/audit을 추가로 바꾸지 않습니다.", GOLD),
    )
    for index, (label, body, accent) in enumerate(lines):
        y = 1175 + index * 63
        draw.rounded_rectangle((88, y, 250, y + 42), radius=15, fill=accent)
        draw.text((112, y + 8), label, fill="FFFFFF", font=_font(18, bold=True))
        draw.text((280, y + 7), body, fill=GRAY, font=_font(19))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)
    return destination


def _faq_card_text_block(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    title: str,
    body: str,
    accent: str,
) -> int:
    """Draw one compact beginner-facing FAQ block and return its next y value."""

    draw.text((x, y), title, fill=accent, font=_font(20, bold=True))
    wrapped = _wrapped_lines(body, 48)
    draw.multiline_text((x, y + 34), wrapped, fill=NAVY, font=_font(18), spacing=7)
    line_count = wrapped.count("\n") + 1
    return y + 44 + line_count * 30 + 16


def create_faq_status_card(
    path: Path,
    *,
    source: Path,
    question: str,
    status_tag: str,
    answer: str,
    facts: str,
    not_meaning: str,
    presenter_line: str,
    next_check: str,
    accent: str,
) -> Path:
    """Combine an actual Edge screen with a contract-safe FAQ explanation."""

    image = Image.new("RGB", (2000, 1290), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 2000, 152), fill=NAVY)
    draw.text((62, 34), question, fill="FFFFFF", font=_font(32, bold=True))
    draw.rounded_rectangle((62, 98, 590, 137), radius=16, fill=accent)
    draw.text((84, 105), status_tag, fill="FFFFFF", font=_font(17, bold=True))

    left_bounds = (55, 190, 965, 1198)
    right_bounds = (1015, 190, 1945, 1198)
    draw.rounded_rectangle(left_bounds, radius=24, fill=LIGHT, outline=LINE, width=3)
    draw.rounded_rectangle(right_bounds, radius=24, fill="FFFFFF", outline=LINE, width=3)
    draw.text((92, 218), "실제 로컬 Edge 화면 · synthetic demo", fill=GRAY, font=_font(18, bold=True))
    screen = Image.open(source).convert("RGB")
    screen.thumbnail((835, 790))
    screen_x = left_bounds[0] + (left_bounds[2] - left_bounds[0] - screen.width) // 2
    screen_y = 258
    image.paste(screen, (screen_x, screen_y))
    draw.rounded_rectangle((92, 1080, 928, 1165), radius=16, fill="FFFFFF", outline=LINE, width=2)
    draw.multiline_text(
        (116, 1102),
        "화면은 상태를 보여줄 뿐, 이 이미지 자체가 실제 고객 결과·\n외부 전달·승인된 업무 기준을 증명하지는 않습니다.",
        fill=GRAY,
        font=_font(16),
        spacing=5,
    )

    draw.text((1055, 228), "한 줄 답", fill=accent, font=_font(22, bold=True))
    draw.multiline_text((1055, 267), _wrapped_lines(answer, 47), fill=NAVY, font=_font(23, bold=True), spacing=8)
    answer_lines = _wrapped_lines(answer, 47).count("\n") + 1
    y = 286 + answer_lines * 36 + 26
    y = _faq_card_text_block(draw, x=1055, y=y, title="화면·artifact 근거", body=facts, accent=accent)
    y = _faq_card_text_block(draw, x=1055, y=y, title="이것이 의미하지 않는 것", body=not_meaning, accent=RED)
    y = _faq_card_text_block(draw, x=1055, y=y, title="발표 20초 답변", body=presenter_line, accent=TEAL)
    _faq_card_text_block(draw, x=1055, y=y, title="다음 확인", body=next_check, accent=GOLD)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def create_faq_status_overview(path: Path) -> Path:
    """Create a first-page index of four common status questions."""

    image = Image.new("RGB", (2000, 1210), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 2000, 150), fill=NAVY)
    draw.text((64, 40), "자주 나오는 상태별 FAQ — 오류인지, 설계 경계인지 읽는 법", fill="FFFFFF", font=_font(36, bold=True))
    draw.text((66, 103), "각 카드는 실제 synthetic 화면과 저장된 artifact를 바탕으로 합니다. 결과를 과장하거나 상태를 임의로 바꾸지 않습니다.", fill="DCEBFA", font=_font(18))
    cards = (
        (
            (65, 220, 955, 625),
            "1. C002082 · landmark 근거 부족",
            "200명 매칭은 성공했지만 과거 risk-path 0명 / avoidance 200명입니다. 양쪽 최소 20명 비교 조건이 없어 landmark를 표시하지 않습니다.",
            "정상 unavailable · 현재 고객의 미래 예측 아님",
            TEAL,
        ),
        (
            (1045, 220, 1935, 625),
            "2. C000003 · Monitor는 왜 Queue 밖인가",
            "Monitor는 관찰 신호가 있다는 뜻입니다. 다만 triage가 MONITOR_ONLY / NO_ROUTING으로 정했으므로 대표 비교 사례이지 운영 검토 Queue 행이 아닙니다.",
            "정책 신호와 triage selection의 책임 분리",
            BLUE,
        ),
        (
            (65, 690, 955, 1095),
            "3. Capacity=3 · 왜 Deferred 1,519명인가",
            "3은 사람이 입력한 draft 비교값입니다. 저장된 1,522명 순위에서 상위 3명만 비교상 Selected이고 1,519명은 이번 용량 밖이라 Deferred입니다.",
            "1,522 = 3 + 1,519 · 실제 SLA/승인값 아님",
            GOLD,
        ),
        (
            (1045, 690, 1935, 1095),
            "4. Alert / Case = 0 · 왜 오류가 아닌가",
            "기본 workflow repository에는 Case fixture가 없습니다. Triage 선정과 Alert/Case 생성은 분리되어 있어 1,522명은 선정됨·Case 미생성으로 보입니다.",
            "읽기 전용 기본 데모 · 별도 synthetic rehearsal만 존재",
            RED,
        ),
    )
    for bounds, title, body, footer, accent in cards:
        x0, y0, x1, y1 = bounds
        draw.rounded_rectangle(bounds, radius=26, fill="FFFFFF", outline=LINE, width=3)
        draw.rounded_rectangle((x0, y0, x1, y0 + 84), radius=26, fill=accent)
        draw.text((x0 + 30, y0 + 23), title, fill="FFFFFF", font=_font(25, bold=True))
        draw.multiline_text((x0 + 38, y0 + 126), _wrapped_lines(body, 43), fill=NAVY, font=_font(22), spacing=8)
        draw.rounded_rectangle((x0 + 34, y1 - 92, x1 - 34, y1 - 30), radius=16, fill=LIGHT)
        draw.text((x0 + 56, y1 - 72), footer, fill=GRAY, font=_font(17, bold=True))
    image.save(path)
    return path


def create_status_faq_images(screens: dict[str, Path], annotations: dict[str, Path]) -> dict[str, Path]:
    """Create the four FAQ cards only from real local screens and fixed facts."""

    faq: dict[str, Path] = {"faq_overview": create_faq_status_overview(ASSET_DIR / "15_faq_status_overview.png")}
    card_specs = (
        (
            "faq_landmark",
            screens.get("presentation_c002082_insufficient"),
            "Q1. C002082의 landmark 근거 부족은 5,000명이 부족하다는 뜻인가?",
            "정상적인 unavailable 결과",
            "아닙니다. 200명 유사 경로 매칭은 성공했지만, 과거 결과 비교에 필요한 두 집단이 만들어지지 않아 landmark를 표시하지 않은 것입니다.",
            "matched_count=200 · analysis_status=success · risk-path=0명 · avoidance=200명 · landmark 비교 규칙은 양쪽 최소 20명입니다.",
            "이 고객이 미래에 안전하다는 뜻, 전체 5,000명이 부족해 분석이 실패했다는 뜻, 현재 고객의 미래 날짜를 예측했다는 뜻이 아닙니다.",
            "‘매칭은 됐지만 비교할 과거 risk-path 집단이 없어 landmark를 억지로 만들지 않았습니다.’",
            "Presentation ③ 유사 경로 근거의 ‘분석 제한 / 비교 제한’과 caption을 함께 확인합니다.",
            TEAL,
        ),
        (
            "faq_monitor",
            screens.get("rm_monitor_c000003"),
            "Q2. C000003은 Monitor인데 왜 운영 Review Queue에 없나요?",
            "업무 Queue와 분리된 비교 상태",
            "Monitor는 관찰할 현재 신호가 있다는 뜻입니다. 하지만 이 run의 triage 결과는 즉시 검토 Queue에 넣는 대상으로 결정되지 않았습니다.",
            "primary_disposition=MONITOR_ONLY · selection_disposition=NOT_QUEUE_ELIGIBLE · routing_disposition=NO_ROUTING · selected_for_review=false.",
            "Monitor에 신호가 전혀 없다는 뜻, Monitor가 운영 Queue 행이라는 뜻, 모든 policy signal이 Alert가 된다는 뜻이 아닙니다.",
            "‘정책 신호와 triage selection은 다릅니다. C000003은 대표 비교 사례로 보이되 Queue에는 섞지 않습니다.’",
            "C000003 검색 시 Queue 0건 화면과 Customer Review의 ‘대표 비교 사례’ 문구를 나란히 봅니다.",
            BLUE,
        ),
        (
            "faq_capacity",
            screens.get("rm_capacity_3"),
            "Q3. 사람이 Capacity=3을 입력하면 왜 1,519명이 Deferred인가?",
            "사람이 입력한 draft 비교값",
            "3은 시스템이 정한 적정 업무량이 아닙니다. 저장된 1,522명 순위에서 앞 3명만 이번 비교상 Selected이고 나머지는 용량 밖이라 Deferred로 표시됩니다.",
            "eligible=1,522 · entered capacity=3 · selected=3 · deferred=1,519 · 1,522 = 3 + 1,519 · saved rank prefix cutoff only.",
            "1,519명을 버리거나 위험이 낮다고 판단했다는 뜻, 실제 RM이 3명만 처리할 수 있다는 뜻, Alert/Case가 자동 생성됐다는 뜻이 아닙니다.",
            "‘사람이 가정을 바꾸어 trade-off를 보는 화면입니다. 순위·원본 manifest·Alert/Case는 바꾸지 않습니다.’",
            "표의 unbounded demo 기준과 입력 용량 3명을 동시에 보고, status=draft와 비교 전용 문구를 확인합니다.",
            GOLD,
        ),
        (
            "faq_alert_case",
            annotations.get("rm_alert_case_status"),
            "Q4. Alert와 Case가 모두 0개인 이유는 무엇인가?",
            "읽기 전용 기본 상태",
            "오류가 아닙니다. 기본 workflow repository에 Case fixture가 없고, Triage 선정과 Alert/Case 생성은 의도적으로 다른 단계입니다.",
            "기본 화면: open Alert=0 · RM Queue Case=0 · selected Case pending=1,522. 격리 rehearsal: synthetic Case 3건 · audit 10건 · network=false.",
            "선정 결과가 없다는 뜻, UI에서 숨은 Case 생성 작업이 있다는 뜻, 외부 메시지가 발송됐다는 뜻이 아닙니다.",
            "‘기본 데모는 선정 근거를 읽는 상태입니다. Action/Audit은 분리된 합성 rehearsal 증거로만 설명합니다.’",
            "02_run_pipeline, RM 탐색, capacity 비교는 Case를 만들지 않습니다. 18~19장의 기본/격리 흐름도를 확인합니다.",
            RED,
        ),
    )
    for key, source, question, tag, answer, facts, not_meaning, presenter, next_check, accent in card_specs:
        if source is None or not source.exists():
            continue
        faq[key] = create_faq_status_card(
            ASSET_DIR / f"{len(faq) + 15:02d}_{key}.png",
            source=source,
            question=question,
            status_tag=tag,
            answer=answer,
            facts=facts,
            not_meaning=not_meaning,
            presenter_line=presenter,
            next_check=next_check,
            accent=accent,
        )
    return faq


def create_sample_customer_map(path: Path) -> Path:
    """Create a visual map of the three safe General-mode demo inputs."""

    image = Image.new("RGB", (1800, 880), "FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1800, 135), fill=NAVY)
    draw.text((65, 37), "일반 모드 — 고객 입력 샘플", fill="FFFFFF", font=_font(40, bold=True))
    draw.text((67, 95), "세 고객은 합성 데모 역할로만 사용합니다. 미래 label 또는 실제 업무 우선순위의 근거가 아닙니다.", fill="DCEBFA", font=_font(18))
    cards = (
        (
            (70, 220, 570, 690),
            "C002608 · 메인 고객",
            "발표와 기본 분석의 시작점\n• 200명 유사 고객\n• Presentation 5 tabs\n• historical landmark를 설명할 때 사용",
            BLUE,
        ),
        (
            (650, 220, 1150, 690),
            "C002082 · 안정 비교",
            "‘근거 부족’도 정상 결과임을 보여줌\n• 안정 흐름 대비\n• landmark unavailable/insufficient을 숨기지 않음\n• Q&A 정직성 사례",
            TEAL,
        ),
        (
            (1230, 220, 1730, 690),
            "C002672 · 고위험 시각 대비",
            "강한 흐름 대비가 필요할 때\n• stress 관찰 사례\n• 시각적 Q&A용\n• RM 선정/미래 결과 증거로 사용 금지",
            RED,
        ),
    )
    for bounds, title, body, color in cards:
        _rounded_box(draw, bounds, title=title, body=body, accent=color, title_size=27, body_size=21)
    draw.rounded_rectangle((165, 750, 1635, 830), radius=22, fill=LIGHT, outline=LINE, width=2)
    draw.text((220, 777), "직접 ID 입력은 synthetic data에 존재하는 ID만 사용합니다. 보이지 않는 ID나 실제 고객 정보를 입력하지 마십시오.", fill=GRAY, font=_font(19))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def create_manual_annotations(screens: dict[str, Path]) -> dict[str, Path]:
    """Derive visual, screen-based teaching aids when live captures are available."""

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    annotations = {"sample_map": create_sample_customer_map(ASSET_DIR / "08_general_sample_customers.png")}
    general_screen = screens.get("general")
    if general_screen is not None and general_screen.exists():
        annotations["general_inputs"] = create_general_input_annotation(
            general_screen,
            ASSET_DIR / "07_general_mode_annotated_inputs.png",
        )
    rm_screen = screens.get("rm")
    if rm_screen is not None and rm_screen.exists():
        annotations["rm_alert_case_status"] = create_rm_alert_case_status_annotation(
            rm_screen,
            ASSET_DIR / "13_rm_alert_case_status_explained.png",
        )
    workflow_before = screens.get("workflow_demo_new")
    workflow_after = screens.get("workflow_demo_ack")
    if (
        workflow_before is not None
        and workflow_before.exists()
        and workflow_after is not None
        and workflow_after.exists()
    ):
        annotations["workflow_demo_before_after"] = create_workflow_demo_before_after_annotation(
            workflow_before,
            workflow_after,
            ASSET_DIR / "22_workflow_demo_action_before_after.png",
        )
    annotations.update(create_status_faq_images(screens, annotations))
    return annotations


CAPTURE_WRAPPER = """\
import os
import runpy
import sys
from pathlib import Path

import streamlit as st

project_root = Path(os.environ[\"FPT_PROJECT_ROOT\"])
sys.path.insert(0, str(project_root))

# The documentation renderer can request a short-lived Workflow Demo timeline.
# Patch only this child Streamlit process so every call to default() uses an
# immutable workspace fixture plus a runtime outside the repository. The normal
# application never receives either environment value and keeps its default path.
workflow_demo_runtime_root = os.environ.get(\"FPT_CAPTURE_WORKFLOW_DEMO_RUNTIME_ROOT\")
workflow_demo_fixture_path = os.environ.get(\"FPT_CAPTURE_WORKFLOW_DEMO_FIXTURE_PATH\")
if workflow_demo_runtime_root and workflow_demo_fixture_path:
    from src.workflow_demo import WorkflowDemoPaths

    _capture_workflow_demo_paths = WorkflowDemoPaths(
        fixture_path=Path(workflow_demo_fixture_path),
        runtime_root=Path(workflow_demo_runtime_root),
    )

    def _capture_workflow_demo_default(cls):
        return _capture_workflow_demo_paths

    WorkflowDemoPaths.default = classmethod(_capture_workflow_demo_default)

workflow_demo_stage = os.environ.get(\"FPT_CAPTURE_WORKFLOW_DEMO_STAGE\")
if workflow_demo_stage:
    from datetime import datetime, timezone

    from src.rm_workflow_ui import (
        build_offline_notification_preview,
        create_file_backed_rm_workflow_ui_service,
        load_rm_workflow_case,
        perform_rm_workflow_operation,
    )
    from src.workflow_demo import reset_demo
    from src.workflow_demo_ui import (
        WORKFLOW_DEMO_FEEDBACK_KEY,
        WORKFLOW_DEMO_OPEN_KEY,
        WORKFLOW_DEMO_PREVIEW_KEY,
    )

    if not (workflow_demo_runtime_root and workflow_demo_fixture_path):
        raise RuntimeError(\"workflow-demo capture stage requires temporary paths\")
    st.session_state[WORKFLOW_DEMO_OPEN_KEY] = True
    if workflow_demo_stage != \"entry\":
        capture_paths = WorkflowDemoPaths.default()
        reset_demo(capture_paths)
        if workflow_demo_stage in {\"acknowledged\", \"preview\"}:
            service = create_file_backed_rm_workflow_ui_service(
                workflow_root=capture_paths.workflow_root,
                audit_root=capture_paths.audit_root,
            )
            response = perform_rm_workflow_operation(
                service,
                operation=\"ACKNOWLEDGE\",
                alert_id=\"ALT-DEMO-C000001\",
                expected_state=\"NEW\",
                occurred_at=datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc),
                actor_reference=\"synthetic-workflow-demo-capture\",
                idempotency_token=\"operating-manual-capture-acknowledge-v1\",
            )
            st.session_state[WORKFLOW_DEMO_FEEDBACK_KEY] = {
                \"alert_id\": response.alert_case.alert_id,
                \"message\": \"RM 업무 조치와 감사 이벤트가 기록되었습니다.\",
                \"operation\": response.operation,
                \"current_state\": response.current_state,
                \"audit_event_id\": response.audit_event.event_id,
            }
            if workflow_demo_stage == \"preview\":
                alert_case = load_rm_workflow_case(
                    service,
                    alert_id=\"ALT-DEMO-C000001\",
                )
                if alert_case is None:
                    raise RuntimeError(\"workflow-demo capture case is unavailable\")
                st.session_state[WORKFLOW_DEMO_PREVIEW_KEY] = {
                    \"alert_id\": alert_case.alert_id,
                    \"result\": build_offline_notification_preview(
                        service,
                        alert_case=alert_case,
                    ),
                }
                st.session_state[\"rm_workflow_demo_capture_preview_expanded\"] = True

mode = os.environ.get(\"FPT_CAPTURE_MODE\")
if mode:
    st.session_state[\"app_mode\"] = mode
st.session_state[\"ui_language\"] = os.environ.get(\"FPT_CAPTURE_LANGUAGE\", \"ko\")
capacity = os.environ.get(\"FPT_CAPTURE_CAPACITY\")
if capacity:
    # This setting exists only in the temporary, one-screen capture session.
    # It is deliberately not written to a triage manifest, workflow repository,
    # or any source artifact.
    st.session_state[\"rm_capacity_comparison_enabled\"] = True
    st.session_state[\"rm_capacity_comparison_value\"] = int(capacity)
customer_id = os.environ.get(\"FPT_CAPTURE_CUSTOMER_ID\")
direct_input_customer_id = os.environ.get(\"FPT_CAPTURE_DIRECT_INPUT_CUSTOMER_ID\")
presentation_option = os.environ.get(\"FPT_CAPTURE_PRESENTATION_OPTION\")
if direct_input_customer_id:
    # This documentation-only session follows the same explicit Manual input
    # route a learner uses in the real app.  It never changes source data.
    st.session_state[\"customer_selector\"] = \"__manual_customer_id__\"
    st.session_state[\"customer_id_input\"] = direct_input_customer_id
elif customer_id:
    # These values live only in the short-lived Streamlit capture session.  The
    # normal app remains responsible for validating the selected demo option.
    if presentation_option:
        st.session_state[\"presentation_customer_selector\"] = presentation_option
    else:
        st.session_state[\"customer_selector\"] = customer_id
representative_category = os.environ.get(\"FPT_CAPTURE_RM_REPRESENTATIVE_CATEGORY\")
if representative_category:
    st.session_state[\"rm_representative_quick_select\"] = representative_category
if customer_id and representative_category:
    st.session_state[\"rm_customer_context\"] = customer_id
queue_search = os.environ.get(\"FPT_CAPTURE_RM_QUEUE_SEARCH\")
if queue_search:
    st.session_state[\"rm_queue_search\"] = queue_search
if mode == \"RM 업무 모드\":
    st.session_state.setdefault(\"rm_customer_context\", \"C000001\")
runpy.run_path(str(project_root / \"app.py\"), run_name=\"__main__\")
"""


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _find_chrome() -> Path | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    ]
    discovered = shutil.which("chrome") or shutil.which("chrome.exe")
    if discovered:
        candidates.insert(0, Path(discovered))
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _find_edge() -> Path | None:
    """Find Microsoft Edge without touching an existing user browser profile."""

    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    discovered = shutil.which("msedge") or shutil.which("msedge.exe")
    if discovered:
        candidates.insert(0, Path(discovered))
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _wait_for_devtools(port: int, timeout_seconds: int = 20) -> list[dict[str, object]]:
    """Wait for an Edge DevTools endpoint bound to localhost only."""

    url = f"http://127.0.0.1:{port}/json"
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # nosec B310 - localhost only
                payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, list) and payload:
                    return [item for item in payload if isinstance(item, dict)]
        except Exception as error:  # noqa: BLE001 - retain a useful failure cause
            last_error = error
        time.sleep(0.4)
    raise RuntimeError(f"Edge DevTools did not become ready within {timeout_seconds}s: {last_error}")


def _cdp_command(connection: websocket.WebSocket, command_id: int, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
    """Send one synchronous Chrome DevTools Protocol command."""

    connection.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(connection.recv())
        if message.get("id") == command_id:
            if "error" in message:
                raise RuntimeError(f"CDP {method} failed: {message['error']}")
            result = message.get("result", {})
            return result if isinstance(result, dict) else {}


def _wait_for_rendered_text(
    connection: websocket.WebSocket,
    command_id: int,
    *,
    expected_text: str,
    timeout_seconds: int = 24,
) -> int:
    """Wait through Streamlit reruns until the intended mode's text is visible."""

    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = _cdp_command(
                connection,
                command_id,
                "Runtime.evaluate",
                {"expression": "document.body ? document.body.innerText : ''", "returnByValue": True},
            )
            command_id += 1
            remote_result = result.get("result")
            text_value = remote_result.get("value") if isinstance(remote_result, dict) else ""
            if isinstance(text_value, str) and expected_text in text_value:
                return command_id
        except RuntimeError as error:
            last_error = error
            command_id += 1
        time.sleep(0.8)
    raise RuntimeError(f"The Edge page did not render expected text {expected_text!r}: {last_error}")


def _edge_page_websocket(port: int, expected_url: str) -> str:
    """Return the websocket for the temporary local app tab."""

    pages = _wait_for_devtools(port)
    for page in pages:
        if page.get("type") == "page" and str(page.get("url", "")).startswith(expected_url):
            websocket_url = page.get("webSocketDebuggerUrl")
            if isinstance(websocket_url, str):
                return websocket_url
    # Edge can expose about:blank first while navigation is underway. Retry once.
    time.sleep(1)
    pages = _wait_for_devtools(port)
    for page in pages:
        websocket_url = page.get("webSocketDebuggerUrl")
        if page.get("type") == "page" and isinstance(websocket_url, str):
            return websocket_url
    raise RuntimeError("Edge DevTools did not expose a debuggable page target.")


def _wait_for_streamlit(port: int, timeout_seconds: int = 55) -> None:
    url = f"http://127.0.0.1:{port}/_stcore/health"
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # nosec B310 - localhost only
                if response.status == 200:
                    return
        except Exception as error:  # noqa: BLE001 - preserve the final diagnostic
            last_error = error
        time.sleep(0.5)
    raise RuntimeError(f"Streamlit did not become healthy within {timeout_seconds}s: {last_error}")


def _capture_one_screen(*, mode: str, filename: str) -> Path:
    """Capture one mode through a finite local-only Streamlit/Chrome session."""

    chrome = _find_chrome()
    if chrome is None:
        raise RuntimeError("Google Chrome was not found; screenshots cannot be captured.")
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = OUTPUT_DIR / "_capture_app.py"
    wrapper_path.write_text(CAPTURE_WRAPPER, encoding="utf-8")
    port = _pick_free_port()
    environment = os.environ.copy()
    environment.update(
        {
            "FPT_PROJECT_ROOT": str(PROJECT_ROOT),
            "FPT_CAPTURE_MODE": mode,
            "FPT_CAPTURE_LANGUAGE": "ko",
        }
    )
    process: subprocess.Popen[str] | None = None
    profile_dir = Path(tempfile.mkdtemp(prefix="financial_path_twin_capture_"))
    destination = SCREEN_DIR / filename
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(wrapper_path),
                "--server.headless=true",
                f"--server.port={port}",
                "--server.address=127.0.0.1",
                "--browser.gatherUsageStats=false",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creation_flags,
        )
        _wait_for_streamlit(port)
        url = f"http://127.0.0.1:{port}"
        chrome_command = [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--user-data-dir={profile_dir}",
            "--window-size=1440,1500",
            "--virtual-time-budget=7000",
            f"--screenshot={destination}",
            url,
        ]
        try:
            subprocess.run(chrome_command, check=True, timeout=40, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            # Older Chrome builds accept --headless but not --headless=new.
            chrome_command[1] = "--headless"
            subprocess.run(chrome_command, check=True, timeout=40, capture_output=True, text=True)
        if not destination.exists() or destination.stat().st_size < 1024:
            raise RuntimeError(f"Chrome did not create a usable screenshot: {destination}")
        return destination
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        wrapper_path.unlink(missing_ok=True)
        shutil.rmtree(profile_dir, ignore_errors=True)


def capture_screens() -> dict[str, Path]:
    """Capture the three primary modes.  Each server is bounded and stopped."""

    return {
        "presentation": _capture_one_screen(mode=APP_MODE_PRESENTATION, filename="01_presentation_mode.png"),
        "general": _capture_one_screen(mode=APP_MODE_GENERAL, filename="02_general_mode.png"),
        "rm": _capture_one_screen(mode=APP_MODE_RM, filename="03_rm_portfolio.png"),
    }


def _capture_one_edge_screen(
    *,
    mode: str,
    filename: str,
    interaction_scripts: tuple[str, ...] = (),
    session_capacity: int | None = None,
    session_customer_id: str | None = None,
    session_direct_input_customer_id: str | None = None,
    session_presentation_option: str | None = None,
    session_representative_category: str | None = None,
    session_queue_search: str | None = None,
) -> Path:
    """Capture a real Edge-rendered app viewport through a bounded local session.

    A separate temporary Edge profile is always used.  The DevTools endpoint is
    loopback-only and lives only for this one screenshot.  Existing user Edge
    tabs, profiles, workflow files, and analytics artifacts are untouched.
    """

    edge = _find_edge()
    if edge is None:
        raise RuntimeError("Microsoft Edge was not found; Edge screenshots cannot be captured.")
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = OUTPUT_DIR / "_capture_app.py"
    wrapper_path.write_text(CAPTURE_WRAPPER, encoding="utf-8")
    streamlit_port = _pick_free_port()
    devtools_port = _pick_free_port()
    app_url = f"http://127.0.0.1:{streamlit_port}"
    environment = os.environ.copy()
    environment.update(
        {
            "FPT_PROJECT_ROOT": str(PROJECT_ROOT),
            "FPT_CAPTURE_MODE": mode,
            "FPT_CAPTURE_LANGUAGE": "ko",
            "FPT_CAPTURE_CAPACITY": "" if session_capacity is None else str(session_capacity),
            "FPT_CAPTURE_CUSTOMER_ID": session_customer_id or "",
            "FPT_CAPTURE_DIRECT_INPUT_CUSTOMER_ID": session_direct_input_customer_id or "",
            "FPT_CAPTURE_PRESENTATION_OPTION": session_presentation_option or "",
            "FPT_CAPTURE_RM_REPRESENTATIVE_CATEGORY": session_representative_category or "",
            "FPT_CAPTURE_RM_QUEUE_SEARCH": session_queue_search or "",
        }
    )
    streamlit_process: subprocess.Popen[str] | None = None
    edge_process: subprocess.Popen[bytes] | None = None
    profile_dir = Path(tempfile.mkdtemp(prefix="financial_path_twin_edge_capture_"))
    destination = SCREEN_DIR / filename
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        streamlit_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(wrapper_path),
                "--server.headless=true",
                f"--server.port={streamlit_port}",
                "--server.address=127.0.0.1",
                "--browser.gatherUsageStats=false",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=creation_flags,
        )
        _wait_for_streamlit(streamlit_port)
        # Headless Edge still uses the production Edge rendering engine while
        # keeping the temporary capture isolated from the user's active window.
        edge_process = subprocess.Popen(
            [
                str(edge),
                "--new-window",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={devtools_port}",
                "--remote-allow-origins=http://localhost",
                "--window-position=30,30",
                "--window-size=1440,1500",
                app_url,
            ],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        websocket_url = _edge_page_websocket(devtools_port, app_url)
        # A tab change can trigger a full Streamlit rerun before CDP sends the
        # next command response.  Give the bounded, local-only capture session
        # enough time to settle so a valid current screenshot is not discarded.
        connection = websocket.create_connection(websocket_url, timeout=90, origin="http://localhost")
        try:
            command_id = 1
            _cdp_command(connection, command_id, "Page.enable")
            command_id += 1
            _cdp_command(connection, command_id, "Page.bringToFront")
            command_id += 1
            # Streamlit intentionally replaces its execution context during the
            # first websocket render.  Waiting outside that context is more
            # reliable than evaluating a JavaScript promise while it reruns.
            time.sleep(8)
            expected_text = "RM 업무 공간" if mode == APP_MODE_RM else "Financial Path Twin"
            command_id = _wait_for_rendered_text(
                connection,
                command_id,
                expected_text=expected_text,
            )
            # The app intentionally starts with a compact sidebar.  Expand it
            # for the operating manual so customer/metric input controls are
            # visible in the actual raster capture.  A missing selector is
            # harmless on future Streamlit versions.
            sidebar_result = _cdp_command(
                connection,
                command_id,
                "Runtime.evaluate",
                {
                    "expression": "(() => { const buttons = Array.from(document.querySelectorAll('button')); const target = document.querySelector('[data-testid=\"stSidebarCollapsedControl\"] button, [data-testid=\"stSidebarCollapsedControl\"]') || buttons.find(button => /sidebar|side bar|open navigation|expand/i.test([button.innerText, button.getAttribute('aria-label'), button.getAttribute('title'), button.getAttribute('data-testid')].filter(Boolean).join(' '))) || buttons.find(button => /[»›]/.test(button.innerText)); if (target) { target.click(); return 'expanded:' + (target.getAttribute('aria-label') || target.getAttribute('title') || target.getAttribute('data-testid') || target.innerText || 'button'); } return JSON.stringify(buttons.slice(0, 20).map(button => ({text: button.innerText, aria: button.getAttribute('aria-label'), title: button.getAttribute('title'), testid: button.getAttribute('data-testid')}))); })()",
                    "returnByValue": True,
                },
            )
            evaluated = sidebar_result.get("result")
            if isinstance(evaluated, dict):
                print(f"Edge sidebar control: {evaluated.get('value', 'unknown')}")
            command_id += 1
            time.sleep(2)
            # A scenario may select a tab or set a session-only capacity value.
            # It runs only against the temporary browser/session created above;
            # no canonical artifact, workflow repository, or user Edge profile
            # is mutated.  We wait after every interaction because Streamlit can
            # legitimately rerun the page when a widget changes.
            for expression in interaction_scripts:
                _cdp_command(
                    connection,
                    command_id,
                    "Runtime.evaluate",
                    {"expression": expression, "returnByValue": True},
                )
                command_id += 1
                time.sleep(3)
                command_id = _wait_for_rendered_text(
                    connection,
                    command_id,
                    expected_text=expected_text,
                )
            result = _cdp_command(
                connection,
                command_id,
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": False, "fromSurface": True},
            )
        finally:
            connection.close()
        encoded = result.get("data")
        if not isinstance(encoded, str):
            raise RuntimeError("Edge returned no PNG data from Page.captureScreenshot.")
        destination.write_bytes(base64.b64decode(encoded))
        if destination.stat().st_size < 1024:
            raise RuntimeError(f"Edge did not create a usable screenshot: {destination}")
        return destination
    finally:
        for process in (edge_process, streamlit_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        wrapper_path.unlink(missing_ok=True)
        shutil.rmtree(profile_dir, ignore_errors=True)


def _tree_digest(path: Path) -> str:
    """Return a stable digest for one protected local artifact root."""

    if not path.exists():
        return "MISSING"
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        relative = child.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        if child.is_file():
            digest.update(child.read_bytes())
    return digest.hexdigest()


def _capture_cdp_viewport(
    connection: websocket.WebSocket,
    command_id: int,
    destination: Path,
) -> int:
    """Save one real, current Edge viewport from a bounded local capture session."""

    result = _cdp_command(
        connection,
        command_id,
        "Page.captureScreenshot",
        {"format": "png", "captureBeyondViewport": False, "fromSurface": True},
    )
    encoded = result.get("data")
    if not isinstance(encoded, str):
        raise RuntimeError("Edge returned no PNG data from Page.captureScreenshot.")
    destination.write_bytes(base64.b64decode(encoded))
    if destination.stat().st_size < 1024:
        raise RuntimeError(f"Edge did not create a usable screenshot: {destination}")
    return command_id + 1


def _button_click_script(label: str) -> str:
    """Build a text-exact button click for a deterministic Korean capture."""

    encoded_label = json.dumps(label, ensure_ascii=False)
    return f"""(() => {{
        const label = {encoded_label};
        const button = Array.from(document.querySelectorAll('button')).find((item) =>
            ((item.innerText || '').trim() === label) ||
            ((item.getAttribute('aria-label') || '').trim() === label)
        );
        if (!button) return 'missing-button:' + label;
        button.scrollIntoView({{block: 'center', behavior: 'instant'}});
        button.click();
        return 'clicked-button:' + label;
    }})()"""


def _scroll_to_text_script(label: str) -> str:
    """Scroll to the first visible text node containing a stable training label."""

    encoded_label = json.dumps(label, ensure_ascii=False)
    return f"""(() => {{
        const label = {encoded_label};
        const nodes = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,p,span,div,summary'));
        const target = nodes.find((item) => (item.innerText || '').trim() === label) ||
            nodes.find((item) => (item.innerText || '').includes(label));
        if (!target) return 'missing-text:' + label;
        target.scrollIntoView({{block: 'start', behavior: 'instant'}});
        return 'scrolled:' + label;
    }})()"""


def _open_expander_script(label: str) -> str:
    """Open one Streamlit expander without changing the workflow model."""

    encoded_label = json.dumps(label, ensure_ascii=False)
    return f"""(() => {{
        const label = {encoded_label};
        const summary = Array.from(document.querySelectorAll('details summary')).find((item) =>
            (item.innerText || '').includes(label)
        );
        if (!summary) return 'missing-expander:' + label;
        const details = summary.closest('details');
        if (details && !details.open) summary.click();
        summary.scrollIntoView({{block: 'start', behavior: 'instant'}});
        return 'opened-expander:' + label;
    }})()"""


def _assert_cdp_interaction(result: dict[str, object]) -> None:
    """Fail rather than silently save a screenshot from the wrong app state."""

    remote_result = result.get("result")
    value = remote_result.get("value") if isinstance(remote_result, dict) else None
    if isinstance(value, str) and value.startswith("missing-"):
        raise RuntimeError(f"Workflow Demo capture interaction failed: {value}")


def _run_timeline_interaction(
    connection: websocket.WebSocket,
    command_id: int,
    *,
    expression: str,
    expected_text: str,
) -> int:
    """Run one user-equivalent DOM interaction and wait through Streamlit reruns."""

    result = _cdp_command(
        connection,
        command_id,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
    )
    _assert_cdp_interaction(result)
    command_id += 1
    time.sleep(3)
    return _wait_for_rendered_text(
        connection,
        command_id,
        expected_text=expected_text,
    )


def _run_timeline_view_interaction(
    connection: websocket.WebSocket,
    command_id: int,
    *,
    expression: str,
) -> int:
    """Run a scroll/expander interaction that does not write a Case or audit."""

    result = _cdp_command(
        connection,
        command_id,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
    )
    _assert_cdp_interaction(result)
    time.sleep(1)
    return command_id + 1


def _capture_workflow_demo_timeline_with_cdp_legacy() -> dict[str, Path]:
    """Capture the Workflow Demo in one real Edge session and temporary runtime.

    The sequence intentionally uses the UI itself for Open, Initialize,
    Acknowledge, Preview, Reset, and Return.  Its mutable Case/audit files live
    only below a temporary directory injected into the capture child process.
    Default workflow/audit roots and the workspace demo fixture are hash-checked
    before and after capture.
    """

    edge = _find_edge()
    if edge is None:
        raise RuntimeError("Microsoft Edge was not found; Workflow Demo screenshots cannot be captured.")

    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = OUTPUT_DIR / "_capture_app.py"
    wrapper_path.write_text(CAPTURE_WRAPPER, encoding="utf-8")
    streamlit_port = _pick_free_port()
    devtools_port = _pick_free_port()
    app_url = f"http://127.0.0.1:{streamlit_port}"
    fixture_path = (
        PROJECT_ROOT
        / "artifacts"
        / "workflow_demo"
        / "fixture_v1"
        / "workflow_demo_fixture.json"
    )
    if not fixture_path.is_file():
        raise RuntimeError(f"Workflow Demo fixture is missing: {fixture_path}")

    protected_paths = {
        "default_workflow": PROJECT_ROOT / "artifacts" / "workflow",
        "default_audit": PROJECT_ROOT / "artifacts" / "audit",
        "workspace_workflow_demo": PROJECT_ROOT / "artifacts" / "workflow_demo",
    }
    protected_before = {name: _tree_digest(path) for name, path in protected_paths.items()}
    timeline_root = Path(tempfile.mkdtemp(prefix="financial_path_twin_workflow_demo_timeline_"))
    runtime_root = timeline_root / "runtime"
    profile_dir = Path(tempfile.mkdtemp(prefix="financial_path_twin_edge_capture_"))
    environment = os.environ.copy()
    environment.update(
        {
            "FPT_PROJECT_ROOT": str(PROJECT_ROOT),
            "FPT_CAPTURE_MODE": APP_MODE_RM,
            "FPT_CAPTURE_LANGUAGE": "ko",
            "FPT_CAPTURE_WORKFLOW_DEMO_RUNTIME_ROOT": str(runtime_root),
            "FPT_CAPTURE_WORKFLOW_DEMO_FIXTURE_PATH": str(fixture_path),
        }
    )

    streamlit_process: subprocess.Popen[str] | None = None
    edge_process: subprocess.Popen[bytes] | None = None
    captured: dict[str, Path] = {}
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        streamlit_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(wrapper_path),
                "--server.headless=true",
                f"--server.port={streamlit_port}",
                "--server.address=127.0.0.1",
                "--browser.gatherUsageStats=false",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=creation_flags,
        )
        _wait_for_streamlit(streamlit_port)
        edge_process = subprocess.Popen(
            [
                str(edge),
                "--new-window",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={devtools_port}",
                "--remote-allow-origins=http://localhost",
                "--window-position=30,30",
                "--window-size=1440,1500",
                app_url,
            ],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        websocket_url = _edge_page_websocket(devtools_port, app_url)
        connection = websocket.create_connection(websocket_url, timeout=12, origin="http://localhost")
        try:
            command_id = 1
            _cdp_command(connection, command_id, "Page.enable")
            command_id += 1
            _cdp_command(connection, command_id, "Page.bringToFront")
            command_id += 1
            time.sleep(8)
            command_id = _wait_for_rendered_text(
                connection,
                command_id,
                expected_text="RM 업무 공간",
            )

            command_id = _run_timeline_interaction(
                connection,
                command_id,
                expression=_button_click_script("합성 Workflow Demo 열기"),
                expected_text="합성 Workflow Demo",
            )
            captured["workflow_demo_entry"] = SCREEN_DIR / "12_workflow_demo_entry_uninitialized.png"
            command_id = _capture_cdp_viewport(
                connection,
                command_id,
                captured["workflow_demo_entry"],
            )

            command_id = _run_timeline_interaction(
                connection,
                command_id,
                expression=_button_click_script("합성 Case 초기화"),
                expected_text="C000001",
            )
            captured["workflow_demo_new"] = SCREEN_DIR / "13_workflow_demo_new_before_action.png"
            command_id = _capture_cdp_viewport(
                connection,
                command_id,
                captured["workflow_demo_new"],
            )

            command_id = _run_timeline_interaction(
                connection,
                command_id,
                expression=_button_click_script("확인"),
                expected_text="확인됨",
            )
            captured["workflow_demo_ack"] = SCREEN_DIR / "14_workflow_demo_ack_after_action.png"
            command_id = _capture_cdp_viewport(
                connection,
                command_id,
                captured["workflow_demo_ack"],
            )

            command_id = _run_timeline_view_interaction(
                connection,
                command_id,
                expression=_scroll_to_text_script("합성 Activity / Audit"),
            )
            captured["workflow_demo_audit"] = SCREEN_DIR / "15_workflow_demo_audit_after_action.png"
            command_id = _capture_cdp_viewport(
                connection,
                command_id,
                captured["workflow_demo_audit"],
            )

            command_id = _run_timeline_view_interaction(
                connection,
                command_id,
                expression=_scroll_to_text_script("알림 미리보기(오프라인)"),
            )
            command_id = _run_timeline_view_interaction(
                connection,
                command_id,
                expression=_open_expander_script("알림 미리보기(오프라인)"),
            )
            command_id = _run_timeline_interaction(
                connection,
                command_id,
                expression=_button_click_script("오프라인 미리보기 생성"),
                expected_text="Offline preview only for an existing RM review case.",
            )
            command_id = _run_timeline_view_interaction(
                connection,
                command_id,
                expression=_open_expander_script("알림 미리보기(오프라인)"),
            )
            captured["workflow_demo_preview"] = SCREEN_DIR / "16_workflow_demo_preview_not_sent.png"
            command_id = _capture_cdp_viewport(
                connection,
                command_id,
                captured["workflow_demo_preview"],
            )

            command_id = _run_timeline_interaction(
                connection,
                command_id,
                expression=_button_click_script("합성 Case 초기 상태로 reset"),
                expected_text="신규",
            )
            command_id = _run_timeline_view_interaction(
                connection,
                command_id,
                expression="window.scrollTo({top: 0, behavior: 'instant'}); 'scrolled-top';",
            )
            captured["workflow_demo_reset"] = SCREEN_DIR / "17_workflow_demo_reset_new.png"
            command_id = _capture_cdp_viewport(
                connection,
                command_id,
                captured["workflow_demo_reset"],
            )

            command_id = _run_timeline_interaction(
                connection,
                command_id,
                expression=_button_click_script("기본 RM 업무로 돌아가기"),
                expected_text="RM 업무 공간",
            )
            captured["workflow_demo_return"] = SCREEN_DIR / "18_workflow_demo_return_baseline.png"
            _capture_cdp_viewport(
                connection,
                command_id,
                captured["workflow_demo_return"],
            )
        finally:
            connection.close()

        protected_after = {name: _tree_digest(path) for name, path in protected_paths.items()}
        if protected_before != protected_after:
            changed = sorted(
                name
                for name in protected_before
                if protected_before[name] != protected_after[name]
            )
            raise RuntimeError(
                "Workflow Demo capture changed protected workspace artifacts: " + ", ".join(changed)
            )
        return captured
    finally:
        for process in (edge_process, streamlit_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        wrapper_path.unlink(missing_ok=True)
        shutil.rmtree(profile_dir, ignore_errors=True)
        shutil.rmtree(timeline_root, ignore_errors=True)


def _capture_workflow_demo_stage_with_edge(*, stage: str, filename: str) -> Path:
    """Render one deterministic Workflow Demo state through a temporary Edge app."""

    edge = _find_edge()
    if edge is None:
        raise RuntimeError("Microsoft Edge was not found; Workflow Demo screenshots cannot be captured.")
    fixture_path = (
        PROJECT_ROOT
        / "artifacts"
        / "workflow_demo"
        / "fixture_v1"
        / "workflow_demo_fixture.json"
    )
    if not fixture_path.is_file():
        raise RuntimeError(f"Workflow Demo fixture is missing: {fixture_path}")

    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = OUTPUT_DIR / "_capture_app.py"
    wrapper_path.write_text(CAPTURE_WRAPPER, encoding="utf-8")
    streamlit_port = _pick_free_port()
    devtools_port = _pick_free_port()
    app_url = f"http://127.0.0.1:{streamlit_port}"
    timeline_root = Path(tempfile.mkdtemp(prefix="financial_path_twin_workflow_demo_stage_"))
    runtime_root = timeline_root / "runtime"
    profile_dir = Path(tempfile.mkdtemp(prefix="financial_path_twin_edge_capture_"))
    destination = SCREEN_DIR / filename
    protected_paths = {
        "default_workflow": PROJECT_ROOT / "artifacts" / "workflow",
        "default_audit": PROJECT_ROOT / "artifacts" / "audit",
        "workspace_workflow_demo": PROJECT_ROOT / "artifacts" / "workflow_demo",
    }
    protected_before = {name: _tree_digest(path) for name, path in protected_paths.items()}
    environment = os.environ.copy()
    environment.update(
        {
            "FPT_PROJECT_ROOT": str(PROJECT_ROOT),
            "FPT_CAPTURE_MODE": APP_MODE_RM,
            "FPT_CAPTURE_LANGUAGE": "ko",
            "FPT_CAPTURE_WORKFLOW_DEMO_RUNTIME_ROOT": str(runtime_root),
            "FPT_CAPTURE_WORKFLOW_DEMO_FIXTURE_PATH": str(fixture_path),
            "FPT_CAPTURE_WORKFLOW_DEMO_STAGE": stage,
        }
    )
    streamlit_process: subprocess.Popen[str] | None = None
    edge_process: subprocess.Popen[bytes] | None = None
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        streamlit_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(wrapper_path),
                "--server.headless=true",
                f"--server.port={streamlit_port}",
                "--server.address=127.0.0.1",
                "--browser.gatherUsageStats=false",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=creation_flags,
        )
        _wait_for_streamlit(streamlit_port)
        edge_process = subprocess.Popen(
            [
                str(edge),
                "--new-window",
                "--disable-crash-reporter",
                "--noerrdialogs",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={devtools_port}",
                "--remote-allow-origins=http://localhost",
                "--window-position=30,30",
                "--window-size=1440,1500",
                app_url,
            ],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        websocket_url = _edge_page_websocket(devtools_port, app_url)
        connection = websocket.create_connection(websocket_url, timeout=12, origin="http://localhost")
        try:
            command_id = 1
            _cdp_command(connection, command_id, "Page.enable")
            command_id += 1
            _cdp_command(connection, command_id, "Page.bringToFront")
            command_id += 1
            time.sleep(8)
            command_id = _wait_for_rendered_text(
                connection,
                command_id,
                expected_text="Workflow Demo",
            )
            focus_by_stage = {
                "entry": "Workflow Demo",
                "new": "RM Action",
                "acknowledged": "Activity / Audit",
                "preview": "알림 미리보기",
            }
            focus = focus_by_stage.get(stage, "Workflow Demo")
            focus_script = f"""(() => {{
                const targetText = {json.dumps(focus, ensure_ascii=False)};
                const candidates = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,p,span,div,summary'));
                const exact = candidates.filter((item) => (item.innerText || '').trim() === targetText);
                const partial = candidates.filter((item) => (item.innerText || '').includes(targetText));
                const target = (exact.length ? exact : partial).sort(
                    (left, right) => (left.innerText || '').length - (right.innerText || '').length
                )[0];
                if (!target) return 'missing-focus:' + targetText;
                target.scrollIntoView({{block: 'start', behavior: 'instant'}});
                return 'focused:' + targetText;
            }})()"""
            result = _cdp_command(
                connection,
                command_id,
                "Runtime.evaluate",
                {"expression": focus_script, "returnByValue": True},
            )
            _assert_cdp_interaction(result)
            command_id += 1
            time.sleep(2)
            _capture_cdp_viewport(connection, command_id, destination)
        finally:
            connection.close()
        if not destination.is_file() or destination.stat().st_size < 1024:
            raise RuntimeError(f"Edge stage {stage!r} did not create a usable screenshot.")

        protected_after = {name: _tree_digest(path) for name, path in protected_paths.items()}
        if protected_before != protected_after:
            changed = sorted(
                name
                for name in protected_before
                if protected_before[name] != protected_after[name]
            )
            raise RuntimeError(
                "Workflow Demo capture changed protected workspace artifacts: " + ", ".join(changed)
            )
        return destination
    finally:
        for process in (edge_process, streamlit_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        wrapper_path.unlink(missing_ok=True)
        shutil.rmtree(profile_dir, ignore_errors=True)
        shutil.rmtree(timeline_root, ignore_errors=True)


def capture_workflow_demo_timeline_with_edge() -> dict[str, Path]:
    """Capture four real Edge-rendered teaching states without touching workspace data."""

    stages = (
        ("workflow_demo_entry", "entry", "12_workflow_demo_entry_uninitialized.png"),
        ("workflow_demo_new", "new", "13_workflow_demo_new_before_action.png"),
        ("workflow_demo_ack", "acknowledged", "14_workflow_demo_ack_after_action.png"),
        ("workflow_demo_preview", "preview", "16_workflow_demo_preview_not_sent.png"),
    )
    return {
        key: _capture_workflow_demo_stage_with_edge(stage=stage, filename=filename)
        for key, stage, filename in stages
    }


def capture_screens_with_edge() -> dict[str, Path]:
    """Capture the three primary modes from actual Edge-rendered app sessions."""

    return {
        "presentation": _capture_one_edge_screen(mode=APP_MODE_PRESENTATION, filename="01_presentation_mode.png"),
        "general": _capture_one_edge_screen(mode=APP_MODE_GENERAL, filename="02_general_mode.png"),
        "rm": _capture_one_edge_screen(mode=APP_MODE_RM, filename="03_rm_portfolio.png"),
    }


# DOM interactions below are deliberately index-based instead of depending on
# Korean/English display text.  They only choose a rendered Streamlit tab or a
# session-local comparison value in a short-lived Edge capture session.
_CLICK_PRESENTATION_LANDMARK_TAB = """(() => {
    const tabs = Array.from(document.querySelectorAll('[role=\"tab\"]'));
    if (!tabs[2]) return 'missing-presentation-landmark-tab';
    tabs[2].click(); return 'presentation-landmark';
})()"""
_CLICK_PRESENTATION_WHATIF_TAB = """(() => {
    const tabs = Array.from(document.querySelectorAll('[role=\"tab\"]'));
    if (!tabs[3]) return 'missing-presentation-whatif-tab';
    tabs[3].click(); return 'presentation-whatif';
})()"""
_CLICK_RM_QUEUE_TAB = """(() => {
    const tabs = Array.from(document.querySelectorAll('[role=\"tab\"]'));
    if (!tabs[1]) return 'missing-rm-queue-tab';
    tabs[1].click(); return 'rm-queue';
})()"""
_CLICK_RM_CUSTOMER_REVIEW_TAB = """(() => {
    const tabs = Array.from(document.querySelectorAll('[role=\"tab\"]'));
    if (!tabs[2]) return 'missing-rm-customer-review-tab';
    tabs[2].click(); return 'rm-customer-review';
})()"""
_ENABLE_RM_CAPACITY_COMPARISON = """(() => {
    const checkboxes = Array.from(document.querySelectorAll('input[type=\"checkbox\"]'));
    const checkbox = checkboxes.find((item) => !item.checked) || checkboxes[0];
    if (!checkbox) return 'missing-rm-capacity-checkbox';
    if (!checkbox.checked) checkbox.click();
    return 'rm-capacity-enabled';
})()"""
_SET_RM_CAPACITY_TO_THREE = """(() => {
    const input = Array.from(document.querySelectorAll('input[type=\"number\"]'))[0];
    if (!input) return 'missing-rm-capacity-input';
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, '3');
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
    input.blur();
    return 'rm-capacity-3';
})()"""
_SCROLL_TO_RM_CAPACITY_COMPARISON = """(() => {
    const target = document.querySelector('[data-testid=\"stNumberInput\"]') ||
        document.querySelector('[data-testid=\"stCheckbox\"]');
    if (!target) return 'missing-rm-capacity-control';
    target.scrollIntoView({block: 'start', behavior: 'instant'});
    return 'rm-capacity-scrolled';
})()"""
_SCROLL_TO_RM_WORKFLOW_DEMO_CTA = """(() => {
    const target = Array.from(document.querySelectorAll('button')).find((item) =>
        (item.innerText || '').includes('Workflow Demo')
    );
    if (!target) return 'missing-rm-workflow-demo-cta';
    target.scrollIntoView({block: 'center', behavior: 'instant'});
    return 'rm-workflow-demo-cta-scrolled';
})()"""


EDGE_SCENARIOS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "presentation": (APP_MODE_PRESENTATION, "01_presentation_mode.png", ()),
    "general": (APP_MODE_GENERAL, "02_general_mode.png", ()),
    "general_direct_c000001": (APP_MODE_GENERAL, "02a_general_direct_c000001.png", ()),
    "rm": (APP_MODE_RM, "03_rm_portfolio.png", ()),
    "presentation_landmark": (
        APP_MODE_PRESENTATION,
        "04_presentation_historical_landmark.png",
        (_CLICK_PRESENTATION_LANDMARK_TAB,),
    ),
    "presentation_whatif": (
        APP_MODE_PRESENTATION,
        "05_presentation_whatif.png",
        (_CLICK_PRESENTATION_WHATIF_TAB,),
    ),
    "rm_capacity_3": (
        APP_MODE_RM,
        "06_rm_human_capacity_3.png",
        (_SCROLL_TO_RM_CAPACITY_COMPARISON,),
    ),
    "rm_workflow_demo_entry_cta": (
        APP_MODE_RM,
        "11a_rm_workflow_demo_entry_cta.png",
        (_SCROLL_TO_RM_WORKFLOW_DEMO_CTA,),
    ),
    "rm_queue": (
        APP_MODE_RM,
        "07_rm_review_queue.png",
        (_CLICK_RM_QUEUE_TAB,),
    ),
    "rm_customer_review": (
        APP_MODE_RM,
        "08_rm_customer_review_c000001.png",
        (_CLICK_RM_CUSTOMER_REVIEW_TAB,),
    ),
    "presentation_c002082_insufficient": (
        APP_MODE_PRESENTATION,
        "09_presentation_c002082_landmark_insufficient.png",
        (_CLICK_PRESENTATION_LANDMARK_TAB,),
    ),
    "rm_monitor_c000003": (
        APP_MODE_RM,
        "10_rm_monitor_c000003.png",
        (_CLICK_RM_CUSTOMER_REVIEW_TAB,),
    ),
    "rm_queue_c000003_excluded": (
        APP_MODE_RM,
        "11_rm_queue_c000003_excluded.png",
        (_CLICK_RM_QUEUE_TAB,),
    ),
}
EDGE_SCENARIO_SESSION_CAPACITY = {"rm_capacity_3": 3}
EDGE_SCENARIO_SESSION_CUSTOMER = {
    "presentation_c002082_insufficient": "C002082",
    "rm_monitor_c000003": "C000003",
}
EDGE_SCENARIO_DIRECT_INPUT_CUSTOMER = {
    "general_direct_c000001": "C000001",
}
EDGE_SCENARIO_PRESENTATION_OPTION = {
    "presentation_c002082_insufficient": "demo:1:C002082",
}
EDGE_SCENARIO_REPRESENTATIVE_CATEGORY = {
    "rm_monitor_c000003": "monitor_no_alert_comparison",
}
EDGE_SCENARIO_QUEUE_SEARCH = {
    "rm_queue_c000003_excluded": "C000003",
}


def capture_evidence_screens_with_edge() -> dict[str, Path]:
    """Capture the bounded evidence gallery used by the detailed manual."""

    captured: dict[str, Path] = {}
    for scenario, (mode, filename, interaction_scripts) in EDGE_SCENARIOS.items():
        try:
            captured[scenario] = _capture_one_edge_screen(
                mode=mode,
                filename=filename,
                interaction_scripts=interaction_scripts,
                session_capacity=EDGE_SCENARIO_SESSION_CAPACITY.get(scenario),
                session_customer_id=EDGE_SCENARIO_SESSION_CUSTOMER.get(scenario),
                session_direct_input_customer_id=EDGE_SCENARIO_DIRECT_INPUT_CUSTOMER.get(scenario),
                session_presentation_option=EDGE_SCENARIO_PRESENTATION_OPTION.get(scenario),
                session_representative_category=EDGE_SCENARIO_REPRESENTATIVE_CATEGORY.get(scenario),
                session_queue_search=EDGE_SCENARIO_QUEUE_SEARCH.get(scenario),
            )
        except (OSError, RuntimeError, subprocess.SubprocessError, websocket.WebSocketException) as error:
            # An optional scenario must not prevent the already-captured current
            # screens from being used in the manual.  The Word captions make a
            # visual's source clear, rather than fabricating a failed screen.
            print(f"WARNING: Edge scenario {scenario!r} was skipped: {error}")
    return captured


def _set_cell(cell, *, bold: bool = False, fill: str | None = None, color: str = "1A2733") -> None:
    cell.font = Font(name="Malgun Gothic", size=10, bold=bold, color=color)
    cell.alignment = Alignment(vertical="top", wrap_text=True)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.border = Border(
        left=Side(style="thin", color=LINE),
        right=Side(style="thin", color=LINE),
        top=Side(style="thin", color=LINE),
        bottom=Side(style="thin", color=LINE),
    )


def _write_sheet_table(sheet, headers: Iterable[str], rows: Iterable[Iterable[str]], *, widths: tuple[int, ...]) -> None:
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column, value=header)
        _set_cell(cell, bold=True, fill=NAVY, color="FFFFFF")
        sheet.column_dimensions[get_column_letter(column)].width = widths[column - 1]
    for row_index, row_values in enumerate(rows, start=2):
        for column, value in enumerate(row_values, start=1):
            cell = sheet.cell(row=row_index, column=column, value=value)
            _set_cell(cell, fill="FFFFFF" if row_index % 2 == 0 else LIGHT)
        sheet.row_dimensions[row_index].height = 42
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False


def create_workbook(
    diagrams: dict[str, Path],
    capture_cards: dict[str, Path],
    annotations: dict[str, Path],
    screens: dict[str, Path],
    *,
    git_head: str,
    dirty: bool,
) -> Path:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "시작_한눈에"
    summary.sheet_view.showGridLines = False
    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 70
    summary.column_dimensions["C"].width = 26
    summary.merge_cells("A1:C1")
    title_cell = summary["A1"]
    title_cell.value = "Financial Path Twin 운영 요약"
    title_cell.font = Font(name="Malgun Gothic", size=20, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill("solid", fgColor=NAVY)
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    summary.row_dimensions[1].height = 38
    summary.merge_cells("A2:C2")
    summary["A2"] = (
        f"기준 커밋: {git_head} / 현재 로컬 Post-P0 보강: {'있음' if dirty else '없음'} / "
        "모든 숫자와 고객 ID는 합성 데이터 데모 기준"
    )
    _set_cell(summary["A2"], fill="EAF2FB", color=NAVY)
    summary.row_dimensions[2].height = 34
    summary["A4"] = "무엇을 고를까?"
    _set_cell(summary["A4"], bold=True, fill=TEAL, color="FFFFFF")
    for cell, value in zip((summary["A5"], summary["B5"], summary["C5"]), ("모드", "언제 사용하는가", "첫 샘플")):
        cell.value = value
        _set_cell(cell, bold=True, fill=NAVY, color="FFFFFF")
    summary_rows = (
        ("일반 모드", "분석 검토·질의응답. 고객/지표를 바꾸며 세로 흐름으로 읽습니다.", "C002082 또는 C002672"),
        ("발표 모드", "심사·발표. 한 고객의 5단계 스토리를 짧고 일관되게 보여줍니다.", "C002608"),
        ("RM 업무 모드", "5,000명 → 후보 → selected queue → evidence/action 흐름을 설명합니다.", "C000001"),
    )
    for row_index, values in enumerate(summary_rows, start=6):
        for column, value in enumerate(values, start=1):
            summary.cell(row=row_index, column=column, value=value)
            _set_cell(summary.cell(row=row_index, column=column), fill="FFFFFF" if row_index % 2 == 0 else LIGHT)
        summary.row_dimensions[row_index].height = 45
    diagram = SpreadsheetImage(str(diagrams["modes"]))
    diagram.width, diagram.height = 760, 401
    summary.add_image(diagram, "A11")

    samples = workbook.create_sheet("발표_샘플")
    _write_sheet_table(
        samples,
        ("시간", "화면 / 고객", "말할 핵심", "말하면 안 되는 것"),
        (
            ("0:00–0:20", "RM Portfolio", "5,000명의 전체 funnel과 exact reconciliation", "1,522명을 실제 일일 업무량으로 표현"),
            ("0:20–0:40", "Capacity 비교 / 3", "사람이 입력한 draft scenario: 3 selected, 1,519 deferred", "시스템이 적정 capacity를 승인한다고 표현"),
            ("0:40–1:10", "C000001 / Customer Review", "왜 선정됐는지, 왜 지금 검토하는지, 근거 출처", "historical landmark를 미래 예정일로 표현"),
            ("1:10–1:30", "C000007 / C000003", "Review·Monitor 비교와 no-cherry-picking", "Monitor를 운영 queue로 표현"),
            ("1:30–2:00", "발표 모드 / C002608", "5 tabs로 Digital Twin 분석을 연결", "historical outcome share를 확률·정확도로 표현"),
        ),
        widths=(16, 28, 52, 52),
    )
    storyboard = SpreadsheetImage(str(diagrams["storyboard"]))
    storyboard.width, storyboard.height = 850, 492
    samples.add_image(storyboard, "A9")

    procedures = workbook.create_sheet("운영_절차")
    _write_sheet_table(
        procedures,
        ("모드", "목적", "기본 절차", "확인할 점"),
        (
            ("일반 모드", "분석 검토", "왼쪽 모드 선택 → demo/customer 선택 → 지표 선택 → 세로 분석 흐름 확인", "고객 변경 뒤 이전 cache 결과가 섞이지 않는지 확인"),
            ("발표 모드", "발표 스토리", "발표 모드 → C002608 → 현재 상태/유사 경로/분기 근거/대응/요약 순서", "landmark caption과 합성 데이터 notice를 유지"),
            ("RM 업무 모드", "운영 후보 검토", "Portfolio → Queue → Customer Review → Activity/Audit", "Queue는 selected/routed only; Monitor/Insufficient은 비교 사례"),
            ("Capacity 비교", "사람 판단용 workload 비교", "Portfolio에서 opt-in → capacity 입력 → selected/deferred 비교", "draft comparison이며 triage/alert 원본을 변경하지 않음"),
        ),
        widths=(20, 24, 54, 54),
    )

    general_inputs = workbook.create_sheet("일반_입력예시")
    general_inputs.sheet_view.showGridLines = False
    _write_sheet_table(
        general_inputs,
        ("입력", "권장값 / 의미"),
        (
            ("화면 모드", "일반 모드 — 상세 검토와 Q&A에 사용"),
            ("고객 선택", "C002608 메인 / C002082 안정·근거부족 대비 / C002672 고위험 시각 대비"),
            ("직접 고객 ID", "드롭다운에서 직접 입력을 선택한 뒤 synthetic dataset에 존재하는 ID만 입력"),
            ("표시 지표", "저축률을 기본으로 보고, 질문에 따라 DSR·고정지출 비중으로 변경"),
            ("세부 궤적 표시", "Q&A에서만 켜고, 기본 발표에서는 숨김"),
        ),
        widths=(28, 90),
    )
    annotated = annotations.get("general_inputs", annotations["sample_map"])
    annotated_image = SpreadsheetImage(str(annotated))
    annotated_image.width, annotated_image.height = 850, 580
    general_inputs.add_image(annotated_image, "A9")

    terminology = workbook.create_sheet("용어_주의")
    _write_sheet_table(
        terminology,
        ("표현", "의미", "안전한 사용법"),
        (
            ("Historical outcome share", "유사 과거 cohort의 이후 결과 비율", "prediction probability가 아니라 historical cohort evidence라고 설명"),
            ("Historical landmark", "유사 과거 cohort 경로가 갈린 retrospective 지점", "현재 고객이 그 달에 위험해진다는 예정일로 쓰지 않음"),
            ("Why Now", "현재/과거 관측 기반 prospective signal과 policy evidence", "미래 final_outcome/persona를 읽지 않는 근거라고 설명"),
            ("What-if", "rule-based cashflow simulation", "개입 효과·자동 조치 보장으로 해석하지 않음"),
            ("Notification Preview", "발송하지 않는 offline preview", "sent/외부 전달/SLA 충족이라고 주장하지 않음"),
            ("Real-data readiness", "governance·adapter·metric 계약 준비", "실제 익명화 데이터 검증 완료로 표현하지 않음"),
        ),
        widths=(26, 50, 60),
    )

    screens_sheet = workbook.create_sheet("화면_미리보기")
    screens_sheet.sheet_view.showGridLines = False
    screens_sheet.column_dimensions["A"].width = 28
    screens_sheet.column_dimensions["B"].width = 25
    screens_sheet["A1"] = "현재 화면 캡처"
    _set_cell(screens_sheet["A1"], bold=True, fill=NAVY, color="FFFFFF")
    image_rows = (("발표 모드", "presentation"), ("일반 모드", "general"), ("RM Portfolio", "rm"))
    row = 3
    for label, key in image_rows:
        is_live_screen = key in screens
        screens_sheet.cell(
            row=row,
            column=1,
            value=label if is_live_screen else f"{label} — 수동 화면 캡처 가이드 (실제 화면 아님)",
        )
        _set_cell(screens_sheet.cell(row=row, column=1), bold=True, fill="EAF2FB", color=NAVY)
        image_path = screens.get(key, capture_cards[key])
        screenshot = SpreadsheetImage(str(image_path))
        screenshot.width, screenshot.height = 620, 646
        screens_sheet.add_image(screenshot, f"A{row + 1}")
        row += 37

    evidence = workbook.create_sheet("현황_근거")
    _write_sheet_table(
        evidence,
        ("상태", "현재 근거", "발표에서 말할 방식", "말하면 안 되는 방식"),
        (
            (
                "현재 증명됨",
                "합성 5,000명 전수 분석·triage·다중 고객 Queue·RM workflow prototype·leakage/circularity regression",
                "‘합성 PoC에서 재현된 기능입니다.’",
                "‘실제 은행 정확도·성과를 증명했습니다.’",
            ),
            (
                "사람의 판단 필요",
                "capacity 입력 비교·draft policy·RM follow-up 기록",
                "‘시스템은 근거와 trade-off를 보여주고 최종 판단은 사람이 합니다.’",
                "‘시스템이 적정 업무량을 승인합니다.’",
            ),
            (
                "현재 open",
                "실제 익명화 데이터 검증·실제 RM pilot·외부 전송/SLA·DB 연동",
                "‘검증을 위한 governance·adapter·metric 계약은 준비했습니다.’",
                "‘실제 고객 데이터로 검증되었습니다.’",
            ),
        ),
        widths=(22, 58, 45, 45),
    )
    evidence_image = SpreadsheetImage(str(diagrams["evidence_status"]))
    evidence_image.width, evidence_image.height = 850, 517
    evidence.add_image(evidence_image, "A7")
    capacity_image = SpreadsheetImage(str(diagrams["capacity_example"]))
    capacity_image.width, capacity_image.height = 850, 403
    evidence.add_image(capacity_image, "A36")

    preparation = workbook.create_sheet("RM_사전준비")
    _write_sheet_table(
        preparation,
        ("순서", "주체", "해야 할 일", "현재 상태 / 주의"),
        (
            ("1", "데모 운영자", "01_install → 02_run_pipeline → 03_run_app", "기존 분석 파이프라인만 실행. triage/Case를 새로 만들지 않음"),
            ("2", "분석 담당자", "5,000 exact reconciliation과 policy/version/provenance 확인", "5,000 = 1,522 selected + 371 monitor + 3,107 no actionable"),
            ("3", "업무 책임자", "capacity를 사람 입력으로 비교", "draft comparison. 시스템이 적정 N·SLA를 승인하지 않음"),
            ("4", "발표자", "Portfolio → Queue → Customer Review로 근거 설명", "Monitor/NoSignal은 operational queue 밖의 비교 사례"),
            ("5", "RM", "승인된 실제 Case 범위에서 review/action 기록", "기본 앱은 open Case 0이 정상. synthetic dry-run과 구분"),
            ("6", "Data owner·Security·Privacy", "실제 데이터/pilot 전에 승인 경로 결정", "not requested / not initiated. 실제 데이터는 저장소로 반입하지 않음"),
        ),
        widths=(10, 25, 55, 58),
    )
    preparation_image = SpreadsheetImage(str(diagrams["rm_preparation"]))
    preparation_image.width, preparation_image.height = 850, 528
    preparation.add_image(preparation_image, "A10")

    feedback = workbook.create_sheet("피드백_대응")
    _write_sheet_table(
        feedback,
        ("평가 피드백", "지금 보여줄 화면·근거", "정직한 한계", "발표 답변"),
        (
            (
                "합성 데이터·단일 고객",
                "RM Portfolio 5,000 funnel, Queue 1,522, C000001/C000007/C000003 deterministic representative 비교",
                "실제 익명화 데이터 검증은 open",
                "‘전수 synthetic PoC는 완료했으며, 실제 데이터 검증은 승인 환경의 다음 단계입니다.’",
            ),
            (
                "앱 비중 확대",
                "Portfolio → capacity → Customer Review → Presentation 5 tabs의 실제 화면",
                "영상 녹화/편집/리허설은 사람이 완료할 발표 작업",
                "‘슬라이드가 아니라 앱에서 evidence를 먼저 보여드립니다.’",
            ),
            (
                "Banker Workflow",
                "Policy → Triage → Alert/Case → RM action → audit → Preview/Null",
                "실제 RM 성과·외부 전송·SLA·자동 금융결정은 없음",
                "‘RM이 판단할 근거와 기록 가능한 workflow prototype입니다.’",
            ),
            (
                "언제 행동할 것인가",
                "Why Now와 historical landmark를 별도 화면/모델로 분리",
                "개별 고객의 미래 발생월/확률은 주장하지 않음",
                "‘Why Now는 현재·과거 관측 신호, landmark는 유사 과거 cohort의 맥락입니다.’",
            ),
        ),
        widths=(28, 58, 43, 53),
    )
    feedback_image = SpreadsheetImage(str(diagrams["feedback_response"]))
    feedback_image.width, feedback_image.height = 850, 502
    feedback.add_image(feedback_image, "A9")

    rehearsal = workbook.create_sheet("발표_리허설")
    _write_sheet_table(
        rehearsal,
        ("시간", "화면/샘플", "보여줄 evidence", "권장 멘트", "피해야 할 표현"),
        (
            ("0:00–0:20", "RM Portfolio", "5,000 → 1,522 → 371 → 3,107 exact funnel", "‘한 고객이 아니라 전체 synthetic population에서 시작합니다.’", "‘1,522명이 실제 업무량입니다.’"),
            ("0:20–0:40", "capacity=3 비교", "3 selected / 1,519 deferred", "‘사람이 capacity를 넣어 trade-off를 비교합니다.’", "‘시스템이 3명을 추천했습니다.’"),
            ("0:40–1:05", "C000001 Customer Review", "선정 이유·Why Now·current signal·provenance", "‘왜 이 고객이며 왜 지금 검토하는지의 근거입니다.’", "‘13개월차에 위험합니다.’"),
            ("1:05–1:20", "C000007 / C000003", "Review와 Monitor의 다중 고객 비교", "‘대표 사례는 no-cherry-picking rule로 정했습니다.’", "‘Monitor도 queue에 있습니다.’"),
            ("1:20–1:45", "C002608 Presentation", "historical cohort / landmark / What-if", "‘landmark는 과거 맥락, What-if는 규칙 기반 가정입니다.’", "‘위험확률 또는 개입효과입니다.’"),
            ("1:45–2:00", "Open boundary", "governance/adapter/metric/pilot protocol", "‘준비했지만 실제 검증 완료는 아닙니다.’", "‘실제 은행 고객에 적용했습니다.’"),
        ),
        widths=(16, 30, 48, 52, 45),
    )
    rehearsal_storyboard = SpreadsheetImage(str(diagrams["storyboard"]))
    rehearsal_storyboard.width, rehearsal_storyboard.height = 850, 492
    rehearsal.add_image(rehearsal_storyboard, "A10")

    gallery = workbook.create_sheet("화면_갤러리")
    gallery.sheet_view.showGridLines = False
    gallery.column_dimensions["A"].width = 28
    gallery["A1"] = "현재 로컬 Edge 증거 화면"
    _set_cell(gallery["A1"], bold=True, fill=NAVY, color="FFFFFF")
    gallery_rows = (
        ("Presentation · historical landmark", "presentation_landmark"),
        ("Presentation · What-if", "presentation_whatif"),
        ("RM · Human-entered capacity = 3", "rm_capacity_3"),
        ("RM · Review Queue", "rm_queue"),
        ("RM · Customer Review C000001", "rm_customer_review"),
        ("FAQ · C002082 landmark evidence insufficient", "presentation_c002082_insufficient"),
        ("FAQ · C000003 Monitor comparison", "rm_monitor_c000003"),
        ("FAQ · Queue search C000003 = 0 rows", "rm_queue_c000003_excluded"),
    )
    gallery_row = 3
    for label, key in gallery_rows:
        image_path = screens.get(key)
        if image_path is None or not image_path.exists():
            continue
        gallery.cell(row=gallery_row, column=1, value=label)
        _set_cell(gallery.cell(row=gallery_row, column=1), bold=True, fill="EAF2FB", color=NAVY)
        image = SpreadsheetImage(str(image_path))
        image.width, image.height = 760, 518
        gallery.add_image(image, f"A{gallery_row + 1}")
        gallery_row += 34

    alert_case = workbook.create_sheet("Alert_Case_안내")
    _write_sheet_table(
        alert_case,
        ("기본 RM 화면 표시", "정확한 의미", "정상인가?", "사용자 행동"),
        (
            (
                "열린 Alert 없음",
                "기본 workflow repository에 생성된 Case가 0개",
                "정상",
                "선정 근거·Why Now를 검토. Alert가 전달됐다고 말하지 않음",
            ),
            (
                "RM 업무 큐 Case 0",
                "기본 앱은 read-only이며 Case fixture를 자동 생성하지 않음",
                "정상",
                "UI로 파일을 직접 만들거나 action을 억지로 실행하지 않음",
            ),
            (
                "선정됨 · Case 미생성",
                "Triage에서 검토 대상으로 선정됐지만 Alert cycle은 실행되지 않음",
                "정상",
                "‘선정’과 ‘실제 Case’를 분리해 설명",
            ),
            (
                "Case 생성 대기 1,522",
                "unbounded demo 후보 집합. 실제 업무량/Alert 수가 아님",
                "정상",
                "사람 입력 capacity로 Selected/Deferred 비교만 수행",
            ),
        ),
        widths=(28, 55, 14, 55),
    )
    status_image = annotations.get("rm_alert_case_status")
    if status_image is not None and status_image.exists():
        image = SpreadsheetImage(str(status_image))
        image.width, image.height = 850, 530
        alert_case.add_image(image, "A8")
    workflow_image = SpreadsheetImage(str(diagrams["default_vs_rehearsal"]))
    workflow_image.width, workflow_image.height = 850, 483
    alert_case.add_image(workflow_image, "A43")
    alert_case["A76"] = "발표자 30초 순서: ① Alert 0/Case 0은 정상이라고 설명 → ② Queue·Customer Review로 선정 이유/Why Now 제시 → ③ Action/Audit은 격리 synthetic rehearsal(3 Cases/10 Audit events) 증거로만 설명"
    _set_cell(alert_case["A76"], bold=True, fill="EAF2FB", color=NAVY)
    alert_case.merge_cells("A76:D77")

    faq_sheet = workbook.create_sheet("상태별_FAQ")
    _write_sheet_table(
        faq_sheet,
        ("질문", "즉시 답", "화면·artifact 근거", "의미하지 않는 것", "발표 20초 답", "다음 확인"),
        (
            (
                "C002082의 landmark 근거 부족은 5,000명이 부족한가?",
                "아니오. 200명 매칭은 성공했지만 과거 risk-path=0명 / avoidance=200명이라 양쪽 최소 20명 비교 기준을 만족하지 못했습니다.",
                "Presentation ③ · breakpoint_status=insufficient_group_size · analysis_status=success",
                "현재 고객이 안전함, 전체 population 분석 실패, 미래 위험 날짜 예측",
                "‘매칭은 됐지만 비교 집단이 없어 landmark를 억지로 만들지 않았습니다.’",
                "C002082의 분석 제한·비교 제한·historical caption",
            ),
            (
                "C000003 Monitor는 왜 운영 Review Queue 밖인가?",
                "Monitor는 관찰 신호가 있다는 뜻이지만 이 run의 triage는 Queue 포함 대상으로 정하지 않았습니다.",
                "MONITOR_ONLY · NOT_QUEUE_ELIGIBLE · NO_ROUTING · selected_for_review=false",
                "Monitor=신호 없음, Monitor=운영 Queue 행, 모든 signal=Alert",
                "‘정책 신호와 triage selection은 다르므로 대표 비교 사례로만 봅니다.’",
                "Customer Review의 대표 비교 사례와 Queue 검색 0건",
            ),
            (
                "Capacity=3이면 왜 1,519명이 Deferred인가?",
                "사람 입력 draft 비교값 3에 따라 저장 순위 앞 3명만 비교상 Selected입니다.",
                "eligible 1,522 = selected 3 + deferred 1,519 · saved rank prefix cutoff only",
                "거절·누락·실제 SLA·자동 Case 생성",
                "‘시스템 추천이 아니라 사람이 바꿔 보는 workload trade-off입니다.’",
                "unbounded 기준과 입력 용량 3 표의 status=draft",
            ),
            (
                "Alert / Case가 왜 0개인가?",
                "기본 workflow repository에 Case fixture가 없고, Triage 선정과 Case 생성은 분리되어 있습니다.",
                "open Alert=0 · RM Queue Case=0 · Case pending=1,522 · rehearsal=3 Cases/10 audit/network=false",
                "분석 실패, 이미 외부 발송, UI의 숨은 Case 생성 작업",
                "‘기본은 읽기 전용이며 Action/Audit은 격리 합성 rehearsal 증거로만 말합니다.’",
                "18~19장과 Alert_Case_안내 시트",
            ),
        ),
        widths=(34, 52, 52, 42, 52, 42),
    )
    faq_overview = annotations.get("faq_overview")
    if faq_overview is not None and faq_overview.exists():
        image = SpreadsheetImage(str(faq_overview))
        image.width, image.height = 850, 514
        faq_sheet.add_image(image, "A8")
    faq_row = 46
    for label, key in (
        ("FAQ 1 · C002082 landmark 근거 부족", "faq_landmark"),
        ("FAQ 2 · C000003 Monitor와 Queue 제외", "faq_monitor"),
        ("FAQ 3 · Capacity 3과 Deferred 1,519", "faq_capacity"),
        ("FAQ 4 · Alert / Case 0", "faq_alert_case"),
    ):
        faq_image = annotations.get(key)
        if faq_image is None or not faq_image.exists():
            continue
        faq_sheet.cell(row=faq_row, column=1, value=label)
        _set_cell(faq_sheet.cell(row=faq_row, column=1), bold=True, fill="EAF2FB", color=NAVY)
        image = SpreadsheetImage(str(faq_image))
        image.width, image.height = 850, 548
        faq_sheet.add_image(image, f"A{faq_row + 1}")
        faq_row += 40

    output = OUTPUT_DIR / WORKBOOK_NAME
    workbook.save(output)
    return output


def _cell_shading(cell, color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


def _set_document_defaults(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Malgun Gothic"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    normal.font.size = Pt(10.5)
    for section in document.sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.65)
        section.right_margin = Inches(0.65)


def _add_title(document: Document, text: str, *, subtitle: str | None = None) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.font.name = "Malgun Gothic"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    run.font.size = Pt(27)
    run.font.bold = True
    run.font.color.rgb = RGBColor(23, 50, 77)
    if subtitle:
        subtitle_paragraph = document.add_paragraph()
        subtitle_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle_run = subtitle_paragraph.add_run(subtitle)
        subtitle_run.font.name = "Malgun Gothic"
        subtitle_run._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
        subtitle_run.font.size = Pt(11)
        subtitle_run.font.color.rgb = RGBColor(93, 107, 120)


def _add_callout(document: Document, label: str, body: str, *, color: str = "EAF2FB") -> None:
    table = document.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    _cell_shading(cell, color)
    paragraph = cell.paragraphs[0]
    heading = paragraph.add_run(label + "\n")
    heading.bold = True
    heading.font.color.rgb = RGBColor(23, 50, 77)
    paragraph.add_run(body)
    document.add_paragraph()


def _add_table(document: Document, headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = True
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = header
        _cell_shading(cell, NAVY)
        for run in cell.paragraphs[0].runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
    for row_index, row in enumerate(rows):
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = value
            if row_index % 2:
                _cell_shading(cells[index], "F4F8FC")
    document.add_paragraph()


def _add_picture(document: Document, path: Path, caption: str, *, width: float = 6.9) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(path), width=Inches(width))
    caption_paragraph = document.add_paragraph()
    caption_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption_run = caption_paragraph.add_run(caption)
    caption_run.italic = True
    caption_run.font.size = Pt(9)
    caption_run.font.color.rgb = RGBColor(93, 107, 120)


def create_document(
    diagrams: dict[str, Path],
    capture_cards: dict[str, Path],
    annotations: dict[str, Path],
    screens: dict[str, Path],
    *,
    git_head: str,
    dirty: bool,
    output_path: Path | None = None,
) -> Path:
    document = Document()
    _set_document_defaults(document)
    _add_title(
        document,
        "Financial Path Twin\n운영 사용자 매뉴얼",
        subtitle=(
            f"초심자용 · 합성 데이터 PoC · 기준 커밋 {git_head} · "
            f"로컬 Post-P0 보강 {'포함' if dirty else '없음'} · {date.today().isoformat()}"
        ),
    )
    document.add_paragraph()
    _add_callout(
        document,
        "먼저 알아둘 점",
        "이 앱은 5,000명의 합성 고객으로 검증하는 PoC입니다. 실제 고객 행동 정확도, 실제 RM 업무량, "
        "실제 외부 알림 또는 금융 의사결정을 증명하지 않습니다. 화면은 근거를 보여주고, 최종 판단은 사람이 합니다.",
        color="FFF8E9",
    )

    document.add_heading("1. 이 문서가 답하는 세 가지", level=1)
    document.add_paragraph("① 커밋된 P0 기준과 현재 로컬 Post-P0 보강의 차이  ② 어떤 화면·샘플로 발표할지  ③ 일반/발표/RM 모드를 언제·어떻게 쓸지")
    _add_picture(document, diagrams["modes"], "그림 1. 세 화면 모드는 같은 분석 기반을 목적별로 보여줍니다.")

    document.add_heading("2. 커밋본 대비 현재 로컬에서 좋아진 점", level=1)
    document.add_paragraph(
        "기준 커밋에는 이미 P0의 5,000명 population, triage, Alert/Case, RM Workspace가 들어 있습니다. "
        "현재 로컬은 그 규칙을 바꾸지 않고 평가 피드백에 맞춰 ‘설명 가능성·업무량 경계·실데이터/파일럿 준비도’를 보강했습니다."
    )
    _add_table(
        document,
        ("영역", "기준 커밋(P0)", "현재 로컬(Post-P0)"),
        (
            ("5,000명 → queue", "전체 triage/선정과 RM queue 기본 구조", "선정 사유를 사람 언어로 표시하고 representative/no-cherry-picking 증거를 강화"),
            ("업무량", "unbounded demo selection", "사람 입력 capacity로 Selected/Deferred를 비교. 자동 승인·최적화는 하지 않음"),
            ("Why Now", "prospective timing과 historical landmark의 분리", "copy/source guard를 강화해 둘을 더 명확히 분리"),
            ("Alert/RM", "선정된 triage만 Alert, service/audit/preview", "due-window의 의미와 외부 전달 미구현 한계를 더 명확히 표기"),
            ("실데이터", "합성 데이터 P0 범위", "governance → approved adapter → 사전 정의 metric 계약과 RM pilot protocol 준비 (실검증 미실행)"),
            ("검증·주장", "P0 regression 및 synthetic validation", "feedback coverage, synthetic dry-run, claim/security 문서 보강. 상태: READY_WITH_OPEN_REAL_DATA_VALIDATION"),
        ),
    )
    _add_picture(document, diagrams["flow"], "그림 2. 분석·정책·triage·case·RM action의 책임 경계입니다.")

    document.add_heading("3. 발표에서 사용할 샘플", level=1)
    _add_table(
        document,
        ("역할", "샘플", "무엇을 보여주는가", "주의"),
        (
            ("주 분석 스토리", "C002608", "발표 모드 5 tabs: 200 matches, historical outcome distribution, historical landmark, What-if", "landmark month 13은 유사 과거 cohort의 지점이지 현재 고객의 미래 예정일이 아님"),
            ("안정/근거부족 대비", "C002082", "landmark가 충분한 비교 집단 부족으로 unavailable일 수 있음을 정직하게 보여줌", "부족한 landmark를 억지로 만들거나 숨기지 않음"),
            ("고위험 시각 대비", "C002672", "질의응답에서 시각적 대비", "RM 선정 또는 미래 label의 증거로 사용하지 않음"),
            ("RM Priority 대표", "C000001", "rank 1, Priority Review, 왜 선정/왜 지금", "실제 고객도 실제 업무 우선순위도 아님"),
            ("RM Review 대표", "C000007", "early-signal Review 비교", "Priority와 같은 결과로 뭉뚱그리지 않음"),
            ("RM Monitor 비교", "C000003", "Monitor는 대표 비교 사례이지 operational Review Queue 행이 아님", "selected queue로 위장하지 않음"),
            ("Insufficient", "unavailable", "대표가 없으면 ‘없음’으로 표기하는 no-cherry-picking 규칙", "사례를 임의로 골라 채우지 않음"),
        ),
    )
    _add_picture(document, diagrams["storyboard"], "그림 3. 심사 피드백에 맞춘 앱 중심 2분 시연 순서입니다.")

    document.add_heading("4. 세 화면을 언제 쓰나", level=1)
    _add_table(
        document,
        ("화면", "가장 적합한 상황", "첫 동작", "피해야 할 사용"),
        (
            ("일반 모드", "분석 검토, 질의응답, 특정 고객/지표 확인", "왼쪽에서 일반 모드 → demo 고객/직접 ID → 지표 선택", "공식 발표에서 긴 세로 화면을 처음부터 끝까지 읽기"),
            ("발표 모드", "심사·데모·의사결정자 브리핑", "발표 모드 → C002608 → 5 tabs 순서", "6번째 RM 탭을 추가하거나 일반 모드와 상태를 섞기"),
            ("RM 업무 모드", "5,000명 funnel, selected queue, 근거와 action 흐름 설명", "RM 업무 모드 → Portfolio부터 시작", "Monitor/Insufficient을 operational queue로 보이게 하기"),
        ),
    )

    document.add_heading("5. 시작·사전 점검", level=1)
    document.add_paragraph("일반 사용자 실행 순서는 다음과 같습니다.")
    for command in ("01_install_requirements.bat", "02_run_pipeline.bat", "03_run_app.bat"):
        paragraph = document.add_paragraph(style="List Number")
        run = paragraph.add_run(command)
        run.font.name = "Consolas"
    _add_callout(
        document,
        "발표 직전 5분 점검",
        "① 02_run_pipeline.bat 실행 후 demo/cache artifact가 준비됐는지 확인  ② 03_run_app.bat으로 앱을 열고 C002608 표시 확인  "
        "③ RM Portfolio의 5,000/1,522/371/3,107 funnel과 synthetic notice 확인  ④ 인터넷/외부 알림 없이도 동작함을 확인  "
        "⑤ ‘실데이터 미검증·capacity 미승인’을 발표자 메모에 남깁니다.",
    )

    document.add_heading("6. 일반 모드 사용법", level=1)
    document.add_paragraph("목적: 분석을 깊게 확인하고 질의에 답하는 화면입니다. 발표 모드의 대체재가 아니라 분석 검토용입니다.")
    document.add_paragraph("1) 왼쪽 ‘화면 모드’에서 일반 모드를 선택합니다.\n2) demo 고객을 선택하거나 직접 고객 ID를 입력합니다.\n3) 지표를 바꿔 현재 상태·유사 경로·landmark·What-if의 세로 흐름을 확인합니다.\n4) 필요할 때만 raw sample을 켭니다.\n5) 고객을 바꾼 뒤에는 이전 고객 분석 결과가 남아 보이지 않는지 확인합니다.")
    general_visual = screens.get("general", capture_cards["general"])
    _add_picture(
        document,
        general_visual,
        "화면 1. 일반 모드의 실제 초기 화면 캡처 (합성 데이터)."
        if "general" in screens
        else "화면 1. 실제 화면을 추가할 때의 수동 캡처 가이드 — 이 그림 자체는 live 화면이 아닙니다.",
        width=6.85,
    )
    if "general_inputs" in annotations:
        _add_picture(
            document,
            annotations["general_inputs"],
            "화면 1-1. 실제 일반 모드 화면 위에 입력 순서를 표시한 안내 이미지입니다.",
            width=6.85,
        )
    _add_table(
        document,
        ("입력", "샘플", "사용 시점"),
        (
            ("고객 선택", "C002608", "기본 분석·발표 연결"),
            ("고객 선택", "C002082", "안정/근거 부족을 정직하게 설명하는 Q&A"),
            ("고객 선택", "C002672", "고위험 시각 대비 Q&A. RM 선정 근거로 사용하지 않음"),
            ("직접 고객 ID", "예: C002608", "드롭다운의 ‘직접 입력’을 먼저 선택. 존재하지 않는 ID나 실제 고객 정보는 입력하지 않음"),
            ("표시 지표", "저축률 → DSR → 고정지출 비중", "저축 여력, 상환부담, 반복지출을 차례로 설명할 때"),
        ),
    )
    _add_picture(document, annotations["sample_map"], "그림 4. 일반 모드에서 안전하게 쓸 수 있는 합성 고객 샘플의 역할입니다.")

    document.add_page_break()
    document.add_heading("6.1 C000001 직접 입력부터 RM 검토까지: 그림으로 따라 하는 실습", level=2)
    document.add_paragraph(
        "이 실습은 일반 모드의 상세 분석과 RM 업무 모드의 선정 근거를 연결해 이해하기 위한 것입니다. "
        "일반 모드에서 C000001을 입력하거나 분석을 실행해도 RM 선정, Queue, Alert/Case는 새로 만들어지거나 바뀌지 않습니다."
    )
    _add_table(
        document,
        ("순서", "클릭 / 입력", "값", "화면에서 확인할 것과 변경 범위"),
        (
            ("1", "화면 모드", "일반 모드", "왼쪽 sidebar가 고객·지표 입력 화면으로 바뀜. 저장 원본은 바뀌지 않음."),
            ("2", "고객 선택", "직접 입력", "고객 ID 입력칸이 나타남. 저장 원본은 바뀌지 않음."),
            ("3", "고객 ID", "C000001", "이전 고객의 화면 분석 캐시가 비워지고 C000001 현재 상태를 읽을 준비. 분석 artifact는 바뀌지 않음."),
            ("4", "표시 지표 + 유사 고객 찾기", "저축률 + 버튼 클릭", "유사 과거 cohort, historical outcome, landmark 결과와 근거 충분성 상태를 확인. 세션 분석 결과만 준비됨."),
            ("5", "화면 모드", "RM 업무 모드", "RM Portfolio의 5,000명 funnel로 전환. 일반 모드 고객 입력과 Queue 상태는 독립."),
            ("6", "Review Queue", "C000001 검색 후 행 선택", "Customer Review에서 선정 이유와 Why Now를 확인. 고객 검토 문맥만 선택됨."),
        ),
    )
    _add_callout(
        document,
        "한 문장으로 설명하기",
        "C000001을 일반 모드에 입력하는 것은 분석을 자세히 읽기 위한 것이고, RM 업무 모드에서 C000001을 선택하는 것은 이미 정해진 5,000명 triage의 선정 이유와 Why Now를 검토하기 위한 것입니다. "
        "둘은 고객 ID가 같아도 역할이 다르며, 일반 모드의 입력이나 What-if는 RM Queue·Alert·Case를 바꾸지 않습니다. "
        "C000001의 일반 모드 landmark가 근거 부족으로 표시되면 오류가 아니라 historical cohort 근거의 unavailable 결과이며, RM Customer Review의 선정 이유·Why Now와는 별도입니다.",
        color="EAF2FB",
    )

    document.add_page_break()
    direct_input_visual = screens.get("general_direct_c000001", annotations.get("general_inputs"))
    if direct_input_visual is not None:
        _add_picture(
            document,
            direct_input_visual,
            "화면 4-1. 일반 모드에서 ‘고객 ID 직접 입력’을 선택하고 C000001을 넣은 실제 Edge 화면. 이 단계는 입력값을 읽는 단계이며, 다음으로 ‘유사 고객 찾기’를 눌러 분석을 시작합니다.",
            width=6.85,
        )
    document.add_page_break()
    queue_visual = screens.get("rm_queue")
    if queue_visual is not None:
        _add_picture(
            document,
            queue_visual,
            "화면 4-2. RM 업무 모드의 검토 큐. C000001은 5,000명 triage에서 1위로 이미 선정됐지만, 기본 상태에서는 ‘열린 Alert 없음 · 선정됨 · Case 미생성’으로 읽기 전용입니다.",
            width=6.85,
        )
    document.add_page_break()
    customer_review_visual = screens.get("rm_customer_review")
    if customer_review_visual is not None:
        _add_picture(
            document,
            customer_review_visual,
            "화면 4-3. C000001 Customer Review. ‘선정 이유’와 ‘왜 지금’을 읽고, prospective timing과 historical landmark를 같은 의미로 섞지 않습니다.",
            width=6.85,
        )

    document.add_page_break()
    document.add_heading("6.2 Synthetic Workflow Demo: 초기화 → Action → Audit → Reset 실습", level=2)
    document.add_paragraph(
        "이 실습은 기본 RM 화면을 바꾸지 않은 채 Alert/Case/RM Action/Audit의 업무 흐름만 교육하기 위한 별도 합성 Demo입니다. "
        "§6.1의 일반 분석·RM 검토와 달리, 여기서는 사용자가 명시적으로 초기화한 뒤에만 분리된 합성 runtime이 바뀝니다."
    )
    _add_table(
        document,
        ("순서", "클릭", "바뀌는 것", "절대 바뀌지 않는 것"),
        (
            ("1", "RM Portfolio에서 ‘합성 Workflow Demo 열기’", "rm_workflow_demo_* 화면 문맥만 열림", "5,000명 원본·triage·기본 Alert/Case"),
            ("2", "‘합성 Case 초기화’", "분리된 demo runtime에 합성 Case 3건이 NEW 상태로 준비되고 demo audit이 시작 상태로 reset", "기본 workflow/audit 저장소와 분석 CSV/JSON"),
            ("3", "C000001의 ‘확인’ 또는 ‘검토 시작’", "해당 합성 Case 상태와 append-only demo audit event", "고객 재무 수치·선정 순위·실제 Alert·결과 label"),
            ("4", "‘알림 미리보기(오프라인)’", "화면의 preview만 생성", "Case/audit 상태, 외부 전송, network, sent 결과"),
            ("5", "‘합성 Case 초기 상태로 reset’", "합성 Case 3건과 demo audit을 같은 NEW 시작 상태로 복원", "기본 RM 화면과 §6.1에서 본 분석 결과"),
            ("6", "‘기본 RM 업무로 돌아가기’", "Demo 세션 문맥만 정리", "분리 runtime 파일과 기본 RM의 0 Alert/0 Case 안전 기본값"),
        ),
    )
    _add_callout(
        document,
        "반복 실습의 핵심",
        "초기화와 reset은 같은 3건의 synthetic Case를 같은 NEW 상태로 되돌립니다. 따라서 발표자나 교육 참여자는 ‘초기화 → Action → Audit 확인 → reset’을 반복할 수 있습니다. 이 과정은 실제 고객 Case를 만들거나, 실제 알림을 보내거나, 5,000명 분석 결과를 바꾸지 않습니다.",
        color="FFF8E9",
    )
    entry_cta_visual = screens.get("rm_workflow_demo_entry_cta")
    if entry_cta_visual is not None:
        _add_picture(
            document,
            entry_cta_visual,
            "화면 4-4. 기본 RM Portfolio에서 ‘합성 Workflow Demo 열기’를 누르는 위치. 이 버튼을 누르기 전에는 기본 RM의 Alert/Case가 자동 생성되지 않습니다.",
            width=6.85,
        )

    document.add_page_break()
    workflow_entry_visual = screens.get("workflow_demo_entry")
    if workflow_entry_visual is not None:
        _add_picture(
            document,
            workflow_entry_visual,
            "화면 4-5. Demo 진입 직후. ‘합성 Case 초기화’를 명시적으로 누르기 전에는 Case가 생성되지 않으며, Synthetic fixture·실제 운영 아님·실제 발송 아님 경고를 먼저 확인합니다.",
            width=6.85,
        )
    workflow_new_visual = screens.get("workflow_demo_new")
    if workflow_new_visual is not None:
        _add_picture(
            document,
            workflow_new_visual,
            "화면 4-6. 초기화 직후 C000001 합성 Case는 NEW입니다. ‘확인’을 누르면 합성 Case 상태와 demo audit만 다음 상태로 진행합니다.",
            width=6.85,
        )

    document.add_page_break()
    workflow_ack_visual = screens.get("workflow_demo_ack")
    if workflow_ack_visual is not None:
        _add_picture(
            document,
            workflow_ack_visual,
            "화면 4-7. 확인 후: Case는 ACKNOWLEDGED가 되고 Activity/Audit에 append-only event가 한 건 기록됩니다. 하단의 reset 버튼으로 언제든 시작 상태로 되돌릴 수 있습니다.",
            width=6.85,
        )
    workflow_preview_visual = screens.get("workflow_demo_preview")
    if workflow_preview_visual is not None:
        _add_picture(
            document,
            workflow_preview_visual,
            "화면 4-8. 알림 미리보기는 offline preview이며 not sent입니다. 전송 채널 선택·외부 network·Case/Audit 변경은 없습니다.",
            width=6.85,
        )
    document.add_paragraph("심화 설명과 데이터 경계 표는 §21~§22를 참고합니다.")

    document.add_page_break()
    document.add_heading("7. 발표 모드 사용법", level=1)
    document.add_paragraph("목적: 한 고객의 분석 근거를 5개의 고정 탭으로 일관되게 전달합니다. 기본 발표 샘플은 C002608입니다.")
    _add_table(
        document,
        ("탭", "한 문장으로 설명", "발표에서 지킬 표현"),
        (
            ("1. 현재 상태", "관측 1–12개월의 현재 재무 상태입니다.", "현재 관측값과 신호라고 말함"),
            ("2. 유사 경로", "같은 출발 패턴의 과거 유사 고객 cohort를 봅니다.", "historical cohort 결과 비율이라고 말함"),
            ("3. 위험 분기점", "유사 과거 cohort가 갈렸던 retrospective landmark입니다.", "현재 고객의 위험 예정일이라고 말하지 않음"),
            ("4. 대응 시나리오", "rule-based 현금흐름 What-if 비교입니다.", "개입 효과 보장 또는 자동 처방이라고 말하지 않음"),
            ("5. 분석 요약", "근거·한계·상담 시 참고점을 정리합니다.", "합성 PoC 한계를 함께 말함"),
        ),
    )
    presentation_visual = screens.get("presentation", capture_cards["presentation"])
    _add_picture(
        document,
        presentation_visual,
        "화면 2. 발표 모드의 실제 초기 화면 캡처 (기본 C002608)."
        if "presentation" in screens
        else "화면 2. 실제 화면을 추가할 때의 수동 캡처 가이드 — 이 그림 자체는 live 화면이 아닙니다.",
        width=6.85,
    )

    document.add_page_break()
    document.add_heading("8. RM 업무 모드 사용법", level=1)
    document.add_paragraph("목적: 한 명을 먼저 보여주는 대신 5,000명 전체에서 어떤 경로로 검토 대상이 됐는지 보여줍니다. 첫 화면은 항상 Portfolio입니다.")
    _add_table(
        document,
        ("RM 탭", "무엇을 확인하나", "운영상 의미"),
        (
            ("Portfolio", "5,000 → eligible/selected → Monitor/No actionable funnel, Case count, capacity comparison", "정책 적격성·triage 선정·Alert를 혼동하지 않는 시작점"),
            ("Review Queue", "selected/routed existing case만 필터·정렬·검색", "Monitor/NoSignal/Insufficient은 operational queue가 아님"),
            ("Customer Review", "선정 이유, Why Now, current signals, twin evidence, historical landmark, recommended follow-up", "왜 이 고객·왜 지금을 근거별로 분리해 읽음"),
            ("Activity / Audit", "시간순 state/action 기록과 preview", "Preview는 발송이 아니며 audit은 append-only prototype"),
        ),
    )
    document.add_paragraph("Capacity 비교는 opt-in입니다. 예를 들어 3을 넣으면 저장된 1,522명 순위의 앞 3명만 비교상 selected로, 나머지 1,519명을 deferred로 보여줍니다. 이 입력은 원래 triage/Alert 파일이나 실제 정책을 변경하지 않습니다.")
    _add_callout(
        document,
        "현재 live 화면의 Action/Audit 범위",
        "기본 앱 경로에는 실제 case fixture가 없으므로 Portfolio에서는 selected pending 1,522 / open case 0이 정상일 수 있습니다. "
        "Action/Audit 완결 흐름은 격리된 synthetic dry-run 증거(최대 3개의 synthetic case와 append-only audit)로만 제시해야 합니다. 실운영처럼 보이게 하지 마십시오.",
        color="FFF8E9",
    )
    document.add_heading("8.1 안내된 RM 업무 흐름: 화면을 처음 보는 사용자를 위한 5단계", level=2)
    document.add_paragraph(
        "Guided Workflow는 새 정책이나 자동 의사결정 기능이 아닙니다. 이미 준비된 RM 화면을 읽는 순서를 안내하며, "
        "각 단계에서 현재 상태, 완료 조건, 다음 행동, 차단 사유를 보여줍니다. 기본 RM의 네 탭은 그대로 유지됩니다."
    )
    _add_callout(
        document,
        "Guided Workflow 이미지 상태: 한국어 기준 캡처 갱신 / 장비 sign-off 대기",
        "이 매뉴얼의 일반·발표·RM PNG는 현재 코드에서 임시 Edge 프로필(한국어, 1440×1500)로 다시 캡처한 기준 이미지입니다. 다만 실제 발표 장비의 1366×768과 1920×1080, Korean/English viewport sign-off는 별도로 PASS/FAIL로 기록해야 합니다. Step 1, capacity acknowledgement, Queue selection, Customer Review, no-Case 또는 Case action, Activity/Audit, Demo entry/return을 확인하고 상세 checklist는 SCREEN_CAPTURE_GUIDE.md를 따르십시오.",
        color="FFF1F3",
    )
    document.add_page_break()
    _add_table(
        document,
        ("단계", "사용자가 확인할 것", "완료 조건 / 다음 행동", "안전 경계"),
        (
            ("1. Portfolio / Capacity", "5,000명 funnel과 사람이 입력한 comparison", "입력한 정확한 capacity를 acknowledgement → Review Queue", "comparison-only; Queue ID·saved rank·Alert는 바뀌지 않음"),
            ("2. Queue Selection", "보이는 selected/routed operational row", "행 선택 → Customer Review", "Monitor·NoSignal·Insufficient·대표 비교는 operational Queue 완료가 아님"),
            ("3. Customer Evidence Review", "Selection Reason과 Why Now를 먼저 읽음", "근거 acknowledgement → RM Action", "landmark는 유사 과거 cohort의 retrospective 근거이며 미래 날짜가 아님"),
            ("4. RM Action", "기존 Case와 Banker action 가능 여부", "Case가 있으면 human RM action 기록 → Activity/Audit", "Case가 없으면 ‘선정됨 · Case 미생성’이 정상 block; 자동 Case 생성 없음"),
            ("5. Activity / Audit / Preview", "현재 Case의 append-only audit과 offline Preview", "기록 acknowledgement로 flow 종료", "Preview는 not sent·network 없음; audit은 현재 Case에만 연결"),
        ),
    )
    document.add_heading("8.2 다음 탭이 막힌 것처럼 보일 때: 실제 동작과 해결 순서", level=2)
    document.add_paragraph(
        "Guided Workflow의 진행 상태와 기본 RM 탭은 서로 다릅니다. Portfolio, Review Queue, Customer Review, "
        "Activity/Audit의 네 탭은 직접 열어 볼 수 있으며, Guide가 탭을 자동으로 이동시키거나 탭 자체를 잠그지 않습니다. "
        "다만 선행 완료 조건이 충족되지 않으면 상단 Guide는 다음 단계로 넘어가지 않고 현재 단계, 완료 조건, 다음 행동, 차단 사유를 계속 표시합니다. "
        "따라서 다음 표의 ‘먼저 할 일’을 해당 탭에서 마친 뒤 상단 Guide의 현재 단계가 바뀌었는지 확인하십시오."
    )
    _add_callout(
        document,
        "가장 먼저 볼 곳",
        "상단 Guided RM workflow의 Current step / 완료 조건 / 다음 행동 / 차단 사유를 먼저 읽으십시오. "
        "다음 탭을 먼저 열어도 내용을 확인할 수는 있지만, 선행 조건을 대신 완료하거나 Case를 자동으로 만들지는 않습니다.",
        color="EAF2FB",
    )
    document.add_page_break()
    _add_table(
        document,
        ("현재 단계", "다음 단계로 진행되지 않는 흔한 이유", "먼저 할 일"),
        (
            ("1. Portfolio / Capacity", "capacity comparison을 열지 않았거나 값을 입력·확인하지 않음", "Portfolio에서 Capacity comparison을 켠 뒤 0 이상의 값을 입력하고 ‘이 비교 시나리오 확인 완료’를 체크합니다. 값을 바꾸면 확인은 다시 해야 합니다."),
            ("2. Queue Selection", "선택한 고객이 없거나 representative comparison을 선택함", "Review Queue에서 보이는 selected/routed 행을 클릭합니다. 행이 안 보이면 검색어와 우선순위·담당자·기한 필터를 전체로 되돌립니다. Portfolio의 대표 비교 사례는 업무 Queue 선택이 아닙니다."),
            ("3. Customer Evidence Review", "운영 Queue에서 온 고객이 아니거나 Selection Reason / Why Now 확인이 끝나지 않음", "Customer Review에서 선택 이유와 Why Now를 먼저 읽고 ‘선정 근거와 Why Now 확인 완료’를 체크합니다. 근거 화면이 없거나 오래되었다면 Queue의 보이는 행을 다시 선택합니다."),
            ("4. RM Action", "선택 고객에게 기존 Alert/Case가 없음", "기본 RM에서 ‘선정됨 · Case 미생성’은 정상적인 안전 차단입니다. 자동 Case를 만들지 마십시오. 전체 조치·감사 연습이 필요하면 별도의 Synthetic Workflow Demo를 열어 연습하되, 기본 RM 진행 상태를 완료로 바꾸지는 않습니다."),
            ("5. Activity / Audit / Preview", "기존 Case의 조치·감사 기록이 없거나 기록 확인을 하지 않음", "기존 Case의 Banker 조치와 append-only Activity/Audit 기록을 확인한 뒤 ‘기록 확인 완료’를 체크합니다. Preview는 발송이 아니며 Preview만으로 이 단계가 완료되지는 않습니다."),
        ),
    )
    _add_callout(
        document,
        "사용자가 해결하지 않는 차단",
        "‘저장된 RM 산출물을 사용할 수 없음’, ‘선택 결과 재조정 불일치’, ‘RM workflow service를 사용할 수 없음’은 고객을 새로 선택하거나 Case를 만드는 방식으로 해결하지 않습니다. "
        "현재 화면을 유지하고 산출물·서비스 상태를 담당자에게 확인하십시오. Queue가 실제로 비어 있으면 Monitor·NoSignal 고객을 억지로 Queue에 넣지 않습니다.",
        color="FFF1F3",
    )
    rm_visual = screens.get("rm", capture_cards["rm"])
    _add_picture(
        document,
        rm_visual,
        "화면 3. RM 업무 모드 Portfolio의 실제 초기 화면 캡처 (합성 data/queue)."
        if "rm" in screens
        else "화면 3. 실제 화면을 추가할 때의 수동 캡처 가이드 — 이 그림 자체는 live 화면이 아닙니다.",
        width=6.85,
    )

    document.add_heading("9. 용어와 한계: 이 네 문장을 지키면 안전합니다", level=1)
    for body in (
        "‘유사 고객의 historical outcome share’이며, 이 고객의 prediction probability가 아닙니다.",
        "‘Historical landmark’는 유사 과거 cohort의 분기 근거이며, 현재 고객의 미래 위험 시점 예측이 아닙니다.",
        "‘What-if’는 rule-based cashflow simulation이며, 실제 개입 효과나 자동 alert 조정이 아닙니다.",
        "실제 익명화 데이터 검증은 아직 하지 않았습니다. 현재는 governance·adapter·metric 계약과 synthetic dry-run만 준비된 상태입니다.",
    ):
        document.add_paragraph(body, style="List Bullet")

    document.add_heading("10. 문제 발생 시", level=1)
    _add_table(
        document,
        ("상황", "먼저 할 일", "해석"),
        (
            ("landmark를 찾지 못함", "C002082 같은 비교 사례와 status를 확인", "비교 cohort가 충분하지 않으면 ‘근거 부족’이 정상 결과일 수 있음"),
            ("RM Queue가 비어 보임", "selected/routed filter와 workflow artifact 존재 여부 확인", "Monitor/NoSignal을 억지로 queue에 넣지 않음"),
            ("Action/Audit가 비어 있음", "기본 workflow fixture 부재 여부 확인", "현재 live 기본 경로에서는 정상이며 synthetic dry-run과 구분"),
            ("앱 import/실행 오류", "01 → 02 → 03 BAT 순서, then readiness check", "서버를 중복 실행하지 말고 foreground BAT를 새 창에서 실행"),
        ),
    )

    document.add_heading("11. 발표자용 한 줄 결론", level=1)
    _add_callout(
        document,
        "권장 멘트",
        "‘Financial Path Twin은 5,000명의 합성 고객에서 유사 과거 경로와 현재 관측 신호를 분리해 보여주는 PoC입니다. "
        "시스템이 고객을 자동 결정하지 않으며, RM이 검토할 근거와 업무량 trade-off를 투명하게 확인하도록 돕습니다.’",
        color="EAF2FB",
    )

    add_detailed_operating_sections(document, diagrams=diagrams, screens=screens)
    add_status_faq_section(document, annotations=annotations)
    add_workflow_demo_sections(document, diagrams=diagrams, screens=screens, annotations=annotations)

    # Apply the footer to the existing final section. Adding a new-page section
    # here creates trailing blank pages after the operating guide.
    section = document.sections[-1]
    section.footer.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    section.footer.paragraphs[0].add_run("Financial Path Twin · Synthetic data PoC · 운영 사용자 매뉴얼")
    output = output_path or OUTPUT_DIR / MANUAL_NAME
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    return output


def add_detailed_operating_sections(
    document: Document,
    *,
    diagrams: dict[str, Path],
    screens: dict[str, Path],
) -> None:
    """Append evidence-first operations, feedback, and rehearsal guidance.

    This is intentionally a manual-only layer: every statement distinguishes a
    reproducible synthetic-PoC result from a human decision or an open real-data
    validation task.  It does not invoke analytics or create workflow state.
    """

    document.add_heading("12. 현재 상태를 한 장으로 이해하기", level=1)
    document.add_paragraph(
        "이 문서의 가장 중요한 규칙은 ‘되는 것’, ‘사람이 승인해야 하는 것’, ‘아직 검증되지 않은 것’을 한 문장으로 섞지 않는 것입니다. "
        "아래 구분을 발표와 운영 설명의 공통 기준으로 사용합니다."
    )
    _add_picture(
        document,
        diagrams["evidence_status"],
        "그림 5. 현재 합성 PoC에서 증명된 범위와, 사람의 운영 판단 및 실제 검증의 경계.",
        width=6.9,
    )
    _add_table(
        document,
        ("구분", "현재 근거", "발표·운영에서 말하는 방식", "말하면 안 되는 방식"),
        (
            (
                "현재 증명됨",
                "합성 5,000명 전수 분석, deterministic triage, 다중 고객 비교, selected-only queue, audit prototype, leakage/circularity 검증",
                "‘고정 seed=42의 합성 PoC에서 재현했습니다.’",
                "‘실제 은행 정확도·성과를 증명했습니다.’",
            ),
            (
                "사람의 판단 필요",
                "capacity 입력 비교, draft policy, RM의 follow-up 기록",
                "‘시스템은 비교 근거를 제공하고 최종 승인과 업무량 결정은 사람이 합니다.’",
                "‘1,522명이 적정 업무량입니다.’",
            ),
            (
                "아직 open",
                "실제 익명화 데이터 검증, 실제 RM pilot, 외부 전송/SLA, DB 연동",
                "‘승인된 환경에서 검증하기 위한 governance·adapter·metric 계약을 준비했습니다.’",
                "‘실제 고객 데이터나 실제 RM 결과로 검증되었습니다.’",
            ),
        ),
    )
    _add_callout(
        document,
        "현재 공식 상태",
        "READY_WITH_OPEN_REAL_DATA_VALIDATION입니다. 합성 데이터 기반의 분석·선별·화면·프로토타입 workflow를 정직하게 보여주되, 실제 데이터 검증과 실제 운영 효과는 open으로 남겨 둡니다.",
        color="FFF8E9",
    )

    document.add_heading("13. RM 업무 모드 전에 팀이 준비할 일", level=1)
    document.add_paragraph(
        "RM 업무 모드는 단순히 화면을 열어 보는 기능이 아닙니다. 분석 결과의 provenance, 사람이 승인할 운영 경계, 그리고 데모 fixture의 범위를 먼저 확인해야 합니다."
    )
    _add_picture(
        document,
        diagrams["rm_preparation"],
        "그림 6. 데모에서 바로 가능한 준비와 실제 운영 전 조직이 결정해야 하는 준비를 분리한 workflow.",
        width=6.9,
    )
    _add_table(
        document,
        ("순서", "주체", "해야 할 일", "현재 상태 / 확인 근거"),
        (
            ("1", "데모 운영자", "01_install_requirements → 02_run_pipeline → 03_run_app 순서로 로컬 환경을 준비", "사용 가능. 분석 규칙이나 canonical data를 바꾸지 않음"),
            ("2", "분석 담당자", "Population/Triage manifest의 exact reconciliation을 확인", "5,000 monitored = 1,522 selected + 371 monitor + 3,107 no actionable"),
            ("3", "정책·업무 책임자", "정책 version, selection as-of, Why Now와 historical landmark의 분리를 검토", "demo policy. production-approved 정책이 아님"),
            ("4", "업무 책임자", "capacity를 사람이 입력해 Selected/Deferred trade-off를 검토", "draft comparison only. 시스템이 적정 값·SLA를 승인하지 않음"),
            ("5", "발표자", "RM Portfolio → Queue → Customer Review에서 근거를 설명", "선택된/routed case만 operational queue. Monitor/NoSignal은 비교 사례"),
            ("6", "RM", "승인된 실제 Case가 있는 범위에서만 action과 outcome을 기록", "기본 앱은 open Case 0이 정상. action/audit은 격리된 synthetic dry-run 증거로만 시연"),
            ("7", "Data owner·Security·Privacy", "실제 데이터·실제 pilot 전 governance와 승인 경로를 결정", "not requested / not initiated. 현재 저장소에서 실제 데이터를 받지 않음"),
        ),
    )
    _add_picture(
        document,
        diagrams["capacity_example"],
        "그림 7. 사람이 capacity=3을 입력했을 때의 artifact-backed 비교 예시. 순위와 원본 triage는 바뀌지 않습니다.",
        width=6.9,
    )
    _add_callout(
        document,
        "기본 RM 화면에서 Action/Audit이 비어 있어도 오류가 아닙니다",
        "기본 artifacts/workflow와 artifacts/audit에는 Case fixture가 없으므로 ‘선정됨 · Case 미생성’과 open Case 0이 정상입니다. Action/Audit의 동작 근거는 artifacts/post_p0/pilot_dry_run/seed42_capacity_3의 격리된 합성 rehearsal(3 Cases, 10 Audit events)로만 설명합니다. 라이브 데모 화면에서 억지로 Case를 만들어서는 안 됩니다.",
        color="FFF1F3",
    )

    document.add_heading("14. 받은 평가 피드백에 대한 발표·준비 방법", level=1)
    document.add_paragraph(
        "피드백은 방어적으로 답하기보다, 현재 화면과 evidence를 먼저 보여주고 남은 검증을 명확히 말하는 방식이 가장 설득력 있습니다."
    )
    _add_picture(
        document,
        diagrams["feedback_response"],
        "그림 8. 평가 피드백 → 앱에서 보여줄 근거 → 정직하게 남길 한계의 대응 지도.",
        width=6.9,
    )
    _add_table(
        document,
        ("평가 의견", "지금 보여줄 화면·근거", "발표에서 할 답", "남은 과제"),
        (
            (
                "합성 데이터·한 고객 데모",
                "RM Portfolio의 5,000 funnel, Queue, C000001/C000007/C000003 대표·비교 사례",
                "‘한 고객만 보여주는 대신 전수 결과를 숨기지 않았고, representative cohort도 미래 label 없이 고정했습니다.’",
                "실제 익명화 데이터 검증은 governance 승인 후 별도로 수행",
            ),
            (
                "앱을 더 많이 보여 달라",
                "Portfolio → capacity → Customer Review → Presentation 5 tabs의 연속 화면",
                "‘슬라이드가 아니라 앱에서 evidence와 경계를 직접 보여드립니다.’",
                "영상 녹화·편집·리허설은 팀이 별도로 완료해야 함",
            ),
            (
                "Banker Workflow가 필요",
                "Policy → TriageDecision → selected/routed Case → RM action → append-only audit → Preview 흐름",
                "‘자동 금융결정이 아니라 RM이 검토할 근거와 기록 가능한 workflow prototype입니다.’",
                "실제 Case 운영, 외부 전달, SLA, 실제 RM 성과는 증명하지 않음",
            ),
            (
                "언제 행동해야 하는가",
                "C000001의 Why Now와 C002608의 historical landmark 화면을 분리",
                "‘Why Now는 현재·과거 관측 신호 기반 검토 근거이며, landmark는 유사 과거 cohort의 맥락입니다.’",
                "개별 고객의 미래 위험 월·확률·개입 효과를 주장하지 않음",
            ),
        ),
    )

    document.add_heading("15. 실제 Edge 화면으로 보는 증거 갤러리", level=1)
    document.add_paragraph(
        "아래 이미지는 이 저장소의 현재 로컬 앱을 임시 Edge 프로필에서 캡처한 것입니다. 캡처는 읽기 전용 화면 전환만 사용했으며, 각 표시는 synthetic data/PoC 경계를 유지합니다.")
    gallery = (
        (
            "presentation_landmark",
            "화면 4. Presentation ③ 유사 경로 근거. ‘과거 landmark 13개월 차’와 ‘현재 고객의 미래 예측 시점이 아님’ 문구가 함께 보입니다.",
        ),
        (
            "presentation_whatif",
            "화면 5. Presentation ④ 대응 시나리오. What-if는 규칙 기반 현금흐름 시뮬레이션이며 조치 효과 보장이 아닙니다.",
        ),
        (
            "rm_capacity_3",
            "화면 6. RM Portfolio의 사람이 입력한 capacity=3 비교. 이 값은 임시 세션의 draft 비교이며 저장된 순위·원본 triage·workflow를 바꾸지 않습니다.",
        ),
        (
            "rm_queue",
            "화면 7. RM 검토 큐. 1,522개의 versioned selection만 표시하며 ‘선정됨 · Case 미생성’을 정직하게 구분합니다.",
        ),
        (
            "rm_customer_review",
            "화면 8. C000001 Customer Review. 선정 이유와 Why Now, 현재 신호를 보여주되 미래 발생월을 표시하지 않습니다.",
        ),
    )
    gallery += (
        (
            "presentation_c002082_insufficient",
            "화면 9. C002082의 Presentation ③ 유사 경로 근거. 200명 매칭은 성공했지만 historical landmark를 비교할 과거 결과 집단이 충분하지 않아 ‘분석 제한’으로 정직하게 표시됩니다.",
        ),
        (
            "rm_monitor_c000003",
            "화면 10. C000003 Customer Review. Monitor는 대표 비교 사례이며, 화면의 선정 이유는 이 고객이 현재 운영 검토 큐에 포함되지 않는다는 것을 명시합니다.",
        ),
        (
            "rm_queue_c000003_excluded",
            "화면 11. RM Queue에서 C000003을 검색한 결과. 0건은 오류가 아니라 Monitor 비교 사례를 selected/routed operational queue에 섞지 않는 설계의 결과입니다.",
        ),
    )
    for key, caption in gallery:
        image_path = screens.get(key)
        if image_path is not None and image_path.exists():
            _add_picture(document, image_path, caption, width=6.85)
    if screens.get("rm_capacity_3") is None:
        _add_callout(
            document,
            "용량 비교 화면에 대한 안내",
            "이 매뉴얼에는 실제 artifact 값으로 만든 그림 7을 사용합니다. capacity 값은 Streamlit 세션에서만 입력하는 draft 비교이며, 저장된 triage·Alert·workflow 파일을 바꾸지 않습니다.",
            color="EAF2FB",
        )

    document.add_heading("16. General 모드 입력을 더 잘 쓰는 법", level=1)
    document.add_paragraph(
        "General 모드는 발표의 기본 story를 대체하는 화면이 아니라, 질문이 나왔을 때 분석을 확인하는 화면입니다. 모든 입력은 합성 데이터셋 안의 demo/customer ID만 사용합니다.")
    _add_table(
        document,
        ("입력·화면 요소", "권장 값", "발표/질문에서 쓰는 이유", "확인할 문장"),
        (
            ("화면 모드", "일반 모드", "고객·지표를 직접 바꾸는 상세 확인", "General 상태는 Presentation/RM의 고객·큐 상태를 바꾸지 않음"),
            ("고객 선택", "C002608", "메인 분석 story와 발표 5 tabs를 연결", "200명의 유사 과거 cohort를 사용한 historical evidence"),
            ("고객 선택", "C002082", "비교 집단 부족·landmark unavailable을 정직하게 보이는 Q&A", "근거가 충분하지 않으면 landmark를 억지로 만들지 않음"),
            ("고객 선택", "C002672", "시각적 high-risk 대비가 필요한 Q&A", "RM 선정·미래 label의 근거로 사용하지 않음"),
            ("직접 고객 ID", "합성 CSV에 존재하는 ID만", "드롭다운 밖 demo ID를 검토할 때", "실제 고객 ID·개인정보를 입력하지 않음"),
            ("표시 지표", "저축률 → DSR → 고정지출 비중", "질문에 맞는 trajectory를 읽기 쉽게 전환", "지표 전환은 표시만 바꾸며 결과·정책을 재계산하지 않음"),
            ("원본 상세 표시", "Q&A 때만", "수치 확인이 필요할 때만 사용", "기본 발표 화면은 너무 많은 raw detail로 채우지 않음"),
            ("언어", "한국어/English", "청중에 맞춘 표현 전환", "언어 전환은 계산·queue 결과를 바꾸지 않음"),
        ),
    )

    document.add_heading("17. 발표·데모 리허설 runbook", level=1)
    _add_table(
        document,
        ("시간", "화면", "보여줄 것", "말할 핵심", "절대 하지 않을 말"),
        (
            ("0:00–0:20", "RM Portfolio", "5,000 → 1,522 → Monitor 371 → No actionable 3,107의 exact funnel", "‘한 명이 아니라 전체 synthetic population에서 시작합니다.’", "‘1,522명이 실제 RM 업무량입니다.’"),
            ("0:20–0:40", "Capacity comparison", "사람 입력 3 → 3 selected / 1,519 deferred", "‘사람이 가정을 넣어 trade-off를 비교합니다.’", "‘시스템이 3명을 추천했습니다.’"),
            ("0:40–1:05", "Customer Review C000001", "선정 이유, Why Now, current signals, policy provenance", "‘왜 이 고객이며 왜 지금 검토하는가를 설명합니다.’", "‘이 고객은 특정 미래 월에 위험해집니다.’"),
            ("1:05–1:20", "C000007 + C000003", "Review와 Monitor의 차이, Monitor는 operational queue 밖", "‘대표 사례를 미래 label로 고른 것이 아닙니다.’", "‘Monitor도 검토 큐에 넣었습니다.’"),
            ("1:20–1:45", "Presentation C002608", "유사 경로 → historical landmark → What-if", "‘landmark는 과거 cohort의 맥락, What-if는 규칙 기반 가정입니다.’", "‘위험확률/개입효과를 증명했습니다.’"),
            ("1:45–2:00", "마지막 boundary", "실데이터 governance/adapter/metric 및 pilot protocol", "‘다음 검증을 준비했지만 아직 검증 완료가 아닙니다.’", "‘실제 은행에 이미 적용됐습니다.’"),
        ),
    )
    _add_callout(
        document,
        "권장 화면 비중",
        "실제 앱 화면 약 60%, 방법론·검증 약 25%, 합성 한계와 다음 검증 약 15%를 권장합니다. 발표 직전에는 C002608, C000001, C000007, C000003의 화면 전환을 한 번씩 리허설하고, C002082는 ‘근거 부족을 숨기지 않는’ Q&A용으로 준비합니다.",
        color="EAF2FB",
    )

    document.add_heading("18. RM 기본 화면에서 Alert가 0개인 이유", level=1)
    document.add_paragraph(
        "기본 RM 화면의 ‘열린 Alert 없음’, ‘RM 업무 큐 Case 0’, ‘선정됨 · Case 미생성’은 오류가 아닙니다. "
        "선정(Triage)과 Case 생성(Alert cycle)을 분리했기 때문에, 기본 데모는 5,000명 전체의 선정 근거를 안전하게 읽는 상태로 시작합니다."
    )
    alert_status_image = ASSET_DIR / "13_rm_alert_case_status_explained.png"
    if alert_status_image.exists():
        _add_picture(
            document,
            alert_status_image,
            "화면 9. 실제 RM Portfolio 상태 위에 ‘Alert 0 / Case 0 / Case 생성 대기 1,522’의 의미를 표시한 안내 이미지.",
            width=6.85,
        )
    _add_table(
        document,
        ("화면 표시", "정확한 뜻", "사용자가 할 수 있는 일", "사용자가 하지 않는 일"),
        (
            (
                "열린 Alert 없음",
                "기본 artifacts/workflow에 생성된 Case가 0개라는 뜻",
                "선정 근거·Why Now·유사 경로 evidence를 검토",
                "오류라고 판단하거나 Alert가 전달됐다고 해석하지 않음",
            ),
            (
                "RM 업무 큐 Case 0",
                "기본 화면은 읽기 전용이며 Case fixture를 자동으로 만들지 않음",
                "Portfolio와 Queue에서 선정 결과를 확인",
                "UI에서 repository 파일을 직접 만들거나 수정하지 않음",
            ),
            (
                "선정됨 · Case 미생성",
                "이 고객은 Triage의 CREATE_NEW_CASE routing contract를 받았지만 Case 생성은 아직 실행되지 않음",
                "‘검토할 이유가 있음’과 ‘실제 업무 항목이 생성됨’을 분리해 설명",
                "선정 1,522명을 실제 Alert 1,522건 또는 실제 업무량으로 말하지 않음",
            ),
            (
                "Case 생성 대기 1,522",
                "unbounded demo의 후보 집합. capacity가 없는 참조값",
                "사람 입력 capacity로 Selected/Deferred trade-off를 비교",
                "자동 capacity 승인·자동 Case 생성으로 해석하지 않음",
            ),
        ),
    )
    _add_callout(
        document,
        "숨은 Case 생성 작업은 없습니다",
        "02_run_pipeline.bat, RM 화면 탐색, capacity 비교는 기본 Case를 만들지 않습니다. 이는 policy eligibility·Triage selection·Alert creation의 책임을 분리한 설계입니다. 실제 Case가 필요하면 별도의 승인된 Alert cycle과 분리된 output path가 필요하며, 현재 기본 데모에서는 이를 실행하지 않습니다.",
        color="FFF8E9",
    )

    document.add_heading("19. 기본 데모와 synthetic workflow rehearsal을 구분하는 법", level=1)
    document.add_paragraph(
        "Action/Audit을 설명해야 할 때 기본 화면의 상태를 바꾸지 않습니다. 아래 두 경로를 나란히 보여주면, 현재 동작과 별도 합성 검증 증거를 모두 정직하게 전달할 수 있습니다."
    )
    _add_picture(
        document,
        diagrams["default_vs_rehearsal"],
        "그림 9. 기본 RM 데모는 Case를 자동 생성하지 않으며, synthetic workflow rehearsal은 별도 artifact 경로의 증거입니다.",
        width=6.9,
    )
    _add_table(
        document,
        ("구분", "무엇을 보여주나", "수치·근거", "발표에서 반드시 붙일 문장"),
        (
            (
                "기본 RM 데모",
                "5,000 population → 1,522 selected → Queue/Customer Review의 선정 이유와 Why Now",
                "workflow Case 0, selected pending 1,522",
                "‘이 화면은 선정 근거를 검토하는 읽기 전용 기본 상태입니다.’",
            ),
            (
                "격리 synthetic rehearsal",
                "선택된 합성 TriageDecision → idempotent Case → RM action/audit/Preview contract",
                "artifacts/post_p0/pilot_dry_run/seed42_capacity_3: synthetic Cases 3, audit events 10, network=false",
                "‘별도 합성 rehearsal의 workflow 증거이며 실제 고객·외부 전달·RM 성과가 아닙니다.’",
            ),
            (
                "향후 실제 운영",
                "승인된 policy/capacity/governance 아래 명시적 Alert cycle과 RM pilot",
                "현재 not initiated / real-data validation open",
                "‘실제 운영 전제는 별도 조직 승인과 안전 환경 검증이 필요합니다.’",
            ),
        ),
    )
    _add_callout(
        document,
        "발표자가 따를 30초 설명 순서",
        "① Portfolio에서 ‘선정됨 · Case 미생성’과 Alert 0을 보여주고 정상 상태라고 설명합니다. ② Queue/Customer Review에서 선정 이유와 Why Now를 보여줍니다. ③ Action/Audit 질문이 나오면 기본 화면을 변경하지 않고, 그림 9와 격리된 synthetic rehearsal의 3 Cases/10 audit events를 별도 증거로 제시합니다.",
        color="EAF2FB",
    )


def add_status_faq_section(document: Document, *, annotations: dict[str, Path]) -> None:
    """Append four evidence-first FAQ pages for presenters and new users."""

    document.add_heading("20. 자주 나오는 상태별 FAQ — 화면으로 답하기", level=1)
    document.add_paragraph(
        "이 장은 ‘오류인가?’, ‘무엇을 해야 하나?’, ‘발표에서 어떻게 답하나?’를 빠르게 확인하기 위한 Q&A입니다. "
        "각 답은 현재 synthetic artifact와 실제 로컬 Edge 화면을 기준으로 하며, 실제 고객 성과·승인된 업무량·외부 전달 결과로 확대 해석하지 않습니다."
    )
    faq_overview = annotations.get("faq_overview")
    if faq_overview is not None and faq_overview.exists():
        _add_picture(
            document,
            faq_overview,
            "그림 10. 네 가지 상태 FAQ의 한눈에 보기. 상세 화면과 발표용 답변은 이어지는 카드에서 확인합니다.",
            width=6.9,
        )
    _add_table(
        document,
        ("질문", "빠른 판정", "바로 열 화면"),
        (
            ("C002082 landmark 근거 부족", "정상적인 unavailable 결과", "Presentation ③ 유사 경로 근거"),
            ("C000003 Monitor가 Queue 밖", "운영 Queue와 분리된 대표 비교 사례", "RM 고객 검토 + Queue 검색"),
            ("Capacity=3 / Deferred=1,519", "사람이 입력한 draft 비교", "RM Portfolio · 검토 용량 비교"),
            ("Alert / Case=0", "읽기 전용 기본 workflow 상태", "RM Portfolio + 18~19장"),
        ),
    )
    faq_sections = (
        (
            "20.1 C002082 — landmark 근거가 부족하면 무엇을 뜻하나?",
            "faq_landmark",
            "이 화면은 전체 5,000명 전수 분석이 실패했다는 뜻이 아닙니다. C002082의 200명 유사 경로 cohort 안에서 historical landmark를 비교할 두 결과 집단이 충분하지 않은 상태입니다.",
            (
                ("확인된 사실", "matched_count=200, analysis_status=success, risk-path=0명, avoidance=200명. landmark 비교는 양쪽 최소 20명을 요구합니다."),
                ("올바른 해석", "유사 과거 cohort에서 비교 근거가 부족하므로 landmark를 unavailable로 둡니다."),
                ("말하면 안 되는 것", "‘이 고객은 안전하다’, ‘5,000명이 부족해 실패했다’, ‘현재 고객의 미래 위험 날짜를 예측했다’는 단정."),
                ("발표 20초 답", "‘매칭은 됐지만 비교할 과거 risk-path 집단이 없어 landmark를 억지로 만들지 않았습니다. 이것은 현재 고객의 미래 예측일이 아닙니다.’"),
            ),
        ),
        (
            "20.2 C000003 — Monitor는 왜 운영 Review Queue에 없나?",
            "faq_monitor",
            "Monitor는 ‘아무 신호가 없다’가 아니라 ‘현재 신호는 관찰하되, 이 run의 triage가 즉시 review route로 보내지 않았다’는 뜻입니다. 대표 비교 사례와 operational queue를 섞지 않는 것이 핵심입니다.",
            (
                ("확인된 사실", "primary_disposition=MONITOR_ONLY, selection_disposition=NOT_QUEUE_ELIGIBLE, routing_disposition=NO_ROUTING, selected_for_review=false."),
                ("올바른 해석", "Policy eligibility와 Triage selection은 별도 책임입니다. Queue에는 selected/routed existing case만 표시됩니다."),
                ("말하면 안 되는 것", "‘Monitor는 신호가 없다’, ‘Monitor도 운영 Queue 행이다’, ‘모든 signal이 Alert가 된다’는 설명."),
                ("발표 20초 답", "‘C000003은 대표 비교 사례로는 열 수 있지만, triage가 MONITOR_ONLY·NO_ROUTING으로 정했으므로 운영 Queue에는 넣지 않습니다.’"),
            ),
        ),
        (
            "20.3 Capacity=3 — 왜 1,519명이 Deferred인가?",
            "faq_capacity",
            "Capacity 3은 사람이 넣어 보는 한 회차 비교 가정입니다. 시스템이 적정 인력이나 실제 SLA를 승인하는 기능이 아니며, 저장된 transparent ranking을 바꾸지 않습니다.",
            (
                ("확인된 사실", "eligible=1,522, 입력 capacity=3, 비교상 selected=3, deferred=1,519. 1,522 = 3 + 1,519로 정확히 조정됩니다."),
                ("올바른 해석", "저장된 순위의 앞 3명만 그 가정에서 selected이고, 나머지는 거절이 아니라 이번 capacity 밖의 deferred입니다."),
                ("말하면 안 되는 것", "‘RM은 실제로 3명만 처리한다’, ‘1,519명은 버렸다’, ‘Deferred가 안전하다’, ‘Case가 자동 생성됐다’는 표현."),
                ("발표 20초 답", "‘사람이 용량 가정을 입력해 workload trade-off를 비교합니다. 시스템이 3명을 추천하거나 원 순위·Alert를 바꾸는 것은 아닙니다.’"),
            ),
        ),
        (
            "20.4 Alert / Case=0 — 왜 오류가 아닌가?",
            "faq_alert_case",
            "기본 workflow repository에 Case fixture가 없으므로 Alert와 Case가 0으로 보입니다. 이는 selection evidence를 먼저 검토하게 하는 비파괴 기본 상태입니다.",
            (
                ("확인된 사실", "기본 화면은 open Alert=0, RM Queue Case=0, selected Case pending=1,522입니다. 격리 rehearsal은 synthetic Case 3건, audit 10건, network=false입니다."),
                ("올바른 해석", "Triage selection은 Alert/Case를 만들기 전의 routing contract이며, 기본 앱에서는 실제 cycle을 실행하지 않습니다."),
                ("말하면 안 되는 것", "‘분석이 실패했다’, ‘1,522명이 이미 Alert다’, ‘버튼을 눌러 Case를 만든다’, ‘외부 메시지가 전송됐다’는 설명."),
                ("발표 20초 답", "‘기본 데모는 선정 근거를 읽는 상태이고 Action/Audit은 별도 합성 rehearsal 증거로만 보여줍니다. 화면에서 Case를 억지로 만들지 않습니다.’"),
            ),
        ),
    )
    for heading, image_key, introduction, rows in faq_sections:
        document.add_heading(heading, level=2)
        document.add_paragraph(introduction)
        image_path = annotations.get(image_key)
        if image_path is not None and image_path.exists():
            _add_picture(document, image_path, f"{heading}의 실제 화면·artifact 기반 FAQ 카드.", width=6.9)
        _add_table(document, ("항목", "설명"), rows)


def add_workflow_demo_sections(
    document: Document,
    *,
    diagrams: dict[str, Path],
    screens: dict[str, Path],
    annotations: dict[str, Path],
) -> None:
    """Append the explicit synthetic Workflow Demo operator and presentation guide."""

    document.add_page_break()
    document.add_heading("21. 새 기능: 분리된 Synthetic Workflow Demo", level=1)
    document.add_paragraph(
        "Workflow Demo는 기본 RM 화면의 Case 0 상태를 바꾸지 않은 채, Alert/Case/RM Action/Audit의 전체 흐름을 "
        "안전하게 시연하기 위해 추가된 별도 문맥입니다. 네 번째 앱 모드, 다섯 번째 RM 탭, 별도 브라우저 또는 별도 "
        "Streamlit 앱이 아닙니다. RM Workspace 안에서 사용자가 Open Synthetic Workflow Demo를 명시적으로 눌렀을 때만 열립니다."
    )
    _add_callout(
        document,
        "기본 RM과 Demo를 먼저 구분합니다",
        "기본 RM의 열린 Alert=0, Case=0, 선정됨·Case 미생성은 정상적인 안전 기본값입니다. Workflow Demo는 그 "
        "기본값을 우회하거나 실제 Case를 만들지 않습니다. Demo 내부의 3건은 미리 정한 synthetic fixture이며, "
        "모든 화면에서 Synthetic, not live, Preview only라는 경계를 유지해야 합니다.",
        color="FFF8E9",
    )
    _add_table(
        document,
        ("구분", "기본 RM Workspace", "Workflow Demo secondary context"),
        (
            ("진입", "일반/발표/RM 3개 앱 모드 중 RM을 선택하면 바로 열림", "RM 내부 Open Synthetic Workflow Demo를 명시적으로 선택한 뒤에만 열림"),
            ("시작 상태", "기본 workflow/audit repository가 없으면 Case=0, Audit=0", "DEMO_NOT_INITIALIZED. 진입만으로 파일이나 Case를 만들지 않음"),
            ("초기화", "기본 RM은 자동 Case 생성 기능을 제공하지 않음", "Initialize synthetic Cases를 누르면 정확히 3개의 synthetic Case를 별도 runtime에 생성"),
            ("종료", "RM Portfolio/Queue/Customer Review의 읽기 전용 기준 화면", "Return to default RM workspace는 demo session key만 지우며, runtime 파일을 삭제하지 않음"),
        ),
    )

    document.add_heading("21.1 실제 화면으로 보는 명시적 진입과 초기화", level=2)
    document.add_paragraph(
        "아래 두 화면은 이 매뉴얼 생성 시 임시 Edge 프로필과 임시 synthetic runtime에서 캡처했습니다. "
        "첫 화면은 Demo에 들어가기만 한 상태이고, 두 번째 화면은 정확히 3건의 synthetic Case를 초기화한 상태입니다. "
        "두 화면 모두 기본 RM workflow/audit과 5,000명 분석 artifact에는 쓰지 않습니다."
    )
    workflow_entry = screens.get("workflow_demo_entry")
    if workflow_entry is not None and workflow_entry.exists():
        _add_picture(
            document,
            workflow_entry,
            "화면 12. 실제 Edge 화면 — Demo 진입 직후: Case가 아직 초기화되지 않았으며, 명시적 ‘합성 Case 초기화’ 버튼만 보입니다.",
            width=6.85,
        )
    workflow_new = screens.get("workflow_demo_new")
    if workflow_new is not None and workflow_new.exists():
        _add_picture(
            document,
            workflow_new,
            "화면 13. 실제 Edge 화면 — 초기화 직후: C000001은 NEW이며, 세 Case 고정 fixture 중 하나로 표시됩니다.",
            width=6.85,
        )
    if workflow_entry is None or workflow_new is None or not workflow_entry.exists() or not workflow_new.exists():
        _add_callout(
            document,
            "화면 캡처가 없는 경우",
            "이 문서의 그림 11 경계 다이어그램과 섹션 23의 수동 리허설 절차로 대신 확인합니다. 캡처가 없다고 Demo가 자동으로 초기화되거나 기본 RM Case가 생성되는 것은 아닙니다.",
            color="FFF8E9",
        )

    document.add_heading("21.2 Demo fixture의 고정 범위", level=2)
    document.add_paragraph(
        "초기화 직후의 Case는 다음 3건으로 고정됩니다. 이는 5,000명 전체를 다시 선택하는 엔진이 아니라, "
        "저장된 selection-rank provenance를 가진 작은 synthetic 시연 fixture입니다. 최대 3건을 넘으면 fail-closed입니다."
    )
    _add_table(
        document,
        ("순서", "Customer ID", "Alert ID", "초기 상태", "업무 우선순위"),
        (
            ("1", "C000001", "ALT-DEMO-C000001", "NEW", "PRIORITY_REVIEW"),
            ("2", "C000008", "ALT-DEMO-C000008", "NEW", "PRIORITY_REVIEW"),
            ("3", "C000010", "ALT-DEMO-C000010", "NEW", "PRIORITY_REVIEW"),
        ),
    )

    _add_callout(
        document,
        "이 fixture가 사용하지 않는 정보",
        "세 Case의 선택은 as_of_month=12 시점의 저장된 selection provenance만 사용합니다. target의 month 13~36, "
        "final_outcome, persona, evaluator label은 Case 선택이나 화면 이유 생성에 사용하지 않습니다.",
        color="EAF2FB",
    )

    document.add_heading("22. 가장 중요한 운영 기준: RM action이 바꾸는 데이터", level=1)
    document.add_paragraph(
        "RM Action은 분석을 다시 돌리는 기능이 아닙니다. 사용자가 명시적으로 Demo를 초기화하고 action을 실행할 때, "
        "분리된 synthetic Case 상태와 append-only audit만 바뀝니다. 이 경계는 발표에서 가장 먼저 설명할 안전장치입니다."
    )
    _add_picture(
        document,
        diagrams["workflow_demo_boundary"],
        "그림 11. 새 Workflow Demo의 데이터 변경 경계. 이 그림은 실제 UI 캡처가 아니라 artifact 경계를 설명하는 운영 다이어그램입니다.",
        width=6.9,
    )
    _add_table(
        document,
        ("사용자 동작", "변경될 수 있는 Demo 데이터", "절대 변경하지 않는 데이터"),
        (
            ("Open Synthetic Workflow Demo", "rm_workflow_demo_* session namespace만 생성. Case/Audit/runtime 파일은 읽기 전용", "기본 RM 필터/고객 문맥, 5,000명 분석, 기본 workflow/audit 저장소"),
            ("Initialize synthetic Cases 또는 Reset", "artifacts/workflow_demo/runtime/runtime_manifest.json, workflow/alert_cases.json을 원자적으로 다시 생성. 3건을 NEW로 복원하고 demo audit을 초기화", "원본/처리 CSV/JSON, feature/matcher/outcome/breakpoint/What-if, triage/ranking/capacity, 기본 artifacts/workflow 및 artifacts/audit"),
            ("Acknowledge / Start Review / Follow-up / Close", "demo alert_cases.json의 해당 Case 상태와 업무 closure 정보, audit/audit_events.jsonl의 append-only event", "고객의 savings, DSR, 고정지출, 상태, historical outcome, 선정 순위, queue 포함 여부, 실제 Alert"),
            ("Record Action", "Demo Case의 RM action 기록과 audit event. 예: Contact planned", "금융 승인/거절/재조정/상품 판매 결정, intervention efficacy, 고객 결과"),
            ("Notification Preview", "화면의 preview request/feedback만. Case와 audit에는 새 기록이 생기지 않음", "외부 provider, credential, network, 실제 메시지, sent 상태"),
        ),
    )
    _add_callout(
        document,
        "한 문장으로 설명하기",
        "우리는 RM이 어떤 evidence를 보고 어떤 업무 상태를 남길 수 있는지는 시연하지만, RM action이 고객의 재무 데이터, "
        "선정 결과 또는 미래 outcome을 바꾼다고 주장하지 않습니다.",
        color="FFF1F3",
    )

    document.add_heading("22.1 Action별 확인 포인트", level=2)
    _add_table(
        document,
        ("동작", "Case 상태", "Audit", "발표에서 확인할 것"),
        (
            ("Acknowledge", "NEW -> ACKNOWLEDGED", "1건 append", "담당자가 Case를 인지했다는 업무 상태만 변경"),
            ("Start Review", "ACKNOWLEDGED -> IN_REVIEW", "1건 append", "고객 재무 분석을 재계산하지 않는지"),
            ("Set Follow-up", "IN_REVIEW -> FOLLOW_UP", "1건 append", "권장 후속조치는 제안이며 자동 금융결정이 아님"),
            ("Record Action", "상태 유지", "1건 append", "예: Contact planned 기록. 고객 outcome 변경 없음"),
            ("Close", "CLOSED", "1건 append", "Case outcome과 analytical final_outcome은 별개"),
            ("Preview", "변경 없음", "변경 없음", "not sent, network=0을 함께 말함"),
            ("Reset", "3건 모두 NEW", "demo audit 초기화", "기본 RM과 5,000명 funnel이 그대로인지 확인"),
        ),
    )

    document.add_heading("22.2 실제 화면으로 보는 RM Action 전·후", level=2)
    document.add_paragraph(
        "Acknowledge는 이 합성 Case를 인지했다는 업무 상태만 남깁니다. 아래 비교에서 핵심은 ‘상태와 audit은 변하지만, "
        "분석·선정·고객 재무 데이터는 그대로’라는 점입니다. 이 비교는 실제 Edge 화면 crop에 교육용 라벨을 더한 것입니다."
    )
    before_after = annotations.get("workflow_demo_before_after")
    if before_after is not None and before_after.exists():
        _add_picture(
            document,
            before_after,
            "그림 13. 실제 Edge 화면 crop 비교 — NEW에서 ACKNOWLEDGED로, 분리된 demo audit 0건에서 1건으로만 바뀝니다.",
            width=6.85,
        )
    workflow_ack = screens.get("workflow_demo_ack")
    if workflow_ack is not None and workflow_ack.exists():
        _add_picture(
            document,
            workflow_ack,
            "화면 14. 실제 Edge 화면 — Acknowledge 후: 성공 메시지, 현재 상태, 그리고 append-only Activity/Audit 행을 함께 확인합니다.",
            width=6.85,
        )
    _add_callout(
        document,
        "교육자가 반드시 물어볼 질문",
        "‘이 클릭 뒤에 고객의 저축률·DSR·선정 순위·historical outcome·5,000명 funnel 중 무엇이 바뀌었나요?’ 정답은 ‘아무 것도 바뀌지 않았습니다’입니다. "
        "변경 대상은 분리된 demo Case 상태와 audit뿐입니다.",
        color="EAF2FB",
    )

    document.add_heading("23. 운영자용 시연 절차", level=1)
    document.add_paragraph(
        "아래 순서는 발표자와 내부 검토자가 동일한 상태를 재현하기 위한 절차입니다. 실제 발표 전에 1366x768 또는 "
        "1920x1080 Edge에서 직접 실행하여 캡처와 문구를 확인합니다. 이 문서에는 loopback-only 임시 Edge 캡처가 포함되어 있지만, "
        "실제 발표 장비에서 사람이 수행하는 수동 리허설은 아직 NOT_RUN입니다. 따라서 매뉴얼은 READY_WITH_WARNINGS 상태를 정직하게 유지합니다."
    )
    steps = (
        ("1", "03_run_app.bat 실행", "일반, 발표, RM의 세 모드가 보이는지 확인합니다. 기본 RM은 먼저 열지 않아도 됩니다."),
        ("2", "기본 RM Portfolio 확인", "열린 Alert 없음, RM 업무 Case 0, 선정됨·Case 미생성이 정상 안전 상태임을 확인하고 필요하면 캡처합니다."),
        ("3", "Portfolio와 Customer Review 시연", "5,000명 funnel, C000001의 선정 이유와 Why Now를 먼저 보여줍니다. Historical landmark는 별도 과거 근거로 설명합니다."),
        ("4", "Open Synthetic Workflow Demo 선택", "RM 내부의 명시적 진입을 누릅니다. Synthetic, not live, not sent/Preview only 경고를 먼저 읽습니다."),
        ("5", "Initialize synthetic Cases 선택", "정확히 3건만 생성되는지, 세 Case가 NEW인지, C000001이 첫 Case로 선택되는지 확인합니다."),
        ("6", "Case 1 업무 흐름", "Acknowledge -> Start Review -> Set Follow-up 또는 Record Action -> Close 순으로 시연합니다. 각 클릭 후 상태와 activity/audit이 같이 갱신되는지 봅니다."),
        ("7", "Recommended Follow-up 검토", "follow-up은 검토/연락/관찰/의뢰를 제안할 뿐 승인/거절/재조정 결정을 자동 실행하지 않는다고 말합니다."),
        ("8", "Notification Preview 열기", "Preview body와 deep-link context만 확인합니다. channel selector, sent 결과, network 호출이 없어야 합니다."),
        ("9", "Activity/Audit 확인", "시간 순서의 append-only history와 현재 Case 상태가 일치하는지 확인합니다."),
        ("10", "Reset 실행", "세 Case가 다시 NEW가 되고 demo audit이 초기화되는 것을 확인합니다. Reset은 demo runtime에만 적용됩니다."),
        ("11", "Return to default RM workspace", "demo session key만 정리됩니다. 기본 RM의 Alert/Case=0과 선정 funnel이 그대로인지 확인합니다."),
        ("12", "리허설 기록", "화면 크기, 언어(KR/EN), 담당자, 결과(PASS/FAIL), 발견한 문구/viewport 이슈를 기록합니다."),
    )
    _add_table(document, ("순서", "화면/동작", "확인할 내용"), steps)

    document.add_page_break()
    document.add_heading("23.1 캡처를 이용한 내부 교육 진행법", level=2)
    document.add_paragraph(
        "화면을 순서대로 넘기며 설명하면, 교육 대상자가 ‘기본 RM의 0 Case’와 ‘격리 Demo의 3 Case’를 혼동하지 않습니다. "
        "캡처는 교육용 증거이며 실제 고객 업무 처리 기록이 아닙니다."
    )
    training_steps = (
        ("1분", "화면 12", "진입만으로는 Case가 생기지 않음을 읽습니다. synthetic/not live/not sent 경고와 초기화 버튼을 함께 확인합니다."),
        ("1분", "화면 13", "C000001 / NEW와 최대 3건 고정 fixture를 확인합니다. 이 세 Case는 5,000명 전체를 새로 선별한 결과가 아닙니다."),
        ("1분", "그림 13 + 화면 14", "NEW→ACKNOWLEDGED 및 audit 0→1만 찾게 합니다. ‘변하지 않은 데이터’를 교육 대상자가 직접 말하게 합니다."),
        ("40초", "화면 16", "Offline Preview body와 deep-link context만 확인합니다. sent, channel selector, network는 없다고 명시합니다."),
        ("40초", "기본 RM 화면", "Return/Reset 뒤 기본 Portfolio의 Alert=0, Case=0, 선정됨·Case 미생성이 계속 정상임을 다시 확인합니다."),
    )
    _add_table(document, ("권장 시간", "사용할 화면", "교육 진행 문장"), training_steps)
    workflow_preview = screens.get("workflow_demo_preview")
    if workflow_preview is not None and workflow_preview.exists():
        _add_picture(
            document,
            workflow_preview,
            "화면 16. 실제 Edge 화면 — Offline Preview: not sent와 network/전달 채널 미사용 문구, deep-link context만 보입니다.",
            width=6.85,
        )

    document.add_heading("24. 내부 공유용 발표 흐름", level=1)
    document.add_paragraph(
        "평가 피드백의 핵심은 슬라이드보다 앱을 더 많이 보여주고, 분석 insight가 RM 업무 흐름으로 이어지는 모습을 "
        "명확하게 만드는 것입니다. 아래 순서는 분석의 강점을 유지하면서도 workflow를 과장하지 않는 2분 30초 내외의 "
        "앱 중심 시연안입니다."
    )
    _add_picture(
        document,
        diagrams["workflow_demo_presentation"],
        "그림 12. 5,000명 population에서 Workflow Demo까지 이어지는 내부 발표 흐름. 실제 UI 캡처가 아니라 발표 순서를 설명하는 운영 다이어그램입니다.",
        width=6.9,
    )
    document.add_page_break()
    _add_table(
        document,
        ("시간", "앱 화면", "핵심 문장", "피해야 할 주장"),
        (
            ("0:00-0:20", "RM Portfolio", "한 명의 이야기가 아니라 5,000명 전체 분석에서 시작합니다.", "1,522명이 실제 RM 업무량이다."),
            ("0:20-0:35", "Capacity 비교", "사람이 입력한 capacity에서 Selected/Deferred trade-off를 비교합니다.", "시스템이 적정 인력이나 SLA를 결정한다."),
            ("0:35-0:55", "Customer Review C000001", "왜 이 고객이 선정됐고 왜 지금 검토해야 하는지 현재/과거 evidence로 설명합니다.", "historical landmark가 이 고객의 미래 날짜를 예측한다."),
            ("0:55-1:25", "Synthetic Workflow Demo", "별도 runtime에서 3개 synthetic Case의 action, audit, preview를 시연합니다.", "실제 고객 Alert를 생성하거나 메시지를 발송했다."),
            ("1:25-1:45", "C000008/C000010과 Reset", "고정 fixture, idempotent action, reset 후 기본 RM 보존을 보여줍니다.", "RM action이 outcome을 개선했다."),
            ("1:45-2:10", "Presentation C002608", "weighted nearest-neighbour cohort, historical landmark, rule-based What-if의 분석 근거를 보여줍니다.", "historical outcome share를 prediction probability로 부른다."),
            ("2:10-2:30", "한계와 다음 검증", "synthetic PoC이며 governance, approved data adapter, RM pilot은 준비 또는 미검증 상태입니다.", "실제 은행 성과나 실제 고객 검증이 완료됐다."),
        ),
    )

    document.add_heading("25. 내부 Q&A와 증거 정리", level=1)
    _add_table(
        document,
        ("예상 질문", "정직한 답변", "바로 보여줄 증거"),
        (
            ("왜 기본 RM은 Alert/Case가 0개인가?", "Triage selection과 Alert creation을 분리한 안전 기본값입니다. 화면 탐색만으로 Case가 생성되지 않습니다.", "RM Portfolio의 0 Case와 섹션 18-19"),
            ("Workflow Demo의 버튼은 무엇을 바꾸나?", "분리된 synthetic Case 상태와 demo audit만 바꿉니다. 분석, ranking, 고객 재무 데이터는 바꾸지 않습니다.", "그림 11과 섹션 22"),
            ("알림을 실제로 보냈나?", "아닙니다. Preview/Null만 있으며 sent=false, network=0입니다.", "Preview panel과 activity/audit"),
            ("왜 3건만 보여주나?", "작고 재현 가능한 offline workflow fixture입니다. 5,000명 전체 selection 증거와 별도로 workflow 계약을 시연합니다.", "Portfolio funnel과 섹션 21.1"),
            ("RM action이 고객 결과를 바꾸나?", "이 PoC는 업무 흐름과 evidence usability를 시연합니다. intervention efficacy와 실제 RM 성과는 검증하지 않았습니다.", "섹션 22, 24의 한계 문구"),
        ),
    )
    capture_note = document.add_paragraph()
    capture_note_run = capture_note.add_run(
        "캡처 정직성: 기존 app screen PNG와 화면 12·13·14·16은 loopback-only 임시 Edge 프로필에서 캡처했습니다. "
        "화면 12·13·14·16은 immutable workspace fixture와 임시 synthetic runtime만 사용했고, 기본 workflow/audit 및 workspace fixture 경로를 전·후 해시로 확인했습니다. "
        "그림 11–12는 운영 다이어그램, 그림 13은 실제 화면 crop에 교육용 라벨을 더한 비교 이미지입니다. 실제 발표 장비에서의 사람이 수행하는 수동 리허설은 별도로 기록해야 합니다."
    )
    capture_note_run.italic = True
    capture_note_run.font.size = Pt(9)
    capture_note_run.font.color.rgb = RGBColor(93, 107, 120)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docx-only",
        action="store_true",
        help="Regenerate the Word operating manual without rewriting the existing Excel summary.",
    )
    parser.add_argument(
        "--output-docx",
        type=Path,
        help="Write the Word manual to this alternate path instead of replacing the default manual.",
    )
    parser.add_argument(
        "--try-capture-screens",
        action="store_true",
        help=(
            "Attempt bounded local Streamlit/Chrome screenshot capture. "
            "The default is offline diagrams and honest manual-capture guides."
        ),
    )
    parser.add_argument(
        "--try-edge-capture-screens",
        action="store_true",
        help=(
            "Open temporary visible Edge windows and capture three local app screens via loopback-only DevTools. "
            "Each app/browser session is bounded and terminated after capture."
        ),
    )
    parser.add_argument(
        "--edge-mode",
        choices=("presentation", "general", "rm"),
        help="Capture one named current Edge screen; useful when refreshing a single manual image.",
    )
    parser.add_argument(
        "--edge-scenario",
        choices=tuple(EDGE_SCENARIOS),
        help=(
            "Capture one bounded Edge evidence scenario, including a selected tab or the "
            "session-only human-capacity comparison. It never writes workflow or analytics artifacts."
        ),
    )
    parser.add_argument(
        "--try-edge-evidence-gallery",
        action="store_true",
        help=(
            "Capture the full bounded Edge evidence gallery for the detailed manual. "
            "Each temporary local Streamlit/Edge session is terminated after its PNG is saved."
        ),
    )
    parser.add_argument(
        "--try-edge-workflow-demo-timeline",
        action="store_true",
        help=(
            "Capture four Workflow Demo teaching states using a temporary loopback-only Edge profile and "
            "temporary synthetic runtime. The default workflow/audit, demo fixture, and analytics paths are "
            "digest-checked and never used as mutable capture output."
        ),
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    diagrams = create_diagrams()
    capture_cards = create_capture_cards()
    git_head, dirty = project_git_reference()
    screens: dict[str, Path] = {}
    known_screens = {
        "presentation": SCREEN_DIR / "01_presentation_mode.png",
        "general": SCREEN_DIR / "02_general_mode.png",
        "general_direct_c000001": SCREEN_DIR / "02a_general_direct_c000001.png",
        "rm": SCREEN_DIR / "03_rm_portfolio.png",
        "presentation_landmark": SCREEN_DIR / "04_presentation_historical_landmark.png",
        "presentation_whatif": SCREEN_DIR / "05_presentation_whatif.png",
        "rm_capacity_3": SCREEN_DIR / "06_rm_human_capacity_3.png",
        "rm_workflow_demo_entry_cta": SCREEN_DIR / "11a_rm_workflow_demo_entry_cta.png",
        "rm_queue": SCREEN_DIR / "07_rm_review_queue.png",
        "rm_customer_review": SCREEN_DIR / "08_rm_customer_review_c000001.png",
        "presentation_c002082_insufficient": SCREEN_DIR / "09_presentation_c002082_landmark_insufficient.png",
        "rm_monitor_c000003": SCREEN_DIR / "10_rm_monitor_c000003.png",
        "rm_queue_c000003_excluded": SCREEN_DIR / "11_rm_queue_c000003_excluded.png",
        "workflow_demo_entry": SCREEN_DIR / "12_workflow_demo_entry_uninitialized.png",
        "workflow_demo_new": SCREEN_DIR / "13_workflow_demo_new_before_action.png",
        "workflow_demo_ack": SCREEN_DIR / "14_workflow_demo_ack_after_action.png",
        "workflow_demo_preview": SCREEN_DIR / "16_workflow_demo_preview_not_sent.png",
    }
    screens = {key: path for key, path in known_screens.items() if path.exists()}
    if args.try_edge_workflow_demo_timeline:
        try:
            screens.update(capture_workflow_demo_timeline_with_edge())
        except (OSError, RuntimeError, subprocess.SubprocessError, websocket.WebSocketException) as error:
            print(f"WARNING: Workflow Demo Edge timeline capture was skipped: {error}")
            print("The manual retains existing captures and clearly-labelled workflow diagrams.")
    elif args.edge_scenario:
        try:
            mode_value, filename, interaction_scripts = EDGE_SCENARIOS[args.edge_scenario]
            screens[args.edge_scenario] = _capture_one_edge_screen(
                mode=mode_value,
                filename=filename,
                interaction_scripts=interaction_scripts,
                session_capacity=EDGE_SCENARIO_SESSION_CAPACITY.get(args.edge_scenario),
                session_customer_id=EDGE_SCENARIO_SESSION_CUSTOMER.get(args.edge_scenario),
                session_direct_input_customer_id=EDGE_SCENARIO_DIRECT_INPUT_CUSTOMER.get(args.edge_scenario),
                session_presentation_option=EDGE_SCENARIO_PRESENTATION_OPTION.get(args.edge_scenario),
                session_representative_category=EDGE_SCENARIO_REPRESENTATIVE_CATEGORY.get(args.edge_scenario),
                session_queue_search=EDGE_SCENARIO_QUEUE_SEARCH.get(args.edge_scenario),
            )
        except (OSError, RuntimeError, subprocess.SubprocessError, websocket.WebSocketException) as error:
            print(f"WARNING: Edge evidence capture was skipped: {error}")
            print("The manual retains its clearly-labelled diagram and existing-screen guidance.")
    elif args.try_edge_evidence_gallery:
        try:
            screens = capture_evidence_screens_with_edge()
        except (OSError, RuntimeError, subprocess.SubprocessError, websocket.WebSocketException) as error:
            print(f"WARNING: Edge evidence gallery capture was skipped: {error}")
            print("The manual retains its clearly-labelled diagram and existing-screen guidance.")
    elif args.edge_mode:
        mode_values = {
            "presentation": (APP_MODE_PRESENTATION, "01_presentation_mode.png"),
            "general": (APP_MODE_GENERAL, "02_general_mode.png"),
            "rm": (APP_MODE_RM, "03_rm_portfolio.png"),
        }
        try:
            mode_value, filename = mode_values[args.edge_mode]
            screens[args.edge_mode] = _capture_one_edge_screen(mode=mode_value, filename=filename)
        except (OSError, RuntimeError, subprocess.SubprocessError, websocket.WebSocketException) as error:
            print(f"WARNING: Edge live screen capture was skipped: {error}")
            print("The manual contains clearly-labelled manual capture guides instead.")
    elif args.try_edge_capture_screens:
        try:
            screens = capture_screens_with_edge()
        except (OSError, RuntimeError, subprocess.SubprocessError, websocket.WebSocketException) as error:
            print(f"WARNING: Edge live screen capture was skipped: {error}")
            print("The manual contains clearly-labelled manual capture guides instead.")
    elif args.try_capture_screens:
        try:
            screens = capture_screens()
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            print(f"WARNING: live screen capture was skipped: {error}")
            print("The manual contains clearly-labelled manual capture guides instead.")
    annotations = create_manual_annotations(screens)
    document_path = create_document(
        diagrams,
        capture_cards,
        annotations,
        screens,
        git_head=git_head,
        dirty=dirty,
        output_path=args.output_docx,
    )
    workbook_path: Path | None = None
    if not args.docx_only:
        workbook_path = create_workbook(diagrams, capture_cards, annotations, screens, git_head=git_head, dirty=dirty)
    print(f"Word manual: {document_path}")
    if workbook_path is not None:
        print(f"Excel summary: {workbook_path}")
    for key, path in screens.items():
        print(f"Screen capture ({key}): {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
