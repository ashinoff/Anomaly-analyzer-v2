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
    'trend_annual_drop':'Годовое снижение (тренд), доля',
    'yoy_median_ratio': 'Медианное отношение год-к-году',
    'zero_share':       'Доля нулевых месяцев',
    'round_share':      'Доля «круглых» значений',
    'iso_score':        'ML-оценка аномальности',
    'сезонность':       'Сезонность',
    'мало_данных':      'Мало данных',
    'кол-во_флагов':    'Кол-во флагов',
    'риск_балл':        'Риск-балл',
}

def _svg(paths):
    """Мини-иконка 15×15, цвет наследуется через currentColor."""
    return ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round" style="flex-shrink:0;">' + paths + '</svg>')

FLAG_ICON = {
    'подозрение_хищение':   _svg('<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>'),
    'долгое_молчание':      _svg('<circle cx="12" cy="12" r="9" stroke-dasharray="3 4"/>'),
    'превышение_мощности':  _svg('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'),
    'нестабильность':       _svg('<path d="M2 12c2-5 4-5 6 0s4 5 6 0 4-5 6 0"/>'),
    'одинаковые_подряд':    _svg('<line x1="5" y1="7" x2="19" y2="7"/><line x1="5" y1="12" x2="19" y2="12"/><line x1="5" y1="17" x2="19" y2="17"/>'),
    'аномалия_в_когорте':   _svg('<circle cx="7" cy="16" r="2.2"/><circle cx="13" cy="17" r="2.2"/><circle cx="17.5" cy="6.5" r="3"/>'),
    'тренд_снижение':       _svg('<line x1="4" y1="6" x2="20" y2="18"/><polyline points="13 18 20 18 20 11"/>'),
    'падение_год_к_году':   _svg('<rect x="5" y="11" width="4.5" height="8"/><rect x="14" y="5" width="4.5" height="14" stroke-dasharray="3 3"/>'),
    'нулевые_показания':    _svg('<circle cx="12" cy="12" r="7.5"/><line x1="6.5" y1="17.5" x2="17.5" y2="6.5"/>'),
    'круглые_числа':        _svg('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.5"/>'),
    'ml_аномалия':          _svg('<rect x="6" y="6" width="12" height="12" rx="2"/><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/>'),
}

FLAG_TITLES = {
    'подозрение_хищение':   'Подозрение на хищение',
    'долгое_молчание':      'Долгое молчание ПУ',
    'превышение_мощности':  'Превышение мощности',
    'нестабильность':       'Нестабильность',
    'одинаковые_подряд':    'Одинаковые подряд',
    'аномалия_в_когорте':   'Аномалия в когорте',
    'тренд_снижение':       'Тренд на снижение',
    'падение_год_к_году':   'Падение год к году',
    'нулевые_показания':    'Нулевые показания',
    'круглые_числа':        'Круглые числа',
    'ml_аномалия':          'ML-аномалия',
}

FLAG_COLOR = {
    'подозрение_хищение':   '#FF5A72',  # тревожный красный
    'долгое_молчание':      '#7FB4FF',  # синий
    'превышение_мощности':  '#FFB066',  # оранжевый
    'нестабильность':       '#2EE6A0',  # зелёный
    'одинаковые_подряд':    '#B58CFF',  # фиолетовый
    'аномалия_в_когорте':   '#5AA2FF',  # синий-акцент
    'тренд_снижение':       '#FF8A5A',  # тёпло-оранжевый
    'падение_год_к_году':   '#FF7A86',  # розово-красный
    'нулевые_показания':    '#9FB2D8',  # серо-синий
    'круглые_числа':        '#FFCA8F',  # песочный
    'ml_аномалия':          '#8FF0CF',  # мятный
}

# =====================================================================
# СТИЛИ
# =====================================================================
# Дизайн вынесен в отдельный файл — правит дизайнер, логику не трогаем.
# Единственный источник правды по стилям наших блоков: assets/app.css
# (тот же файл подключает автономный превью design/preview.html).
from pathlib import Path
_CSS = (Path(__file__).parent / 'assets' / 'app.css').read_text(encoding='utf-8')
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


