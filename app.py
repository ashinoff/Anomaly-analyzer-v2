"""
Streamlit-приложение: анализ аномального потребления.
Стиль: editorial data publication — bone bg · ink fg · rust accent · moss for ok.
Шрифты: Instrument Serif (display) · Geist (text) · JetBrains Mono (data).
"""
import streamlit as st
import pandas as pd
import numpy as np
import io
import plotly.graph_objects as go

from analyzer import (
    analyze, DEFAULT_CONFIG, FLAG_DEFINITIONS,
    detect_month_columns, MONTHS_RU
)
from excel_export import build_full_report, build_subscriber_card

st.set_page_config(
    page_title="Анализ потребления",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================
# ЛОКАЛИЗАЦИЯ
# =====================================================================
METRIC_LABELS = {
    'active_months':    'Активных месяцев',
    'mean_kwh':         'Среднее, кВт·ч/мес',
    'total_kwh':        'Всего, кВт·ч',
    'max_kwh':          'Пиковый месяц, кВт·ч',
    'avg_recent':       'Среднее в недавнем периоде',
    'avg_baseline':     'Среднее в опорном периоде',
    'drop_ratio':       'Доля падения',
    'longest_silence':  'Макс. пауза в показаниях, мес.',
    'longest_flat_run': 'Макс. серия одинаковых, мес.',
    'power_ratio':      'Отношение пиковой/разрешённой',
    'cohort_z':         'Z-оценка в когорте',
    'сезонность':       'Сезонность',
    'мало_данных':      'Мало данных',
    'кол-во_флагов':    'Кол-во флагов',
}

FLAG_EMOJI = {
    'подозрение_хищение':   '▼',   # треугольник вниз — падение
    'долгое_молчание':      '◌',   # пунктирный круг — нет данных
    'превышение_мощности':  '▲',   # треугольник вверх — превышение
    'нестабильность':       '~',   # волна — нестабильно
    'одинаковые_подряд':    '▦',   # сетка — повторение
    'аномалия_в_когорте':   '◆',   # ромб — выбивается
}

FLAG_TITLES = {
    'подозрение_хищение':   'Подозрение на хищение',
    'долгое_молчание':      'Долгое молчание ПУ',
    'превышение_мощности':  'Превышение мощности',
    'нестабильность':       'Нестабильность',
    'одинаковые_подряд':    'Одинаковые подряд',
    'аномалия_в_когорте':   'Аномалия в когорте',
}

FLAG_COLOR = {
    'подозрение_хищение':   '#B5432C',  # rust — основной флаг риска
    'долгое_молчание':      '#4A5A6B',  # slate
    'превышение_мощности':  '#C7873A',  # amber
    'нестабильность':       '#5A6B3D',  # moss
    'одинаковые_подряд':    '#6B3F5F',  # plum
    'аномалия_в_когорте':   '#8C2F1E',  # rust-deep
}

# =====================================================================
# СТИЛИ
# =====================================================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bone:        #F2EDE2;
    --bone-deep:   #ECE5D5;
    --paper:       #FBF8F1;
    --ink:         #181513;
    --ink-soft:    #3A332C;
    --ink-dim:     #6F6557;
    --ink-faint:   #A89E8C;
    --rule:        #D4CCBA;
    --rule-soft:   #E2DBC8;
    --rust:        #B5432C;
    --rust-deep:   #8C2F1E;
    --rust-soft:   #F2D9CF;
    --moss:        #5A6B3D;
    --amber:       #C7873A;
    --plum:        #6B3F5F;
    --slate:       #4A5A6B;

    --display: 'Instrument Serif', 'Times New Roman', serif;
    --sans: 'Geist', system-ui, sans-serif;
    --mono: 'JetBrains Mono', ui-monospace, monospace;
}

/* base */
.stApp { background: var(--bone) !important; }
html, body, [class*="css"], .stApp, .stApp * {
    font-family: var(--sans);
    color: var(--ink);
}
header[data-testid="stHeader"] { background: transparent !important; height: 0; }
.stDeployButton, #MainMenu, footer { display: none !important; }
.block-container { padding-top: 1.4rem !important; max-width: 1400px; }

h1, h2, h3 { font-family: var(--display) !important; font-weight: 400; letter-spacing: -0.01em; color: var(--ink); }
h1 { font-size: 2.6rem !important; line-height: 1; }
h2 { font-size: 1.6rem !important; }
.mono { font-family: var(--mono) !important; }

/* ========= HERO (editorial masthead) ========= */
.hero {
    border-top: 3px solid var(--ink);
    border-bottom: 1px solid var(--ink);
    padding: 1.4rem 0 1rem;
    margin: 0.4rem 0 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 2rem;
    font-family: var(--mono);
    font-size: 0.66rem;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--ink-dim);
}
.hero .brand { display: flex; align-items: baseline; gap: 14px; }
.hero .brand-mark {
    font-family: var(--display) !important;
    font-style: italic;
    font-size: 1.6rem;
    letter-spacing: -0.005em;
    color: var(--ink) !important;
    text-transform: none;
}
.hero .brand-tag { border-left: 1px solid var(--rule); padding-left: 14px; color: var(--ink-dim); }
.hero .meta { display: flex; gap: 28px; }
.hero .meta b { color: var(--ink); font-weight: 500; }

