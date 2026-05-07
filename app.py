"""
Streamlit-приложение: анализ аномального потребления.
Стиль: корпоративный (по образцу Россети Кубань) — светлый фон, navy и красный акценты.
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
    'подозрение_хищение':   '#C8102E',  # красный (Россети)
    'долгое_молчание':      '#5A6F8E',  # серо-синий
    'превышение_мощности':  '#E37222',  # оранжевый
    'нестабильность':       '#0E8A6E',  # бирюзово-зелёный
    'одинаковые_подряд':    '#7B5BA6',  # фиолетовый
    'аномалия_в_когорте':   '#1F3868',  # navy
}

# =====================================================================
# СТИЛИ
# =====================================================================
CSS = """
<style>
/* Material Symbols — дублирующая загрузка с jsdelivr на случай блокировки Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined');
@import url('https://cdn.jsdelivr.net/npm/material-icons@1.13.12/iconfont/material-icons.css');
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@300;400;500;600;700;800;900&family=Manrope:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --navy:        #1F3868;       /* основной корпоративный (фон обложек Россети) */
    --navy-deep:   #142647;       /* темнее navy */
    --blue:        #2E5BA8;       /* акцентный синий */
    --blue-light:  #5891CA;       /* светло-синий */
    --sky:         #B8D4ED;       /* небесный для фонов */
    --red:         #C8102E;       /* красный (флаг "опасно") */
    --orange:      #E37222;       /* оранжевый */
    --green:       #0E8A6E;       /* зелёный (позитивные показатели) */
    --purple:      #7B5BA6;
    --gold:        #C9A227;

    --bg:          #FFFFFF;
    --bg-soft:     #F4F6FA;       /* очень светлый фон карточек */
    --bg-card:     #FFFFFF;
    --border:      #E1E5EB;
    --border-soft: #EEF1F5;
    --text:        #1A1F2C;
    --text-dim:    #5A6478;
    --text-faint:  #98A0AE;
}

/* фон */
.stApp { background: var(--bg) !important; }

html, body, [class*="css"], .stApp, .stApp * {
    font-family: 'Manrope', system-ui, sans-serif;
    color: var(--text);
}

/* убираем дефолтные элементы */
header[data-testid="stHeader"] { background: transparent !important; height: 0; }
.stDeployButton, #MainMenu, footer { display: none !important; }
.block-container { padding-top: 1.5rem !important; }

/* типографика */
h1, h2, h3, .display-font {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-weight: 700;
    letter-spacing: -0.005em;
    color: var(--navy);
    text-transform: uppercase;
}
h1 { font-size: 3rem !important; line-height: 1; letter-spacing: 0.01em; }
h2 { font-size: 1.6rem !important; }

.mono { font-family: 'JetBrains Mono', monospace !important; }

/* ========= HERO (как обложка слайда Россети: navy блок) ========= */
.hero {
    background: linear-gradient(135deg, var(--navy) 0%, var(--navy-deep) 100%);
    color: #FFFFFF;
    padding: 2rem 2.4rem;
    margin: 0 -1rem 2rem -1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 2rem;
    position: relative;
    overflow: hidden;
}
/* красный треугольник в стиле обложки Россети */
.hero::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 0; height: 0;
    border-style: solid;
    border-width: 0 110px 110px 0;
    border-color: transparent var(--red) transparent transparent;
    opacity: 0.92;
}
.hero::after {
    content: '';
    position: absolute;
    top: 0; right: 110px;
    width: 0; height: 0;
    border-style: solid;
    border-width: 0 80px 80px 0;
    border-color: transparent var(--blue-light) transparent transparent;
    opacity: 0.7;
}
/* МАКСИМАЛЬНАЯ специфичность — заголовок гарантированно белый,
   побеждаем любое правило h1/h2/h3 от Streamlit или нашего общего */
.stApp .hero h1,
.stApp .hero .hero-title,
.stApp div.hero h1.hero-title,
div.hero > h1,
div.hero > h1 *:not(.hero-em) {
    color: #FFFFFF !important;
}
.hero-title {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-weight: 800;
    font-size: 3.4rem;
    letter-spacing: 0.005em;
    line-height: 0.96;
    margin: 0;
    color: #FFFFFF !important;
    text-transform: uppercase;
    position: relative;
    z-index: 2;
}
.hero-title em, .hero-title span.hero-em, .hero .hero-em {
    font-style: normal;
    font-weight: 300;
    color: #B8D4ED !important;
    border-bottom: 4px solid #C8102E;
    padding-bottom: 2px;
}
.hero-meta {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.72rem;
    color: rgba(255, 255, 255, 0.78) !important;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    text-align: right;
    line-height: 1.7;
    white-space: nowrap;
    position: relative;
    z-index: 2;
    padding-right: 90px;
}
.hero-meta .badge {
    display: inline-block;
    color: #FFFFFF !important;
    font-weight: 600;
    border-left: 3px solid #C8102E;
    padding-left: 8px;
    margin-bottom: 4px;
}