# =====================================================================
# Plotly-тема (светлая, корпоративная)
# =====================================================================
PLOTLY_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(20, 34, 72, 0.18)',
    font=dict(family='system-ui, sans-serif', color='#9FB2D8', size=11),
    xaxis=dict(gridcolor='rgba(90,162,255,0.12)', linecolor='rgba(90,162,255,0.28)', zerolinecolor='rgba(90,162,255,0.2)',
               tickfont=dict(color='#9FB2D8', family='ui-monospace, monospace')),
    yaxis=dict(gridcolor='rgba(90,162,255,0.12)', linecolor='rgba(90,162,255,0.28)', zerolinecolor='rgba(90,162,255,0.2)',
               tickfont=dict(color='#9FB2D8', family='ui-monospace, monospace')),
    margin=dict(l=10, r=10, t=20, b=10),
    showlegend=False,
)

NAVY = '#5AA2FF'
BLUE = '#7FB4FF'
RED = '#FF5A72'
ORANGE = '#FFB066'
GREEN = '#2EE6A0'
PURPLE = '#B58CFF'
GRAY = '#6F83AC'

# =====================================================================
# САЙДБАР
# =====================================================================
ALGO_INFO = {
    'хищение': """**Что ищет:** абонентов, у которых потребление резко и надолго упало.

**Как работает:** берём среднее потребление за последние месяцы («недавний период») и сравниваем со средним за предыдущие месяцы («обычный уровень»). Если раньше абонент потреблял заметно, а теперь тратит на N% меньше — ставим флаг.

**Пример:** два года подряд по 500 кВт·ч/мес, последний год — по 80. Падение 84% — типичная картина после установки «жучка» или магнита.""",

    'молчание': """**Что ищет:** счётчики, которые подолгу не передают показания.

**Как работает:** ищем самый длинный непрерывный «пробел» — месяцы без данных — в истории абонента, включая тишину в самом конце периода. Длинное молчание — повод проверить: счётчик мог быть отключён, сломан или показания скрывают.""",

    'мощность': """**Что ищет:** потребление выше того, что разрешено договором.

**Как работает:** берём самый «жирный» месяц абонента и переводим его в среднюю мощность (кВт·ч ÷ 720 часов). Если она превышает разрешённую мощность из договора — флаг. Это либо самовольное увеличение нагрузки, либо подключение мимо счётчика соседних потребителей.

Работает только если в файле есть колонка «Разрешенная мощность».""",

    'нестабильность': """**Что ищет:** абонентов, у которых потребление хаотично скачет.

**Как работает:** считаем коэффициент вариации — насколько сильно значения разбросаны относительно среднего. Порог 1.2 означает «разброс больше самого среднего». Сильные скачки без сезонной логики бывают при периодическом отключении счётчика или частичном обходе.""",

    'одинаковые': """**Что ищет:** подозрительно одинаковые показания месяц за месяцем.

**Как работает:** ищем самую длинную серию, где значение вообще не меняется (и не равно нулю). Реальное потребление всегда чуть «дышит». Одна и та же цифра 6+ месяцев подряд — почти наверняка кто-то вручную вписывает норматив, а не снимает показания.""",

    'когорта': """**Что ищет:** абонентов, которые сильно выбиваются из своей группы.

**Как работает:** делим всех на группы по колонке «Вид потребителя» (физлица, юрлица) и смотрим, насколько потребление каждого отличается от типичного для его группы. Отклонение измеряется в «сигмах» — порог 3 означает «выбивается сильнее, чем 99.7% группы». Слишком мало — возможен обход; слишком много — возможна перепродажа.

Работает только если в файле есть колонка «Вид потребителя».""",

    'тренд': """**Что ищет:** медленное, но упорное снижение — «хищение мелкими шагами».

**Как работает:** через все точки за выбранный период проводим устойчивую к выбросам линию тренда (метод Тейла–Сена) и смотрим её наклон. Если линия за год опускается на N% от среднего уровня — флаг. Резкий флаг «падение» такого не поймает: там снижение размазано и каждый месяц выглядит почти нормально.""",

    'год_к_году': """**Что ищет:** падение по сравнению с тем же месяцем прошлого года.

**Как работает:** январь сравниваем с прошлым январём, февраль — с прошлым февралём, и так далее. Берём медиану этих отношений. Так дача, которая «пустеет» каждую зиму, не даст ложного срабатывания — а реальное снижение будет видно даже на сезонном потреблении.""",

    'нули': """**Что ищет:** абонентов, у которых слишком часто «ноль», хотя раньше было живое потребление.

**Как работает:** считаем долю нулевых месяцев среди всех отчитанных. Если нулей много, а в ненулевые месяцы потребление заметное — это похоже на остановку счётчика (шунт, магнит) или передачу нулей вместо реальных показаний.""",

    'круглые': """**Что ищет:** показания, которые слишком «красивые», чтобы быть настоящими.

**Как работает:** считаем, какая доля значений делится ровно на выбранное число (например, на 100). Реальные показания — это 347, 512, 289... Если у абонента сплошь 300, 400, 500 — цифры, скорее всего, вписываются вручную «от балды» или по нормативу.""",

    'ml': """**Что ищет:** необычные профили потребления, которые не описаны ни одним правилом выше.

**Как работает:** алгоритм Isolation Forest (машинное обучение без учителя) смотрит на каждого абонента сразу по многим признакам — уровень, разброс, тренд, сезонность, доля нулей — и находит тех, кто в совокупности «не такой, как все». Ползунок задаёт, сколько самых необычных отметить. Это страховочная сетка: ловит хитрые схемы, под которые не написано отдельное правило.""",

    'прочее': """Если у абонента слишком мало месяцев с данными, статистика по нему ненадёжна: любое правило может сработать случайно. Такие абоненты не участвуют в большинстве проверок и помечаются признаком «мало данных».""",
}