.headline {
    padding: 0 0 1.6rem;
    border-bottom: 1px solid var(--ink);
    margin-bottom: 1.6rem;
}
.headline h1 {
    font-family: var(--display) !important;
    font-weight: 400 !important;
    font-size: clamp(3rem, 6vw, 5.4rem) !important;
    line-height: 0.94 !important;
    letter-spacing: -0.012em !important;
    margin: 0 !important;
    color: var(--ink) !important;
    text-transform: none !important;
}
.headline h1 em {
    font-style: italic;
    color: var(--rust);
    font-weight: 400;
}
.headline .deck {
    font-family: var(--display) !important;
    font-style: italic;
    font-size: 1.15rem;
    line-height: 1.35;
    color: var(--ink-soft);
    border-left: 2px solid var(--ink);
    padding: 0.2rem 0 0.2rem 0.9rem;
    margin-top: 1.2rem;
    max-width: 560px;
}

/* ========= KPI strip ========= */
.metric-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border-top: 1px solid var(--ink);
    border-bottom: 1px solid var(--ink);
    margin: 1.6rem 0 2rem;
}
.metric-cell {
    padding: 1.2rem 1.4rem 1.4rem;
    border-right: 1px solid var(--rule);
    background: transparent;
}
.metric-cell:last-child { border-right: none; }
.metric-label {
    font-family: var(--mono) !important;
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--ink-dim);
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 500;
}
.metric-label::before {
    content: '';
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--cell-accent, var(--ink));
    display: inline-block;
}
.metric-value {
    font-family: var(--display) !important;
    font-weight: 400;
    font-size: 3.6rem;
    line-height: 1;
    letter-spacing: -0.015em;
    color: var(--ink);
    margin-top: 0.9rem;
    font-variant-numeric: tabular-nums;
}
.metric-value.rust  { color: var(--rust); }
.metric-value.amber { color: var(--amber); }
.metric-value.moss  { color: var(--moss); }

/* ========= Section heads ========= */
.section-label {
    font-family: var(--mono) !important;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--rust);
    margin: 1.6rem 0 0.4rem 0;
    font-weight: 500;
}
.section-title {
    font-family: var(--display) !important;
    font-weight: 400;
    font-size: 2rem;
    line-height: 1.05;
    color: var(--ink);
    margin: 0.1rem 0 1.2rem 0;
    padding-bottom: 0.6rem;
    border-bottom: 1px solid var(--ink);
    letter-spacing: -0.01em;
}
.section-title em { font-style: italic; color: var(--rust); }

/* ========= Flags ========= */
.flag-row {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 0.7rem 0.9rem;
    margin-bottom: 0.5rem;
    background: var(--paper);
    border-left: 3px solid var(--flag-color, var(--rust));
}
.flag-row .emoji {
    font-family: var(--mono) !important;
    font-size: 0.95rem;
    color: var(--flag-color, var(--rust));
    font-weight: 600;
}
.flag-row .name {
    font-family: var(--sans);
    font-weight: 500;
    color: var(--ink);
    font-size: 0.92rem;
}
.flag-empty {
    padding: 0.9rem 1.1rem;
    color: var(--moss);
    background: var(--paper);
    border-left: 3px solid var(--moss);
    font-weight: 500;
    font-family: var(--sans);
}

/* ========= KV list ========= */
.kv-list {
    font-family: var(--sans);
    border-top: 1px solid var(--rule);
}
.kv-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 0.55rem 0;
    border-bottom: 1px dashed var(--rule);
    gap: 1rem;
}
.kv-key { color: var(--ink-dim); font-size: 0.84rem; }
.kv-val {
    font-family: var(--mono) !important;
    font-size: 0.86rem;
    color: var(--ink);
    text-align: right;
    font-weight: 500;
    word-break: break-word;
    font-variant-numeric: tabular-nums;
}

/* ========= Tabs ========= */
.stTabs [data-baseweb="tab-list"] {
    gap: 28px;
    border-bottom: 1px solid var(--ink);
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    font-family: var(--display) !important;
    font-size: 1.4rem !important;
    font-weight: 400;
    text-transform: none;
    letter-spacing: -0.005em;
    padding: 0.7rem 0;
    color: var(--ink-dim);
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--ink); }
.stTabs [aria-selected="true"] {
    color: var(--ink) !important;
    border-bottom-color: var(--rust) !important;
}