/* ========= ЛЕНТА МЕТРИК ========= */
.metric-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 2rem;
}
.metric-cell {
    padding: 1.4rem 1.5rem;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-top: 4px solid var(--cell-accent, var(--navy));
    border-radius: 2px;
    transition: box-shadow 0.2s;
}
.metric-cell:hover { box-shadow: 0 4px 12px rgba(31, 56, 104, 0.08); }
.metric-label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.66rem;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--text-dim);
    margin-bottom: 0.7rem;
    font-weight: 500;
}
.metric-value {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-weight: 700;
    font-size: 3rem;
    line-height: 1;
    color: var(--navy);
}
.metric-value.red { color: var(--red); }
.metric-value.green { color: var(--green); }
.metric-value.blue { color: var(--blue); }

/* ========= СЕКЦИОННЫЕ ЗАГОЛОВКИ ========= */
.section-label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.22em;
    color: var(--blue);
    margin: 2rem 0 0.4rem 0;
    font-weight: 500;
}
.section-title {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-weight: 600;
    font-size: 1.7rem;
    line-height: 1.05;
    text-transform: uppercase;
    color: var(--navy);
    margin: 0.2rem 0 1.3rem 0;
    padding-bottom: 0.7rem;
    border-bottom: 2px solid var(--navy);
}

/* ========= ФЛАГИ ========= */
.flag-row {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 0.7rem 1rem;
    margin-bottom: 0.5rem;
    background: var(--bg-soft);
    border-left: 4px solid var(--flag-color, var(--navy));
    transition: transform 0.15s ease, box-shadow 0.15s;
}
.flag-row:hover {
    transform: translateX(3px);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
}
.flag-row .emoji { font-size: 1.05rem; }
.flag-row .name {
    font-family: 'Manrope', sans-serif;
    font-weight: 500;
    color: var(--text);
    font-size: 0.95rem;
}
.flag-empty {
    padding: 0.9rem 1.1rem;
    color: var(--green);
    background: rgba(14, 138, 110, 0.08);
    border-left: 4px solid var(--green);
    font-weight: 500;
}

/* ========= KEY-VALUE ========= */
.kv-list { font-family: 'Manrope', sans-serif; }
.kv-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 0.55rem 0;
    border-bottom: 1px dashed var(--border);
    gap: 1rem;
}
.kv-row:last-child { border-bottom: none; }
.kv-key { color: var(--text-dim); font-size: 0.86rem; }
.kv-val {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.92rem;
    color: var(--text);
    text-align: right;
    font-weight: 500;
    word-break: break-word;
}

/* ========= ТАБЫ ========= */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 2px solid var(--border);
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 1.05rem !important;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.7rem 1.6rem;
    color: var(--text-dim);
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    margin-bottom: -2px;
    transition: color 0.2s, border-color 0.2s;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--navy); }
.stTabs [aria-selected="true"] {
    color: var(--navy) !important;
    border-bottom-color: var(--red) !important;
}

/* ========= САЙДБАР ========= */
[data-testid="stSidebar"] {
    background: var(--bg-soft) !important;
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] h1 {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 1.8rem !important;
    font-weight: 700;
    color: var(--navy);
    margin-bottom: 0.4rem;
    text-transform: uppercase;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 2px;
    margin-bottom: 0.5rem;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 600;
    color: var(--navy);
}

/* ========= СЛАЙДЕРЫ — синий navy ========= */
.stSlider [data-baseweb="slider"] > div > div > div {
    background: var(--navy) !important;
}
.stSlider [role="slider"] {
    background-color: var(--navy) !important;
    border-color: var(--navy) !important;
    box-shadow: 0 0 0 4px rgba(31, 56, 104, 0.15) !important;
}
.stSlider [data-baseweb="tooltip"] > div {
    background: var(--navy) !important;
    color: #FFFFFF !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 600;
}

/* number input */
.stNumberInput input {
    background: var(--bg) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    font-family: 'JetBrains Mono', monospace !important;
}

