"""
Анализатор аномального потребления.
Архитектура: каждый флаг декларирует, какие колонки ему нужны.
Если колонки нет — флаг пропускается, остальное продолжает работать.
"""
import pandas as pd
import numpy as np
import re

DEFAULT_CONFIG = {
    "theft_recent_months": 12,
    "theft_baseline_months": 24,
    "theft_drop_pct": 0.5,
    "theft_min_baseline_kwh": 50,
    "silence_months": 6,
    "power_overrun_ratio": 1.0,
    "hours_per_month": 720,
    "season_summer_winter_ratio": 1.5,
    "season_winter_summer_ratio": 1.5,
    "cv_threshold": 1.2,
    "cohort_zscore": 3.0,
    "flat_run_months": 6,
    "min_active_months": 12,
}

MONTHS_RU = ['Январь','Февраль','Март','Апрель','Май','Июнь',
             'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']
MONTH_NUM = {m: i+1 for i, m in enumerate(MONTHS_RU)}
SUMMER = {6, 7, 8}
WINTER = {12, 1, 2}

COLUMN_ALIASES = {
    'permitted_power': ['Разрешенная мощность', 'Разрешённая мощность', 'Разр. мощность',
                        'Максимальная мощность'],
    'consumer_kind':   ['Вид потребителя', 'Тип потребителя', 'Категория потребителя'],
    'meter_id':        ['Заводской номер прибора учета', 'Заводской номер ПУ',
                        'Номер ПУ', 'Серийный номер ПУ'],
    'event_type':      ['Тип события'],
    'event_date':      ['Дата события'],
    'point_name':      ['Наименование точки учета', 'Точка учета'],
    'locality':        ['Населенный пункт', 'Населённый пункт'],
    'street':          ['Улица'],
    'house':           ['Дом'],
}

def resolve_columns(df):
    return {k: next((a for a in aliases if a in df.columns), None)
            for k, aliases in COLUMN_ALIASES.items()}


def detect_month_columns(df):
    out = []
    for c in df.columns:
        s = str(c).strip()
        for m, num in MONTH_NUM.items():
            if s.startswith(m + ' '):
                m_match = re.search(r'(\d{4})', s)
                if m_match:
                    out.append((c, int(m_match.group(1)), num))
                break
    out.sort(key=lambda x: (x[1], x[2]))
    return out


def to_long(df, month_info):
    rows = []
    for col, y, m in month_info:
        s = pd.to_numeric(df[col], errors='coerce')
        for i, v in s.items():
            if pd.notna(v):
                rows.append((i, y, m, float(v)))
    long = pd.DataFrame(rows, columns=['row_idx', 'year', 'month', 'kwh'])
    long['period'] = pd.PeriodIndex.from_fields(year=long['year'], month=long['month'], freq='M')
    return long


def longest_silence(rows, last_p):
    rows = rows.sort_values('period')
    if rows.empty: return 0
    first_p = rows['period'].min()
    all_periods = pd.period_range(first_p, last_p, freq='M')
    present = set(rows['period'])
    max_run, run = 0, 0
    for p in all_periods:
        if p in present: run = 0
        else:
            run += 1
            max_run = max(max_run, run)
    return max_run


def longest_flat(rows):
    rows = rows.sort_values('period')
    vals = rows['kwh'].values
    if len(vals) < 2: return 0
    max_run, run, prev = 1, 1, vals[0]
    for v in vals[1:]:
        if v == prev and v > 0:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
            prev = v
    return max_run


def robust_z(x):
    med = x.median()
    mad = (x - med).abs().median()
    return (x - med) / (1.4826 * mad + 1e-9)


# ============================================================
# Реестр флагов: каждый объявляет requires_cols
# ============================================================

FLAG_DEFINITIONS = []

def register_flag(name, requires_cols=None):
    def deco(fn):
        FLAG_DEFINITIONS.append({
            'name': name,
            'requires_cols': requires_cols or [],
            'compute': fn,
        })
        return fn
    return deco