/* ========= Sidebar ========= */
[data-testid="stSidebar"] {
    background: var(--bone-deep) !important;
    border-right: 1px solid var(--rule);
}
[data-testid="stSidebar"] h1 {
    font-family: var(--display) !important;
    font-size: 1.9rem !important;
    font-weight: 400;
    color: var(--ink);
    margin-bottom: 0.2rem;
    text-transform: none;
    letter-spacing: -0.01em;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: transparent;
    border: 0;
    border-top: 1px solid var(--ink);
    border-radius: 0;
    margin-bottom: 0;
}
[data-testid="stSidebar"] [data-testid="stExpander"]:last-of-type { border-bottom: 1px solid var(--ink); }
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    font-family: var(--sans) !important;
    font-weight: 500;
    color: var(--ink);
    padding: 0.8rem 0 !important;
}

/* sliders — ink */
.stSlider [data-baseweb="slider"] > div > div > div {
    background: var(--ink) !important;
}
.stSlider [role="slider"] {
    background-color: var(--ink) !important;
    border-color: var(--bone-deep) !important;
    box-shadow: 0 0 0 3px rgba(24, 21, 19, 0.12) !important;
}
.stSlider [data-baseweb="tooltip"] > div {
    background: var(--ink) !important;
    color: var(--paper) !important;
    font-family: var(--mono) !important;
    font-weight: 600;
}

/* number input */
.stNumberInput input {
    background: var(--paper) !important;
    color: var(--ink) !important;
    border: 1px solid var(--rule) !important;
    border-radius: 0 !important;
    font-family: var(--mono) !important;
}

/* select */
.stSelectbox > div > div, .stMultiSelect > div > div {
    background: var(--paper) !important;
    border: 1px solid var(--rule) !important;
    border-radius: 0 !important;
}

/* ========= Buttons ========= */
.stDownloadButton button, .stButton button,
[data-testid="stDownloadButton"] button,
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-primary"] {
    background: var(--ink) !important;
    color: var(--paper) !important;
    border: none !important;
    font-family: var(--mono) !important;
    font-weight: 500 !important;
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    padding: 0.85rem 1.6rem !important;
    border-radius: 0 !important;
    transition: background 0.15s;
}
.stDownloadButton button *, .stButton button *,
[data-testid="stDownloadButton"] button * {
    color: var(--paper) !important;
}
.stDownloadButton button:hover, .stButton button:hover,
[data-testid="stDownloadButton"] button:hover {
    background: var(--rust) !important;
}

/* hide material icons */
.material-icons, .material-icons-outlined, .material-symbols-outlined,
[class*="material-icons"], [class*="material-symbols"],
[data-testid="stIconMaterial"], [data-testid*="ToggleIcon"] {
    font-size: 0 !important;
    visibility: hidden !important;
    width: 0 !important; height: 0 !important;
    margin: 0 !important; padding: 0 !important;
    overflow: hidden !important;
    display: inline-block !important;
}
[data-testid="stExpander"] details > summary { position: relative; padding-right: 1.8rem !important; }
[data-testid="stExpander"] details > summary::after {
    content: "+";
    position: absolute; right: 0.8rem; top: 50%;
    transform: translateY(-50%);
    color: var(--ink-dim);
    font-family: var(--mono) !important;
    font-size: 1rem;
    visibility: visible !important;
    width: auto !important; height: auto !important;
}
[data-testid="stExpander"] details[open] > summary::after { content: "−"; }

/* file uploader */
[data-testid="stFileUploaderDropzone"] {
    background: var(--paper) !important;
    border: 1.5px dashed var(--ink) !important;
    border-radius: 0 !important;
    padding: 1.4rem 1.8rem !important;
    min-height: 90px !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--rust) !important;
    background: #fff !important;
}
section[data-testid="stFileUploaderDropzone"] > button,
[data-testid="stFileUploaderDropzone"] > button {
    background: var(--ink) !important;
    color: transparent !important;
    border: none !important;
    padding: 0 !important;
    width: 150px !important;
    height: 42px !important;
    min-width: 150px !important;
    position: relative !important;
    overflow: hidden !important;
    border-radius: 0 !important;
    cursor: pointer !important;
    font-size: 0 !important;
}
section[data-testid="stFileUploaderDropzone"] > button > *,
[data-testid="stFileUploaderDropzone"] > button > * {
    visibility: hidden !important;
}
section[data-testid="stFileUploaderDropzone"] > button::after,
[data-testid="stFileUploaderDropzone"] > button::after {
    content: "ЗАГРУЗИТЬ" !important;
    position: absolute !important;
    inset: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    color: #FBF8F1 !important;
    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    font-weight: 500 !important;
    font-size: 11px !important;
    letter-spacing: 0.18em !important;
    z-index: 2 !important;
    pointer-events: none !important;
    visibility: visible !important;
}
section[data-testid="stFileUploaderDropzone"] > button:hover,
[data-testid="stFileUploaderDropzone"] > button:hover {
    background: var(--rust) !important;
}

[data-testid="stFileUploaderDropzoneInstructions"] {
    font-size: 0 !important;
    position: relative !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] > * { display: none !important; }
