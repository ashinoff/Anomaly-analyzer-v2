"""
Streamlit-приложение для анализа аномального потребления.
Запуск локально: streamlit run app.py
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

st.set_page_config(
    page_title="Анализ потребления",
    page_icon="⚡",
    layout="wide",
)

# ============ САЙДБАР: ПОРОГИ ============
st.sidebar.title("⚙️ Настройки порогов")
st.sidebar.markdown("Подкручивайте — таблица пересчитывается на лету.")

with st.sidebar.expander("🔻 Подозрение на хищение", expanded=True):
    cfg_theft_drop = st.slider(
        "Падение потребления, %",
        min_value=20, max_value=95, value=50, step=5,
        help="На сколько % должно упасть потребление в недавнем периоде vs опорном"
    ) / 100
    cfg_theft_recent = st.slider("Недавний период, мес.", 3, 24, 12)
    cfg_theft_baseline = st.slider("Опорный период, мес.", 6, 36, 24)
    cfg_theft_min = st.number_input(
        "Мин. опорное потребление, кВт·ч/мес",
        min_value=0, max_value=10000, value=50, step=10,
        help="Если в опорный период потребляли меньше — игнорируем (шум)"
    )

with st.sidebar.expander("🔇 Долгое молчание ПУ"):
    cfg_silence = st.slider("Подряд месяцев без показаний", 3, 24, 6)

with st.sidebar.expander("⚡ Превышение мощности"):
    cfg_power_ratio = st.slider(
        "Порог отношения пиковой/разрешённой",
        min_value=0.5, max_value=3.0, value=1.0, step=0.1
    )

with st.sidebar.expander("📊 Нестабильность"):
    cfg_cv = st.slider(
        "Коэфф. вариации (σ/μ)",
        min_value=0.3, max_value=3.0, value=1.2, step=0.1
    )

with st.sidebar.expander("📐 Одинаковые числа подряд"):
    cfg_flat = st.slider("Подряд одинаковых значений", 3, 24, 6)

with st.sidebar.expander("👥 Аномалия в когорте"):
    cfg_z = st.slider("Robust z-score порог", 1.5, 5.0, 3.0, 0.1)

with st.sidebar.expander("🔧 Прочее"):
    cfg_min_active = st.slider(
        "Мин. активных месяцев для анализа", 3, 36, 12,
        help="Абоненты с меньшим числом месяцев исключаются из проверки на хищение/молчание"
    )

config = {
    "theft_recent_months": cfg_theft_recent,
    "theft_baseline_months": cfg_theft_baseline,
    "theft_drop_pct": cfg_theft_drop,
    "theft_min_baseline_kwh": cfg_theft_min,
    "silence_months": cfg_silence,
    "power_overrun_ratio": cfg_power_ratio,
    "cv_threshold": cfg_cv,
    "flat_run_months": cfg_flat,
    "cohort_zscore": cfg_z,
    "min_active_months": cfg_min_active,
}

# ============ ОСНОВНОЙ ЭКРАН ============
st.title("⚡ Анализ аномального потребления")
st.caption("Загрузите Excel-выгрузку — получите реестр абонентов с флагами аномалий. Данные нигде не сохраняются.")

uploaded = st.file_uploader(
    "Excel-файл с потреблением",
    type=['xlsx', 'xls'],
    help="Минимум: столбцы вида «Январь 2024», «Февраль 2024»… "
         "Опционально: Разрешенная мощность, Вид потребителя, и т.д."
)

if not uploaded:
    st.info("👆 Загрузите файл, чтобы начать анализ.")
    with st.expander("Какие колонки распознаются?"):
        st.markdown("""
**Обязательно** — помесячные столбцы вида `Январь 2019`, `Февраль 2019` ... `Январь 2026`.

**Опционально** (без них часть флагов пропускается, но анализ работает):
- `Разрешенная мощность` — для флага «превышение мощности»
- `Вид потребителя` (ФИЗ/ЮР) — для «аномалия в когорте»
- `Заводской номер ПУ`, `Наименование точки учета`, адресные поля — для удобства идентификации
- `Тип события`, `Дата события` — пока не используются, заложено на будущее