def algo_help(key):
    with st.popover("ⓘ  как это работает"):
        st.markdown(ALGO_INFO[key])


with st.sidebar:
    st.markdown("# Настройки")
    st.markdown('<div style="color:var(--text-dim);font-size:0.86rem;margin-bottom:1.2rem;">Измените порог — таблица пересчитается. У каждого правила есть справка ⓘ.</div>', unsafe_allow_html=True)

    with st.expander("Резкое падение потребления", expanded=True):
        algo_help('хищение')
        cfg_theft_drop = st.slider("Потребление упало не менее чем на, %", 20, 95, 50, 5,
                                   help="Насколько недавнее потребление ниже обычного уровня") / 100
        cfg_theft_recent = st.slider("«Недавние» — это последние, мес.", 3, 24, 12)
        cfg_theft_baseline = st.slider("«Обычный уровень» — предыдущие, мес.", 6, 36, 24)
        cfg_theft_min = st.number_input("Не проверять мелких: обычный уровень от, кВт·ч/мес", 0, 10000, 50, 10,
                                        help="Абоненты, потреблявшие меньше, не проверяются — там падение ни о чём не говорит")

    with st.expander("Счётчик молчит"):
        algo_help('молчание')
        cfg_silence = st.slider("Нет показаний подряд, мес.", 3, 24, 6)

    with st.expander("Потребляет больше разрешённого"):
        algo_help('мощность')
        cfg_power_ratio = st.slider("Превышение разрешённой мощности, раз", 0.5, 3.0, 1.0, 0.1,
                                    help="1.0 = флаг при любом превышении договора; 1.5 = только при превышении в полтора раза")

    with st.expander("Скачущее потребление"):
        algo_help('нестабильность')
        cfg_cv = st.slider("Порог разброса значений", 0.3, 3.0, 1.2, 0.1,
                           help="Чем выше — тем более дикие скачки нужны для флага")

    with st.expander("Одни и те же цифры подряд"):
        algo_help('одинаковые')
        cfg_flat = st.slider("Одинаковое значение подряд, мес.", 3, 24, 6)

    with st.expander("Не похож на свою группу"):
        algo_help('когорта')
        cfg_z = st.slider("Порог отклонения от группы", 1.5, 5.0, 3.0, 0.1,
                          help="3.0 = выбивается сильнее, чем 99.7% похожих абонентов")

    with st.expander("Плавное снижение месяц за месяцем"):
        algo_help('тренд')
        cfg_trend_drop = st.slider("Снижение за год не менее, %", 10, 80, 25, 5) / 100
        cfg_trend_window = st.slider("Смотрим последние, мес.", 12, 48, 24)

    with st.expander("Ниже, чем год назад"):
        algo_help('год_к_году')
        cfg_yoy_drop = st.slider("Падение к тому же месяцу прошлого года, %", 20, 90, 40, 5) / 100
        cfg_yoy_pairs = st.slider("Минимум месяцев для сравнения", 3, 12, 6,
                                  help="Сколько пар «месяц — тот же месяц год назад» нужно для вывода")

    with st.expander("Слишком много нулей"):
        algo_help('нули')
        cfg_zero_share = st.slider("Нулевых месяцев не менее, %", 10, 90, 30, 5) / 100

    with st.expander("Подозрительно круглые цифры"):
        algo_help('круглые')
        cfg_round_share = st.slider("Круглых значений не менее, %", 30, 100, 70, 5) / 100
        cfg_round_base = st.selectbox("Круглое = делится на", [10, 50, 100, 500, 1000], index=2)

    with st.expander("Поиск аномалий ИИ-моделью"):
        algo_help('ml')
        cfg_iso = st.slider("Отметить самых необычных, %", 1, 15, 5, 1)  / 100

    with st.expander("Общие ограничения"):
        algo_help('прочее')
        cfg_min_active = st.slider("Минимум месяцев с данными", 3, 36, 12)