[data-testid="stFileUploaderDropzoneInstructions"]::before {
    content: "Перетащите Excel-выгрузку сюда";
    display: block !important;
    font-family: var(--display) !important;
    font-style: italic;
    font-size: 1.4rem !important;
    color: var(--ink) !important;
    text-indent: 0 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"]::after {
    content: "XLSX · XLS · ДО 200 МБ";
    display: block !important;
    font-family: var(--mono) !important;
    font-size: 0.62rem !important;
    color: var(--ink-dim) !important;
    margin-top: 0.5rem;
    letter-spacing: 0.2em;
    text-indent: 0 !important;
    text-transform: uppercase;
}

/* uploaded file block */
[data-testid="stFileUploader"] svg,
[data-testid="stFileUploaderFile"] *,
[data-testid="stFileUploaderUploadedFile"] *,
[data-testid="stFileUploaderDeleteBtn"] * {
    visibility: visible !important;
}
[data-testid="stFileUploaderFile"],
[data-testid="stFileUploaderUploadedFile"] {
    background: var(--paper) !important;
    border: 1px solid var(--rule) !important;
    border-radius: 0 !important;
    padding: 0.6rem 0.9rem !important;
    margin-top: 0.6rem !important;
    display: flex !important;
    align-items: center !important;
}

[data-testid="stFileUploaderDeleteBtn"],
button[data-testid="stFileUploaderDeleteBtn"],
[data-testid="stFileUploaderFile"] button,
[data-testid="stFileUploaderUploadedFile"] button {
    visibility: visible !important;
    display: inline-flex !important;
    width: 36px !important; height: 36px !important;
    min-width: 36px !important;
    padding: 0 !important;
    margin-left: 8px !important;
    background: transparent !important;
    border: 1px solid var(--rust) !important;
    border-radius: 0 !important;
    color: var(--rust) !important;
    position: relative !important;
    text-indent: -9999px !important;
    overflow: hidden !important;
    cursor: pointer !important;
    flex-shrink: 0 !important;
}
[data-testid="stFileUploaderDeleteBtn"] *,
[data-testid="stFileUploaderFile"] button > *,
[data-testid="stFileUploaderUploadedFile"] button > * { display: none !important; }
[data-testid="stFileUploaderDeleteBtn"]::after,
[data-testid="stFileUploaderFile"] button::after,
[data-testid="stFileUploaderUploadedFile"] button::after {
    content: "✕";
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    display: flex !important;
    align-items: center; justify-content: center;
    color: var(--rust) !important;
    font-family: var(--mono) !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
    text-indent: 0 !important;
    visibility: visible !important;
}
[data-testid="stFileUploaderDeleteBtn"]:hover,
[data-testid="stFileUploaderFile"] button:hover,
[data-testid="stFileUploaderUploadedFile"] button:hover { background: var(--rust) !important; }
[data-testid="stFileUploaderDeleteBtn"]:hover::after,
[data-testid="stFileUploaderFile"] button:hover::after,
[data-testid="stFileUploaderUploadedFile"] button:hover::after { color: var(--paper) !important; }

/* dataframe */
[data-testid="stDataFrame"] {
    border: 1px solid var(--ink);
    border-radius: 0;
}

/* expander */
[data-testid="stExpander"] {
    border: 1px solid var(--rule);
    border-radius: 0;
    background: var(--paper);
}

/* pills */
.pill {
    display: inline-block;
    padding: 0.22rem 0.7rem;
    border-radius: 0;
    font-family: var(--mono) !important;
    font-size: 0.7rem;
    margin: 0.18rem 0.22rem 0.18rem 0;
    border: 1px solid var(--rule);
    background: var(--paper);
    color: var(--ink);
    letter-spacing: 0.04em;
}
.pill.found {
    color: var(--moss);
    border-color: var(--moss);
}

/* empty pull-quote */
.empty-state {
    border-top: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: 3.2rem 1rem 3.6rem;
    text-align: center;
    color: var(--ink-soft);
    font-family: var(--display) !important;
    font-size: 1.8rem;
    margin: 1.4rem 0;
    background: transparent;
    text-transform: none;
    letter-spacing: -0.005em;
    line-height: 1.3;
    font-style: italic;
}
.empty-state::before {
    content: "00";
    display: block;
    font-family: var(--display) !important;
    font-style: italic;
    font-size: 4.2rem;
    color: var(--rust);
    line-height: 1;
    margin-bottom: 1rem;
    letter-spacing: -0.02em;
}
.empty-state .small {
    text-transform: uppercase;
    font-family: var(--mono) !important;
    font-size: 0.66rem;
    color: var(--ink-dim);
    letter-spacing: 0.18em;
    display: block;
    margin-top: 1.2rem;
    font-weight: 500;
    font-style: normal;
}

/* footer */
.footer-strip {
    margin-top: 3rem;
    padding: 1rem 0 0.8rem;
    border-top: 1px solid var(--ink);
    font-family: var(--mono) !important;
    font-size: 0.62rem;
    color: var(--ink-dim);
    text-transform: uppercase;
    letter-spacing: 0.2em;
    text-align: center;
}