@register_flag('подозрение_хищение')
def flag_theft(df, base, long, last_period, cols, cfg):
    recent_start = last_period - cfg["theft_recent_months"] + 1
    baseline_end = recent_start - 1
    baseline_start = baseline_end - cfg["theft_baseline_months"] + 1
    bucket = np.where(long['period'] >= recent_start, 'recent',
             np.where(long['period'] >= baseline_start, 'baseline', 'older'))
    pivot = long.assign(bucket=bucket).pivot_table(
        index='row_idx', columns='bucket', values='kwh', aggfunc='mean')
    for b in ('recent', 'baseline'):
        if b not in pivot.columns: pivot[b] = np.nan
    base['avg_recent'] = pivot['recent']
    base['avg_baseline'] = pivot['baseline']
    base['drop_ratio'] = 1 - base['avg_recent'] / base['avg_baseline']
    return ((base['avg_baseline'] >= cfg["theft_min_baseline_kwh"]) &
            (base['drop_ratio'] >= cfg["theft_drop_pct"]) &
            (base['active_months'] >= cfg["min_active_months"]))


@register_flag('долгое_молчание')
def flag_silence(df, base, long, last_period, cols, cfg):
    sil = long.groupby('row_idx').apply(
        lambda r: longest_silence(r, last_period), include_groups=False)
    base['longest_silence'] = sil
    base['months_silent_at_end'] = base['last_period'].apply(
        lambda p: (last_period - p).n if pd.notna(p) else 0)
    return ((base['longest_silence'] >= cfg["silence_months"]) |
            (base['months_silent_at_end'] >= cfg["silence_months"])) & \
           (base['active_months'] >= cfg["min_active_months"])


@register_flag('нестабильность')
def flag_unstable(df, base, long, last_period, cols, cfg):
    return base['cv'] >= cfg["cv_threshold"]


@register_flag('одинаковые_подряд')
def flag_flat(df, base, long, last_period, cols, cfg):
    fr = long.groupby('row_idx').apply(longest_flat, include_groups=False)
    base['longest_flat_run'] = fr
    return base['longest_flat_run'] >= cfg["flat_run_months"]


@register_flag('превышение_мощности', requires_cols=['permitted_power'])
def flag_power(df, base, long, last_period, cols, cfg):
    permitted = pd.to_numeric(df[cols['permitted_power']], errors='coerce')
    avg_power_peak = base['max_kwh'] / cfg["hours_per_month"]
    base['разрешенная_кВт'] = permitted.reindex(base.index)
    base['пиковая_средняя_кВт'] = avg_power_peak
    base['power_ratio'] = avg_power_peak / base['разрешенная_кВт']
    return base['power_ratio'] >= cfg["power_overrun_ratio"]


@register_flag('аномалия_в_когорте', requires_cols=['consumer_kind'])
def flag_cohort(df, base, long, last_period, cols, cfg):
    kind = df[cols['consumer_kind']].reindex(base.index)
    log_mean = np.log1p(base['mean_kwh'])
    z = log_mean.groupby(kind).transform(robust_z)
    base['cohort_z'] = z
    return base['cohort_z'].abs() >= cfg["cohort_zscore"]


# ============================================================