Какие флаги считаются:
- 🔻 **Подозрение на хищение** — резкое устойчивое падение vs опорный период
- 🔇 **Долгое молчание ПУ** — длинные пропуски в показаниях
- ⚡ **Превышение мощности** — пиковое потребление выше разрешённой
- 📊 **Нестабильность** — высокий коэффициент вариации
- 📐 **Одинаковые числа подряд** — подозрение на ручной ввод «по нормативу»
- 👥 **Аномалия в когорте** — потребление сильно выше/ниже соседей по виду
        """)
    st.stop()

# ============ АНАЛИЗ ============
@st.cache_data(show_spinner="Читаю файл…")
def load_excel(file_bytes):
    return pd.read_excel(io.BytesIO(file_bytes))

@st.cache_data(show_spinner="Анализирую…")
def run_analysis(file_bytes, config):
    df = load_excel(file_bytes)
    return df, *analyze(df, config)

try:
    df_raw, registry, base, flags, report = run_analysis(uploaded.getvalue(), config)
except ValueError as e:
    st.error(f"❌ {e}")
    st.stop()

# ============ ОТЧЁТ О ЗАГРУЗКЕ ============
c1, c2, c3, c4 = st.columns(4)
c1.metric("Абонентов", report['total_rows'])
c2.metric("Месяцев в файле", report['months_detected'])
c3.metric("Флагов вычислено", len(report['flags_computed']))
c4.metric("С флагами", int((registry['кол-во_флагов'] > 0).sum()))

with st.expander(f"📋 Период: {report['period_range']} · что распознано в файле", expanded=False):
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("**✅ Найденные колонки:**")
        for k, v in report['columns_found'].items():
            st.markdown(f"- `{v}`")
    with cc2:
        if report['flags_skipped']:
            st.markdown("**⚠️ Пропущенные флаги:**")
            for f in report['flags_skipped']:
                st.markdown(f"- `{f['name']}` — {f['reason']}")
        else:
            st.markdown("**✅ Все флаги вычислены.**")

# ============ ВКЛАДКИ ============
tab_summary, tab_registry, tab_detail = st.tabs(["📊 Сводка", "📋 Реестр", "🔍 Абонент"])

# ------------ СВОДКА ------------
with tab_summary:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Распределение по числу флагов")
        flag_counts = registry['кол-во_флагов'].value_counts().sort_index()
        fig = go.Figure(go.Bar(
            x=flag_counts.index.astype(int).astype(str),
            y=flag_counts.values,
            text=flag_counts.values,
            textposition='outside',
            marker_color='#3498db',
        ))
        fig.update_layout(
            xaxis_title="Кол-во флагов", yaxis_title="Кол-во абонентов",
            height=350, margin=dict(t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Срабатывание каждого флага")
        flag_names = [f['name'] for f in FLAG_DEFINITIONS if f['name'] in flags.columns]
        flag_sums = [(n, int(flags[n].sum())) for n in flag_names]
        flag_sums.sort(key=lambda x: x[1], reverse=True)
        fig2 = go.Figure(go.Bar(
            y=[n for n, _ in flag_sums],
            x=[v for _, v in flag_sums],
            text=[v for _, v in flag_sums],
            textposition='outside',
            orientation='h',
            marker_color='#e74c3c',
        ))
        fig2.update_layout(
            xaxis_title="Кол-во абонентов",
            height=350, margin=dict(t=10, b=10, l=10),
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Сезонная классификация")
    seas = registry['сезонность'].value_counts()
    fig3 = go.Figure(go.Bar(
        x=seas.index, y=seas.values, text=seas.values, textposition='outside',
        marker_color=['#27ae60', '#e67e22', '#9b59b6', '#95a5a6'][:len(seas)],
    ))
    fig3.update_layout(height=300, margin=dict(t=10, b=10), yaxis_title="Кол-во абонентов")
    st.plotly_chart(fig3, use_container_width=True)

# ------------ РЕЕСТР ------------
with tab_registry:
    st.subheader("Реестр абонентов с флагами")

    fc1, fc2, fc3 = st.columns([1, 1, 2])
    with fc1:
        min_flags = st.number_input(
            "Мин. флагов", min_value=0, max_value=10, value=1, step=1
        )
    with fc2:
        seasons = ['(все)'] + list(registry['сезонность'].unique())
        season_filter = st.selectbox("Сезонность", seasons)
    with fc3:
        active_flag_filter = st.multiselect(
            "Только с этими флагами (И)",
            options=[c for c in flags.columns],
        )

    view = registry[registry['кол-во_флагов'] >= min_flags].copy()
    if season_filter != '(все)':
        view = view[view['сезонность'] == season_filter]
    for flag_name in active_flag_filter:
        view = view[view[flag_name] == True]

    st.caption(f"Показано: {len(view)} из {len(registry)} абонентов")
    st.dataframe(view, use_container_width=True, height=500)

    # Экспорт
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine='openpyxl') as w:
        view.to_excel(w, index=False, sheet_name='Реестр')
    st.download_button(
        "💾 Скачать реестр (Excel)",
        data=excel_buf.getvalue(),
        file_name="реестр_аномалий.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ------------ ДЕТАЛЬНЫЙ ВИД ПО АБОНЕНТУ ------------
with tab_detail:
    st.subheader("График потребления по абоненту")

    # Список с подписью
    def label(idx):
        r = registry.loc[idx]
        parts = [str(idx)]
        for col in ['Заводской номер прибора учета', 'Наименование точки учета',
                    'Населенный пункт', 'Улица', 'Дом']:
            if col in r and pd.notna(r[col]):
                parts.append(str(r[col]))
        flags_n = int(r.get('кол-во_флагов', 0))
        return f"#{idx} · {' · '.join(parts[1:])} · флагов: {flags_n}"

    # сортируем: сначала с большим числом флагов
    sorted_idx = registry.sort_values('кол-во_флагов', ascending=False).index.tolist()
    selected = st.selectbox(
        "Выберите абонента",
        options=sorted_idx,
        format_func=label,
    )

    if selected is not None:
        month_info = detect_month_columns(df_raw)
        month_cols = [c for (c, _, _) in month_info]
        periods = [pd.Period(f"{y}-{m:02d}", freq='M') for (_, y, m) in month_info]
        s = pd.to_numeric(df_raw.loc[selected, month_cols], errors='coerce')

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[p.to_timestamp() for p in periods],
            y=s.values,
            mode='lines+markers',
            line=dict(color='#2980b9', width=1.5),
            marker=dict(size=5),
            connectgaps=False,
            name='Потребление',
        ))
        fig.update_layout(
            xaxis_title="Месяц", yaxis_title="кВт·ч",
            height=400, margin=dict(t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        # карточка с флагами и метаданными
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Активные флаги:**")
            row_flags = [n for n in flags.columns if flags.loc[selected, n]]
            if row_flags:
                for n in row_flags:
                    st.markdown(f"- 🚩 `{n}`")
            else:
                st.markdown("✅ Без флагов")

            st.markdown("**Ключевые метрики:**")
            for k in ['active_months', 'mean_kwh', 'avg_recent', 'avg_baseline',
                      'drop_ratio', 'longest_silence', 'longest_flat_run',
                      'power_ratio', 'cohort_z', 'сезонность']:
                if k in registry.columns:
                    v = registry.loc[selected, k]
                    if pd.notna(v):
                        v_fmt = f"{v:.2f}" if isinstance(v, (int, float, np.floating)) else str(v)
                        st.markdown(f"- `{k}`: **{v_fmt}**")

        with c2:
            st.markdown("**Метаданные:**")
            for col in ['Вид потребителя', 'Заводской номер прибора учета',
                        'Наименование точки учета', 'Населенный пункт',
                        'Улица', 'Дом', 'Разрешенная мощность',
                        'Тип события', 'Дата события']:
                if col in registry.columns:
                    v = registry.loc[selected, col]
                    if pd.notna(v):
                        st.markdown(f"- **{col}:** {v}")

st.caption("Прототип. Данные обрабатываются и не сохраняются.")