/* select */
.stSelectbox > div > div, .stMultiSelect > div > div {
    background: var(--bg) !important;
    border: 1px solid var(--border) !important;
}

/* ========= КНОПКИ ========= */
.stDownloadButton button, .stButton button,
[data-testid="stDownloadButton"] button,
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-primary"] {
    background: var(--navy) !important;
    color: #FFFFFF !important;
    border: none !important;
    font-family: 'Barlow Condensed', sans-serif !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0.7rem 1.8rem !important;
    border-radius: 2px !important;
    transition: background 0.15s, transform 0.1s;
}
/* белый текст также для всех потомков (p, span, div внутри button) */
.stDownloadButton button *, .stButton button *,
[data-testid="stDownloadButton"] button *,
[data-testid="stDownloadButton"] button p,
[data-testid="stDownloadButton"] button span,
[data-testid="stDownloadButton"] button div {
    color: #FFFFFF !important;
}
.stDownloadButton button:hover, .stButton button:hover,
[data-testid="stDownloadButton"] button:hover {
    background: var(--red) !important;
    transform: translateY(-1px);
}

/* ========= ОТКЛЮЧАЕМ MATERIAL ICONS (если CDN заблокирован) ========= */
/* Если Google Fonts недоступны, Streamlit показывает голые имена иконок
   ("arrow_drop_down", "upload" и т.д.). Прячем их везде. */
.material-icons,
.material-icons-outlined,
.material-symbols-outlined,
[class*="material-icons"],
[class*="material-symbols"],
[data-testid="stIconMaterial"],
[data-testid*="ToggleIcon"] {
    font-size: 0 !important;
    visibility: hidden !important;
    width: 0 !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    display: inline-block !important;
}

/* Возвращаем индикатор открыт/закрыт у expander через текстовый символ */
[data-testid="stExpander"] details > summary {
    position: relative;
    padding-right: 1.8rem !important;
}
[data-testid="stExpander"] details > summary::after {
    content: "▾";
    position: absolute;
    right: 0.8rem;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-dim);
    font-size: 0.85rem;
    transition: transform 0.2s;
    visibility: visible !important;
    width: auto !important;
    height: auto !important;
}
[data-testid="stExpander"] details[open] > summary::after {
    content: "▴";
}
[data-testid="stFileUploaderDropzone"] {
    background: var(--bg-soft) !important;
    border: 2px dashed var(--blue-light) !important;
    border-radius: 2px !important;
    padding: 1.2rem 1.5rem !important;
    min-height: 90px !important;
    transition: border-color 0.2s, background 0.2s;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--navy) !important;
    background: #FFFFFF !important;
}
/* Кнопка "Browse files / Upload" — ТОЛЬКО прямой потомок dropzone, не вложенная.
   Если использовать просто [stFileUploaderDropzone] button, селектор может
   зацепить кнопку крестика в блоке загруженного файла, и появится "Загрузить файл" дважды. */
section[data-testid="stFileUploaderDropzone"] > button,
[data-testid="stFileUploaderDropzone"] > button {
    background: var(--navy) !important;
    color: #FFFFFF !important;
    border: none !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0 !important;          /* прячем оригинальный текст */
    line-height: 1 !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    padding: 0.6rem 1.2rem !important;
    min-width: 150px;
    white-space: nowrap !important;
}
section[data-testid="stFileUploaderDropzone"] > button::after,
[data-testid="stFileUploaderDropzone"] > button::after {
    content: "Загрузить файл";
    display: inline-block;
    font-size: 0.92rem !important;
    font-family: 'Manrope', sans-serif;
    font-weight: 500;
    color: #FFFFFF;
}
/* На случай старой структуры со span внутри: спрятать его текст */
section[data-testid="stFileUploaderDropzone"] > button > * {
    font-size: 0 !important;
    visibility: hidden !important;
}
section[data-testid="stFileUploaderDropzone"] > button::after {
    visibility: visible !important;
}

/* Заменяем текст-инструкцию ("Drag and drop file here / Limit X / XLSX, XLS")
   на собственный русский — без зависимости от material-icons */
[data-testid="stFileUploaderDropzoneInstructions"] {
    font-size: 0 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"]::before {
    content: "Перетащите Excel-файл сюда или нажмите кнопку справа";
    display: block;
    font-family: 'Manrope', sans-serif;
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--text);
}
[data-testid="stFileUploaderDropzoneInstructions"]::after {
    content: "Поддерживается: XLSX, XLS — до 200 МБ";
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--text-dim);
    margin-top: 0.4rem;
    letter-spacing: 0.05em;
}
/* Прячем все иконки внутри drop-zone (svg или material-icons) */
[data-testid="stFileUploaderDropzone"] svg,
[data-testid="stFileUploaderDropzone"] [class*="material"] {
    display: none !important;
}