/* alerts */
.stAlert { border-radius: 0 !important; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# =====================================================================
# Plotly-тема (светлая, корпоративная)
# =====================================================================
PLOTLY_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family='Geist, sans-serif', color='#6F6557', size=11),
    xaxis=dict(gridcolor='#E2DBC8', linecolor='#181513', zerolinecolor='#D4CCBA',
               tickfont=dict(color='#6F6557', family='JetBrains Mono')),
    yaxis=dict(gridcolor='#E2DBC8', linecolor='#181513', zerolinecolor='#D4CCBA',
               tickfont=dict(color='#6F6557', family='JetBrains Mono')),
    margin=dict(l=10, r=10, t=20, b=10),
    showlegend=False,
)

INK    = '#181513'
RUST   = '#B5432C'
RUST_D = '#8C2F1E'
MOSS   = '#5A6B3D'
AMBER  = '#C7873A'
PLUM   = '#6B3F5F'
SLATE  = '#4A5A6B'
GRAY   = '#A89E8C'

# Aliases kept for legacy refs in this file (so old code paths still work)
NAVY   = INK
BLUE   = SLATE
RED    = RUST
ORANGE = AMBER
GREEN  = MOSS
PURPLE = PLUM

# =====================================================================
# САЙДБАР
# =====================================================================
with st.sidebar:
    st.markdown("# Настройки")
    st.markdown('<div style="color:var(--ink-dim);font-family:var(--display);font-style:italic;font-size:0.95rem;margin-bottom:1.2rem;">Подкручивайте — таблица пересчитается.</div>', unsafe_allow_html=True)

    with st.expander("Хищение", expanded=True):
        cfg_theft_drop = st.slider("Падение, %", 20, 95, 50, 5) / 100
        cfg_theft_recent = st.slider("Недавний период, мес.", 3, 24, 12)
        cfg_theft_baseline = st.slider("Опорный период, мес.", 6, 36, 24)
        cfg_theft_min = st.number_input("Мин. опорное, кВт·ч", 0, 10000, 50, 10)

    with st.expander("Молчание ПУ"):
        cfg_silence = st.slider("Подряд месяцев без показаний", 3, 24, 6)

    with st.expander("Превышение мощности"):
        cfg_power_ratio = st.slider("Порог пиковой/разрешённой", 0.5, 3.0, 1.0, 0.1)

    with st.expander("Нестабильность"):
        cfg_cv = st.slider("Коэфф. вариации", 0.3, 3.0, 1.2, 0.1)

    with st.expander("Одинаковые подряд"):
        cfg_flat = st.slider("Подряд одинаковых значений", 3, 24, 6)

    with st.expander("Аномалия в когорте"):
        cfg_z = st.slider("Robust z-score порог", 1.5, 5.0, 3.0, 0.1)

    with st.expander("Прочее"):
        cfg_min_active = st.slider("Мин. активных месяцев", 3, 36, 12)

config = {
    "theft_recent_months": cfg_theft_recent, "theft_baseline_months": cfg_theft_baseline,
    "theft_drop_pct": cfg_theft_drop, "theft_min_baseline_kwh": cfg_theft_min,
    "silence_months": cfg_silence, "power_overrun_ratio": cfg_power_ratio,
    "cv_threshold": cfg_cv, "flat_run_months": cfg_flat,
    "cohort_zscore": cfg_z, "min_active_months": cfg_min_active,
}

# =====================================================================
# ШАПКА (как обложка слайда Россети)
# =====================================================================
st.markdown(f"""
<div class="hero">
  <div class="brand">
    <span class="brand-mark">Analyzer</span>
    <span class="brand-tag">Энергоучёт · Россети Кубань</span>
  </div>
  <div class="meta">
    <span>Выпуск · <b>{pd.Timestamp.now().strftime('%d.%m.%Y')}</b></span>
    <span>Данные не сохраняются</span>
  </div>
</div>
<div class="headline">
  <h1>Анализ <em>аномального</em> потребления</h1>
  <div class="deck">Реестр абонентов с автоматическими флагами риска: хищения, долгое молчание ПУ, превышение мощности и нестабильность.</div>
</div>
""", unsafe_allow_html=True)

# =====================================================================
# ЗАГРУЗКА + СКАЧИВАНИЕ ОТЧЁТА (две колонки рядом)
# =====================================================================
@st.cache_data(show_spinner="Читаю файл…")
def load_excel(file_bytes):
    return pd.read_excel(io.BytesIO(file_bytes))

@st.cache_data(show_spinner="Анализирую…")
def run_analysis(file_bytes, config):
    df = load_excel(file_bytes)
    return df, *analyze(df, config)

upload_col, download_col = st.columns([3, 1])

with upload_col:
    uploaded = st.file_uploader(
        "Excel-файл с потреблением",
        type=['xlsx', 'xls'],
        label_visibility="collapsed",
    )