config = {
    "theft_recent_months": cfg_theft_recent, "theft_baseline_months": cfg_theft_baseline,
    "theft_drop_pct": cfg_theft_drop, "theft_min_baseline_kwh": cfg_theft_min,
    "silence_months": cfg_silence, "power_overrun_ratio": cfg_power_ratio,
    "cv_threshold": cfg_cv, "flat_run_months": cfg_flat,
    "cohort_zscore": cfg_z, "min_active_months": cfg_min_active,
    "trend_annual_drop_pct": cfg_trend_drop, "trend_window_months": cfg_trend_window,
    "yoy_drop_pct": cfg_yoy_drop, "yoy_min_pairs": cfg_yoy_pairs,
    "zero_share_threshold": cfg_zero_share,
    "round_share_threshold": cfg_round_share, "round_base": cfg_round_base,
    "iso_contamination": cfg_iso,
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
        "Загрузка выгрузки Excel",
        type=['xlsx', 'xls'],
        help="XLSX или XLS до 200 МБ. Нужны помесячные столбцы вида «Январь 2024».",
    )
    st.caption("Перетащите Excel-файл в область выше или нажмите «Browse files». "
               "Формат XLSX / XLS, до 200 МБ. Данные не сохраняются.")

# Если файл не загружен — заглушка и стоп
if not uploaded:
    with download_col:
        st.markdown(
            '<div style="height:100%;display:flex;align-items:center;'
            'justify-content:center;color:var(--text-faint);font-family:ui-monospace, monospace;'
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

    with st.expander("Какие колонки распознаются и какие проверки выполняются"):
        st.markdown("""
**Обязательно** — помесячные столбцы вида `Январь 2019`, `Февраль 2019` ... `Январь 2026`.

**Опционально** (без них часть проверок пропускается, но анализ работает):
- `Разрешенная мощность` — для проверки «потребляет больше разрешённого»
- `Вид потребителя` (ФИЗ/ЮР) — для «не похож на свою группу»
- `Заводской номер ПУ`, `Наименование точки учета`, адресные поля
        """)
        _legend_desc = {
            'подозрение_хищение':  'резкое и устойчивое падение потребления',
            'тренд_снижение':      'плавное снижение месяц за месяцем',
            'падение_год_к_году':  'ниже, чем в тот же месяц год назад',
            'долгое_молчание':     'долгие пропуски в показаниях',
            'нулевые_показания':   'слишком много нулей при живой истории',
            'превышение_мощности': 'пиковое потребление выше договора',
            'одинаковые_подряд':   'одна и та же цифра много месяцев',
            'круглые_числа':       'подозрительно круглые значения',
            'нестабильность':      'хаотичные скачки потребления',
            'аномалия_в_когорте':  'сильно выбивается из своей группы',
            'ml_аномалия':         'необычный профиль по мнению ИИ-модели',
        }
        _rows = "".join(
            f'<div class="flag-row" style="--flag-color:{FLAG_COLOR.get(k, NAVY)};">'
            f'<span class="icon">{FLAG_ICON.get(k, "")}</span>'
            f'<span class="name"><b>{FLAG_TITLES.get(k, k)}</b> — {d}</span></div>'
            for k, d in _legend_desc.items()
        )
        st.markdown(f'<div style="margin-top:0.4rem;">{_rows}</div>', unsafe_allow_html=True)
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
    FLAG_TITLES, {}, METRIC_LABELS,
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
n_high_risk = int((registry['риск_балл'] >= 5).sum())

_metric_cards = [
    ("Абонентов в файле", f"{report['total_rows']:,}", "navy", ""),
    ("Месяцев данных", f"{report['months_detected']}", "navy", ""),
    ("С флагами", f"{n_with_flags:,}", "orange", "orange"),
    ("Высокий риск (балл ≥ 5)", f"{n_high_risk:,}", "red", "red"),
]
for _col, (_lbl, _val, _accent, _vcls) in zip(st.columns(4), _metric_cards):
    with _col:
        st.markdown(
            f'<div class="metric-cell" style="--cell-accent:var(--{_accent});">'
            f'<div class="metric-label">{_lbl}</div>'
            f'<div class="metric-value {_vcls}">{_val}</div></div>',
            unsafe_allow_html=True,
        )

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
            st.markdown('<div style="color:var(--green);font-family:ui-monospace, monospace;font-weight:500;">✓ полный набор</div>', unsafe_allow_html=True)

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
            textfont=dict(family='ui-monospace, monospace', color='#DBE6F7', size=12),
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
            textfont=dict(family='ui-monospace, monospace', color='#DBE6F7', size=12),
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
        textfont=dict(family='ui-monospace, monospace', color='#DBE6F7', size=12),
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
            format_func=lambda x: FLAG_TITLES.get(x, x),
        )

    view = registry[registry['кол-во_флагов'] >= min_flags].copy()
    if season_filter != '(все)':
        view = view[view['сезонность'] == season_filter]
    for fn in active_flag_filter:
        view = view[view[fn] == True]

    display_view = view.rename(columns={
        **METRIC_LABELS,
        **{k: FLAG_TITLES.get(k, k) for k in flags.columns},
    })

    st.markdown(
        f'<div style="font-family:ui-monospace,monospace;font-size:0.78rem;'
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
        suffix = f"  ·  флагов: {flags_n}" if flags_n else ""
        return f"#{idx} · {' · '.join(parts) if parts else 'без идентификатора'}{suffix}"

    sorted_idx = registry.sort_values(['риск_балл', 'кол-во_флагов'], ascending=False).index.tolist()
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
            fillcolor='rgba(90, 162, 255, 0.14)',
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
                             f'<span class="icon">{FLAG_ICON.get(n,"")}</span>'
                             f'<span class="name">{FLAG_TITLES.get(n,n)}</span></div>')
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.markdown('<div class="flag-empty">✓ Без флагов</div>', unsafe_allow_html=True)

            st.markdown('<div class="section-label" style="margin-top:1.6rem;">Ключевые метрики</div>', unsafe_allow_html=True)
            metric_keys = ['active_months', 'mean_kwh', 'avg_recent', 'avg_baseline',
                           'drop_ratio', 'trend_annual_drop', 'yoy_median_ratio',
                           'zero_share', 'round_share', 'iso_score',
                           'longest_silence', 'longest_flat_run',
                           'power_ratio', 'cohort_z', 'сезонность', 'риск_балл']
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
            FLAG_TITLES, {}, METRIC_LABELS,
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