/* ========= ЗАГРУЖЕННЫЙ ФАЙЛ (после загрузки) ========= */
/* Блок с именем файла, его размером и кнопкой-крестиком для удаления.
   Делаем крестик видимым через ::after (символ ✕), даже если material-icons не загружен. */
[data-testid="stFileUploaderFile"],
[data-testid="stFileUploaderFileData"] {
    background: var(--bg-soft);
    border: 1px solid var(--border);
    border-radius: 2px;
    padding: 0.5rem 0.8rem;
}
[data-testid="stFileUploaderFile"] button,
[data-testid="stFileUploaderDeleteBtn"] button {
    background: transparent !important;
    color: var(--red) !important;
    border: 1px solid var(--border) !important;
    font-family: 'Manrope', sans-serif !important;
    font-size: 0 !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    padding: 0.35rem 0.6rem !important;
    min-width: 0 !important;
    line-height: 1 !important;
    border-radius: 2px !important;
}
[data-testid="stFileUploaderFile"] button::after,
[data-testid="stFileUploaderDeleteBtn"] button::after {
    content: "✕ Удалить";
    display: inline-block;
    font-size: 0.78rem !important;
    font-weight: 500;
    color: var(--red);
    visibility: visible !important;
}
[data-testid="stFileUploaderFile"] button:hover,
[data-testid="stFileUploaderDeleteBtn"] button:hover {
    background: var(--red) !important;
    border-color: var(--red) !important;
}
[data-testid="stFileUploaderFile"] button:hover::after,
[data-testid="stFileUploaderDeleteBtn"] button:hover::after {
    color: #FFFFFF !important;
}
/* В новой кнопке текст внутри child-нодов — прячем (чтобы не было дубля) */
[data-testid="stFileUploaderFile"] button > *,
[data-testid="stFileUploaderDeleteBtn"] button > * {
    font-size: 0 !important;
    visibility: hidden !important;
    width: 0 !important;
    height: 0 !important;
}

/* dataframe */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: 2px;
}

/* expander */
[data-testid="stExpander"] {
    border: 1px solid var(--border);
    border-radius: 2px;
}

/* pills */
.pill {
    display: inline-block;
    padding: 0.22rem 0.7rem;
    border-radius: 2px;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.74rem;
    margin: 0.18rem 0.22rem 0.18rem 0;
    border: 1px solid var(--border);
    background: var(--bg-soft);
    color: var(--text);
}
.pill.found {
    color: var(--green);
    border-color: rgba(14, 138, 110, 0.3);
    background: rgba(14, 138, 110, 0.05);
}

/* заглушка */
.empty-state {
    border: 1px dashed var(--border);
    padding: 3rem 2rem;
    text-align: center;
    color: var(--text-dim);
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 1.6rem;
    margin: 1rem 0;
    background: var(--bg-soft);
    text-transform: uppercase;
    letter-spacing: 0.02em;
    font-weight: 400;
}
.empty-state .small {
    text-transform: none;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.8rem;
    color: var(--text-faint);
    letter-spacing: 0.05em;
    display: block;
    margin-top: 0.7rem;
    font-weight: 400;
}

/* подвал */
.footer-strip {
    margin-top: 3rem;
    padding: 1.2rem 0;
    border-top: 2px solid var(--navy);
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.2em;
    text-align: center;
}

/* Streamlit info/warning/error */
.stAlert { border-radius: 2px !important; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# =====================================================================
# Plotly-тема (светлая, корпоративная)
# =====================================================================
PLOTLY_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(244, 246, 250, 0.4)',
    font=dict(family='Manrope, sans-serif', color='#5A6478', size=11),
    xaxis=dict(gridcolor='#EEF1F5', linecolor='#E1E5EB', zerolinecolor='#E1E5EB',
               tickfont=dict(color='#5A6478', family='JetBrains Mono')),
    yaxis=dict(gridcolor='#EEF1F5', linecolor='#E1E5EB', zerolinecolor='#E1E5EB',
               tickfont=dict(color='#5A6478', family='JetBrains Mono')),
    margin=dict(l=10, r=10, t=20, b=10),
    showlegend=False,
)