# Если файл не загружен — заглушка и стоп
if not uploaded:
    with download_col:
        st.markdown(
            '<div style="height:100%;display:flex;align-items:center;'
            'justify-content:center;color:var(--ink-faint);font-family:JetBrains Mono,monospace;'
            'font-size:0.66rem;text-transform:uppercase;letter-spacing:0.2em;'
            'border:1px dashed var(--rule);padding:1.2rem;text-align:center;'
            'min-height:90px;background:var(--paper);">Отчёт появится<br/>после загрузки</div>',
            unsafe_allow_html=True
        )

    st.markdown("""
    <div class="empty-state">
      «Все спокойно — пока вы не загрузите файл».
      <span class="small">Минимум — столбцы вида «Январь 2024», «Февраль 2024»…</span>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Какие колонки распознаются и как добавить флаг"):
        st.markdown("""
**Обязательно** — помесячные столбцы вида `Январь 2019`, `Февраль 2019` ... `Январь 2026`.

**Опционально** (без них часть флагов пропускается, но анализ работает):
- `Разрешенная мощность` — для флага «превышение мощности»
- `Вид потребителя` (ФИЗ/ЮР) — для «аномалия в когорте»
- `Заводской номер ПУ`, `Наименование точки учета`, адресные поля

**Какие флаги считаются:**
- ▼ Подозрение на хищение — резкое устойчивое падение
- ◌ Долгое молчание ПУ — длинные пропуски в показаниях
- ▲ Превышение мощности — пиковое потребление выше разрешённой
- ~ Нестабильность — высокий коэффициент вариации
- ▦ Одинаковые подряд — подозрение на ручной ввод «по нормативу»
- ◆ Аномалия в когорте — потребление сильно выше/ниже соседей
        """)
    st.stop()

# Файл загружен — анализируем
try:
    df_raw, registry, base, flags, report = run_analysis(uploaded.getvalue(), config)
except ValueError as e:
    st.error(f"Ошибка: {e}")
    st.stop()

# Готовим сводный отчёт и сразу же показываем кнопку скачивания
full_report_bytes = build_full_report(
    df_raw, registry, base, flags, report, config,
    FLAG_TITLES, FLAG_EMOJI, METRIC_LABELS,
    detect_month_columns(df_raw),
)

with download_col:
    st.download_button(
        "Скачать отчёт",
        data=full_report_bytes,
        file_name=f"анализ_потребления_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Сводный Excel: листы со сводкой, реестром, потреблением, по флагам и настройками",
        use_container_width=True,
    )

# =====================================================================
# ЛЕНТА МЕТРИК
# =====================================================================
n_with_flags = int((registry['кол-во_флагов'] > 0).sum())
n_high_risk = int((registry['кол-во_флагов'] >= 3).sum())

st.markdown(f"""
<div class="metric-strip">
  <div class="metric-cell" style="--cell-accent:var(--ink);">
    <div class="metric-label">Абонентов в файле</div>
    <div class="metric-value">{report['total_rows']:,}</div>
  </div>
  <div class="metric-cell" style="--cell-accent:var(--slate);">
    <div class="metric-label">Месяцев данных</div>
    <div class="metric-value">{report['months_detected']}</div>
  </div>
  <div class="metric-cell" style="--cell-accent:var(--amber);">
    <div class="metric-label">С флагами</div>
    <div class="metric-value amber">{n_with_flags:,}</div>
  </div>
  <div class="metric-cell" style="--cell-accent:var(--rust);">
    <div class="metric-label">Высокий риск (3+ флага)</div>
    <div class="metric-value rust">{n_high_risk:,}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# =====================================================================
# ОТЧЁТ О ЗАГРУЗКЕ
# =====================================================================
with st.expander(f"Период: {report['period_range']} · что распознано в файле", expanded=False):
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown('<div class="section-label">Найденные колонки</div>', unsafe_allow_html=True)
        pills = "".join(f'<span class="pill found">{v}</span>' for v in report['columns_found'].values())
        st.markdown(f'<div>{pills}</div>', unsafe_allow_html=True)
    with cc2:
        if report['flags_skipped']:
            st.markdown('<div class="section-label">Пропущенные флаги</div>', unsafe_allow_html=True)
            for f in report['flags_skipped']:
                st.markdown(
                    f'<div style="margin:0.3rem 0;font-size:0.88rem;">'
                    f'<span class="mono" style="color:var(--rust);font-weight:500;">{f["name"]}</span> '
                    f'<span style="color:var(--ink-dim);">— {f["reason"]}</span></div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown('<div class="section-label">Все флаги вычислены</div>', unsafe_allow_html=True)
            st.markdown('<div style="color:var(--moss);font-family:JetBrains Mono,monospace;font-weight:500;">✓ полный набор</div>', unsafe_allow_html=True)

# =====================================================================
# ВКЛАДКИ
# =====================================================================
tab_summary, tab_registry, tab_detail = st.tabs(["Сводка", "Реестр", "Абонент"])

# ----- СВОДКА -----
with tab_summary:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-label">Распределение</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">По числу флагов</div>', unsafe_allow_html=True)
        flag_counts = registry['кол-во_флагов'].value_counts().sort_index()
        # шкала: 0—песок, 1—чернила, 2—мох, 3—янтарь, 4+—ржавчина
        scale = {0: GRAY, 1: INK, 2: MOSS, 3: AMBER, 4: RUST, 5: RUST_D}
        colors = [scale.get(int(k), RED) for k in flag_counts.index]
        fig = go.Figure(go.Bar(
            x=flag_counts.index.astype(int).astype(str), y=flag_counts.values,
            text=flag_counts.values, textposition='outside',
            marker=dict(color=colors),
            textfont=dict(family='JetBrains Mono', color='#1A1F2C', size=12),
            hovertemplate='<b>%{x} флагов</b><br>%{y} абонентов<extra></extra>',
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=320,
                          xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    with col2:
        st.markdown('<div class="section-label">Срабатывание</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Каждого флага</div>', unsafe_allow_html=True)
        flag_names = [f['name'] for f in FLAG_DEFINITIONS if f['name'] in flags.columns]
        flag_data = sorted(
            [(FLAG_TITLES.get(n, n), int(flags[n].sum()), FLAG_COLOR.get(n, RED)) for n in flag_names],
            key=lambda x: x[1]
        )
        fig2 = go.Figure(go.Bar(
            y=[t for t, _, _ in flag_data],
            x=[v for _, v, _ in flag_data],
            text=[v for _, v, _ in flag_data],
            textposition='outside',
            orientation='h',
            marker=dict(color=[c for _, _, c in flag_data]),
            textfont=dict(family='JetBrains Mono', color='#181513', size=12),
            hovertemplate='<b>%{y}</b><br>%{x} абонентов<extra></extra>',
        ))
        fig2.update_layout(**PLOTLY_LAYOUT, height=320,
                           xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

    st.markdown('<div class="section-label">Сезонная классификация</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">По характеру потребления</div>', unsafe_allow_html=True)
    seas = registry['сезонность'].value_counts()
    season_color = {'круглогодичный': MOSS, 'летний (дача)': AMBER,
                    'зимний (отопление)': SLATE, 'нет данных': GRAY}
    fig3 = go.Figure(go.Bar(
        x=seas.index, y=seas.values, text=seas.values, textposition='outside',
        marker_color=[season_color.get(k, GRAY) for k in seas.index],
        textfont=dict(family='JetBrains Mono', color='#181513', size=12),
        hovertemplate='<b>%{x}</b><br>%{y} абонентов<extra></extra>',
    ))
    fig3.update_layout(**PLOTLY_LAYOUT, height=280,
                       xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig3, use_container_width=True, config={'displayModeBar': False})

# ----- РЕЕСТР -----
with tab_registry:
    st.markdown('<div class="section-label">Реестр</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Абоненты с флагами</div>', unsafe_allow_html=True)

    fc1, fc2, fc3 = st.columns([1, 1.2, 2])
    with fc1:
        min_flags = st.number_input("Мин. флагов", 0, 10, 1, 1)
    with fc2:
        seasons = ['(все)'] + list(registry['сезонность'].unique())
        season_filter = st.selectbox("Сезонность", seasons)
    with fc3:
        active_flag_filter = st.multiselect(
            "Только с этими флагами (И)",
            options=[c for c in flags.columns],
            format_func=lambda x: f"{FLAG_EMOJI.get(x,'')} {FLAG_TITLES.get(x, x)}",
        )

    view = registry[registry['кол-во_флагов'] >= min_flags].copy()
    if season_filter != '(все)':
        view = view[view['сезонность'] == season_filter]
    for fn in active_flag_filter:
        view = view[view[fn] == True]

    display_view = view.rename(columns={
        **METRIC_LABELS,
        **{k: f"{FLAG_EMOJI.get(k,'')} {FLAG_TITLES.get(k,k)}" for k in flags.columns},
    })

    st.markdown(
        f'<div style="font-family:JetBrains Mono,monospace;font-size:0.78rem;'
        f'color:var(--ink-dim);text-transform:uppercase;letter-spacing:0.18em;'
        f'margin:0.5rem 0 0.8rem 0;font-weight:500;">'
        f'Показано <span style="color:var(--rust);">{len(view):,}</span> из {len(registry):,} абонентов'
        f'</div>',
        unsafe_allow_html=True
    )
    st.dataframe(display_view, use_container_width=True, height=480)

    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine='openpyxl') as w:
        display_view.to_excel(w, index=False, sheet_name='Реестр')

    st.download_button(
        "Скачать только текущую выборку",
        data=excel_buf.getvalue(),
        file_name=f"выборка_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Только то, что отфильтровано выше. Сводный отчёт по всем флагам — кнопкой наверху страницы.",
    )

# ----- АБОНЕНТ -----
with tab_detail:
    st.markdown('<div class="section-label">Детальный просмотр</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">График и метрики абонента</div>', unsafe_allow_html=True)

    def label(idx):
        r = registry.loc[idx]
        parts = []
        for col in ['Заводской номер прибора учета', 'Наименование точки учета',
                    'Населенный пункт', 'Улица', 'Дом']:
            if col in r and pd.notna(r[col]):
                parts.append(str(r[col]))
        flags_n = int(r.get('кол-во_флагов', 0))
        suffix = f"  ⚑ {flags_n}" if flags_n else ""
        return f"#{idx} · {' · '.join(parts) if parts else 'без идентификатора'}{suffix}"

    sorted_idx = registry.sort_values('кол-во_флагов', ascending=False).index.tolist()
    selected = st.selectbox("Абонент", options=sorted_idx, format_func=label,
                            label_visibility="collapsed")

    if selected is not None:
        month_info = detect_month_columns(df_raw)
        month_cols = [c for (c, _, _) in month_info]
        periods = [pd.Period(f"{y}-{m:02d}", freq='M') for (_, y, m) in month_info]
        s = pd.to_numeric(df_raw.loc[selected, month_cols], errors='coerce')

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[p.to_timestamp() for p in periods], y=s.values,
            mode='lines+markers',
            line=dict(color=INK, width=1.6),
            marker=dict(size=5, color=INK, line=dict(color='#FBF8F1', width=1)),
            connectgaps=False,
            fill='tozeroy',
            fillcolor='rgba(181, 67, 44, 0.10)',
            hovertemplate='<b>%{x|%b %Y}</b><br>%{y:,.0f} кВт·ч<extra></extra>',
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=400,
                          xaxis_title=None, yaxis_title='кВт·ч')
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        c1, c2 = st.columns(2)

        with c1:
            st.markdown('<div class="section-label">Активные флаги</div>', unsafe_allow_html=True)
            row_flags = [n for n in flags.columns if flags.loc[selected, n]]
            if row_flags:
                html = ""
                for n in row_flags:
                    color = FLAG_COLOR.get(n, NAVY)
                    html += (f'<div class="flag-row" style="--flag-color:{color};">'
                             f'<span class="emoji">{FLAG_EMOJI.get(n,"🚩")}</span>'
                             f'<span class="name">{FLAG_TITLES.get(n,n)}</span></div>')
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.markdown('<div class="flag-empty">✓ Без флагов</div>', unsafe_allow_html=True)

            st.markdown('<div class="section-label" style="margin-top:1.6rem;">Ключевые метрики</div>', unsafe_allow_html=True)
            metric_keys = ['active_months', 'mean_kwh', 'avg_recent', 'avg_baseline',
                           'drop_ratio', 'longest_silence', 'longest_flat_run',
                           'power_ratio', 'cohort_z', 'сезонность']
            html = '<div class="kv-list">'
            for k in metric_keys:
                if k in registry.columns:
                    v = registry.loc[selected, k]
                    if pd.notna(v):
                        if isinstance(v, (int, float, np.floating)):
                            v_fmt = f"{v:,.2f}" if isinstance(v, float) else f"{v:,}"
                        else:
                            v_fmt = str(v)
                        html += (f'<div class="kv-row">'
                                 f'<span class="kv-key">{METRIC_LABELS.get(k,k)}</span>'
                                 f'<span class="kv-val">{v_fmt}</span></div>')
            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)

        with c2:
            st.markdown('<div class="section-label">Метаданные</div>', unsafe_allow_html=True)
            html = '<div class="kv-list">'
            meta_cols = ['Вид потребителя', 'Заводской номер прибора учета',
                         'Наименование точки учета', 'Населенный пункт',
                         'Улица', 'Дом', 'Разрешенная мощность',
                         'Тип события', 'Дата события']
            for col in meta_cols:
                if col in registry.columns:
                    v = registry.loc[selected, col]
                    if pd.notna(v):
                        html += (f'<div class="kv-row">'
                                 f'<span class="kv-key">{col}</span>'
                                 f'<span class="kv-val">{v}</span></div>')
            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)

        # ----- Скачать карточку абонента -----
        st.markdown('<div style="margin-top:1.5rem;"></div>', unsafe_allow_html=True)
        card_bytes = build_subscriber_card(
            df_raw, registry, base, flags, selected,
            FLAG_TITLES, FLAG_EMOJI, METRIC_LABELS,
            detect_month_columns(df_raw),
        )
        st.download_button(
            "Карточка абонента (Excel)",
            data=card_bytes,
            file_name=f"абонент_{selected}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Метаданные + флаги + метрики + помесячное потребление в одном файле",
        )

# =====================================================================
# ПОДВАЛ
# =====================================================================
st.markdown("""
<div class="footer-strip">
  Прототип · Данные не сохраняются · Работает в браузере
</div>
""", unsafe_allow_html=True)