def analyze(df, config=None):
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    month_info = detect_month_columns(df)
    if not month_info:
        raise ValueError(
            "Не найдены столбцы помесячного потребления. "
            "Ожидаемый формат заголовка: 'Январь 2024', 'Февраль 2024' и т.д."
        )

    cols = resolve_columns(df)
    long = to_long(df, month_info)
    last_period = pd.Period(f"{month_info[-1][1]}-{month_info[-1][2]:02d}", freq='M')

    # ---- базовая статистика ----
    g = long.groupby('row_idx')
    base = pd.DataFrame({
        'active_months': g.size(),
        'total_kwh': g['kwh'].sum(),
        'mean_kwh': g['kwh'].mean(),
        'std_kwh': g['kwh'].std(),
        'max_kwh': g['kwh'].max(),
        'first_period': g['period'].min(),
        'last_period': g['period'].max(),
    })
    base = base.reindex(df.index)
    base['active_months'] = base['active_months'].fillna(0).astype(int)
    base['cv'] = (base['std_kwh'] / base['mean_kwh']).replace([np.inf, -np.inf], np.nan)

    # ---- сезонность ----
    long['season'] = long['month'].map(
        lambda m: 'summer' if m in SUMMER else 'winter' if m in WINTER else 'mid')
    season_avg = long.pivot_table(index='row_idx', columns='season',
                                  values='kwh', aggfunc='mean').fillna(0)
    for s in ('summer', 'winter', 'mid'):
        if s not in season_avg.columns: season_avg[s] = 0.0
    base = base.join(season_avg.add_prefix('avg_'))
    def season_label(r):
        s, w = r.get('avg_summer', 0), r.get('avg_winter', 0)
        if s == 0 and w == 0: return 'нет данных'
        if w > 0 and s / max(w, 1e-9) >= cfg["season_summer_winter_ratio"]:
            return 'летний (дача)'
        if s > 0 and w / max(s, 1e-9) >= cfg["season_winter_summer_ratio"]:
            return 'зимний (отопление)'
        return 'круглогодичный'
    base['сезонность'] = base.apply(season_label, axis=1)

    # ---- вычисление флагов ----
    flags = pd.DataFrame(index=df.index)
    flags_computed, flags_skipped = [], []
    for fdef in FLAG_DEFINITIONS:
        missing = [k for k in fdef['requires_cols'] if cols.get(k) is None]
        if missing:
            flags_skipped.append({
                'name': fdef['name'],
                'reason': f"нет колонки: {', '.join(COLUMN_ALIASES[k][0] for k in missing)}"
            })
            continue
        try:
            result = fdef['compute'](df, base, long, last_period, cols, cfg)
            flags[fdef['name']] = result.reindex(df.index).fillna(False).astype(bool)
            flags_computed.append(fdef['name'])
        except Exception as e:
            flags_skipped.append({'name': fdef['name'], 'reason': f"ошибка: {e}"})

    base['мало_данных'] = base['active_months'] < cfg["min_active_months"]
    base['кол-во_флагов'] = flags[flags_computed].sum(axis=1) if flags_computed else 0

    # ---- сборка реестра ----
    meta_cols = [cols[k] for k in
                 ['consumer_kind', 'meter_id', 'point_name', 'locality',
                  'street', 'house', 'permitted_power', 'event_type', 'event_date']
                 if cols.get(k)]
    meta = df[meta_cols].copy() if meta_cols else pd.DataFrame(index=df.index)

    extra_cols = ['active_months', 'mean_kwh', 'avg_recent', 'avg_baseline',
                  'drop_ratio', 'longest_silence', 'longest_flat_run',
                  'power_ratio', 'cohort_z', 'сезонность', 'мало_данных',
                  'кол-во_флагов']
    extra_cols = [c for c in extra_cols if c in base.columns]

    out = meta.join(flags).join(base[extra_cols])
    out = out.sort_values('кол-во_флагов', ascending=False)

    report = {
        'flags_computed': flags_computed,
        'flags_skipped': flags_skipped,
        'columns_found': {k: v for k, v in cols.items() if v},
        'columns_missing': [k for k, v in cols.items() if not v],
        'months_detected': len(month_info),
        'period_range': f"{month_info[0][0]} – {month_info[-1][0]}",
        'total_rows': len(df),
    }
    return out, base, flags, report


if __name__ == '__main__':
    import json
    df = pd.read_excel('/mnt/user-data/uploads/Лазаревский_РЭС2.xlsx')

    print(f"=== ПОЛНЫЙ ФАЙЛ ({len(df.columns)} колонок) ===")
    registry, base, flags, report = analyze(df)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    # имитация: выгрузка без 'Разрешенная мощность' и без 'Вид потребителя'
    months = [c for c in df.columns if any(c.startswith(m+' ') for m in MONTHS_RU)]
    df_minimal = df[['Заводской номер прибора учета'] + months]
    print(f"\n=== УРЕЗАННЫЙ ФАЙЛ ({len(df_minimal.columns)} колонок) ===")
    registry2, base2, flags2, report2 = analyze(df_minimal)
    print(json.dumps(report2, ensure_ascii=False, indent=2, default=str))

    print(f"\nФлаги в реестре (полный): {[c for c in registry.columns if c in [f['name'] for f in FLAG_DEFINITIONS]]}")
    print(f"Флаги в реестре (урезанный): {[c for c in registry2.columns if c in [f['name'] for f in FLAG_DEFINITIONS]]}")
    print(f"\nРаспределение по числу флагов (урезанный):")
    print(registry2['кол-во_флагов'].value_counts().sort_index().to_string())