NAVY = '#1F3868'
BLUE = '#2E5BA8'
RED = '#C8102E'
ORANGE = '#E37222'
GREEN = '#0E8A6E'
PURPLE = '#7B5BA6'
GRAY = '#98A0AE'

# =====================================================================
# САЙДБАР
# =====================================================================
with st.sidebar:
    st.markdown("# Настройки")
    st.markdown('<div style="color:var(--text-dim);font-size:0.86rem;margin-bottom:1.2rem;">Подкручивайте — таблица пересчитается.</div>', unsafe_allow_html=True)

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
st.markdown("""
<div class="hero">
  <h1 class="hero-title">Анализ <span class="hero-em">аномального</span><br/>потребления</h1>
  <div class="hero-meta">
    <span class="badge">ЭНЕРГОУЧЁТ</span><br/>
    Реестр абонентов с флагами<br/>
    Данные не сохраняются
  </div>
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
            'justify-content:center;color:var(--text-faint);font-family:JetBrains Mono;'
            'font-size:0.7rem;text-transform:uppercase;letter-spacing:0.18em;'
            'border:1px dashed var(--border);padding:1.2rem;text-align:center;'
            'min-height:90px;">Отчёт появится<br/>после загрузки</div>',
            unsafe_allow_html=True
        )

    st.markdown("""
    <div class="empty-state">
      Перетащите выгрузку выше, чтобы начать анализ
      <span class="small">Минимум: столбцы вида «Январь 2024», «Февраль 2024»…</span>
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
  <div class="metric-cell" style="--cell-accent:var(--navy);">
    <div class="metric-label">Абонентов в файле</div>
    <div class="metric-value">{report['total_rows']:,}</div>
  </div>
  <div class="metric-cell" style="--cell-accent:var(--blue);">
    <div class="metric-label">Месяцев данных</div>
    <div class="metric-value blue">{report['months_detected']}</div>
  </div>
  <div class="metric-cell" style="--cell-accent:var(--orange);">
    <div class="metric-label">С флагами</div>
    <div class="metric-value" style="color:var(--orange);">{n_with_flags:,}</div>
  </div>
  <div class="metric-cell" style="--cell-accent:var(--red);">
    <div class="metric-label">Высокий риск (3+ флага)</div>
    <div class="metric-value red">{n_high_risk:,}</div>
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
                    f'<span class="mono" style="color:var(--blue);font-weight:500;">{f["name"]}</span> '
                    f'<span style="color:var(--text-dim);">— {f["reason"]}</span></div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown('<div class="section-label">Все флаги вычислены</div>', unsafe_allow_html=True)
            st.markdown('<div style="color:var(--green);font-family:JetBrains Mono;font-weight:500;">✓ полный набор</div>', unsafe_allow_html=True)

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
        # шкала: 0—серый, 1—синий, 2—голубой, 3—оранж, 4+—красный (как svetofor)
        scale = {0: GRAY, 1: NAVY, 2: BLUE, 3: ORANGE, 4: RED, 5: RED}
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
            textfont=dict(family='JetBrains Mono', color='#1A1F2C', size=12),
            hovertemplate='<b>%{y}</b><br>%{x} абонентов<extra></extra>',
        ))
        fig2.update_layout(**PLOTLY_LAYOUT, height=320,
                           xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

    st.markdown('<div class="section-label">Сезонная классификация</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">По характеру потребления</div>', unsafe_allow_html=True)
    seas = registry['сезонность'].value_counts()
    season_color = {'круглогодичный': NAVY, 'летний (дача)': ORANGE,
                    'зимний (отопление)': BLUE, 'нет данных': GRAY}
    fig3 = go.Figure(go.Bar(
        x=seas.index, y=seas.values, text=seas.values, textposition='outside',
        marker_color=[season_color.get(k, GRAY) for k in seas.index],
        textfont=dict(family='JetBrains Mono', color='#1A1F2C', size=12),
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
        f'color:var(--text-dim);text-transform:uppercase;letter-spacing:0.14em;'
        f'margin:0.5rem 0 0.8rem 0;font-weight:500;">'
        f'Показано <span style="color:var(--red);">{len(view):,}</span> из {len(registry):,} абонентов'
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
            line=dict(color=NAVY, width=2),
            marker=dict(size=5, color=NAVY, line=dict(color='#FFFFFF', width=1)),
            connectgaps=False,
            fill='tozeroy',
            fillcolor='rgba(31, 56, 104, 0.08)',
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
