"""
FastAPI-приложение: анализ аномального потребления.

Почему FastAPI, а не Streamlit: встроенный загрузчик Streamlit шлёт файл одним
большим HTTP-запросом, который режет прокси Amvera (HTTP 413). Здесь файл
грузится «чанками» (мелкими кусками) — каждый запрос заведомо под лимитом, а на
сервере куски склеиваются в памяти. Ничего не пишется на диск: файл, результаты
и Excel-отчёт живут только в оперативной памяти и вычищаются.

Алгоритмы (analyzer.py) и выгрузка Excel (excel_export.py) НЕ тронуты — вызываем
их как есть. Метаданные интерфейса — в ui_meta.py.
"""
import io
import json
from collections import OrderedDict
from urllib.parse import quote

import numpy as np
import pandas as pd
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from analyzer import analyze, detect_month_columns, FLAG_DEFINITIONS
from excel_export import build_full_report, build_subscriber_card
import ui_meta as M

BASE = Path(__file__).parent
app = FastAPI(title="Анализ потребления")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# ── Хранилища в памяти (ничего не пишем на диск) ──────────────────────────
# UPLOADS: сборка чанков, FILES: распарсенный DataFrame, RESULTS: результат
# анализа под текущий конфиг. Ограничиваем размер, чтобы память не текла.
_UPLOADS: "OrderedDict[str, dict]" = OrderedDict()
_FILES: "OrderedDict[str, pd.DataFrame]" = OrderedDict()
_RESULTS: "OrderedDict[str, dict]" = OrderedDict()
_MAX_KEEP = 6


def _prune(store: OrderedDict):
    while len(store) > _MAX_KEEP:
        store.popitem(last=False)


def _cd(filename: str) -> dict:
    """Content-Disposition с кириллицей: ASCII-фолбэк + filename* (RFC 5987).
    HTTP-заголовки только latin-1, поэтому имя с кириллицей — через filename*."""
    ascii_name = filename.encode("ascii", "ignore").decode() or "report.xlsx"
    return {"Content-Disposition":
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"}


# ── Утилиты ───────────────────────────────────────────────────────────────
def _label_for(col):
    return M.METRIC_LABELS.get(col, M.FLAG_TITLES.get(col, col))


def _fmt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}".replace(",", " ")
    if isinstance(v, (float, np.floating)):
        return f"{float(v):,.2f}".replace(",", " ")
    return str(v)


def _run_analysis(file_id: str, values: dict):
    """Прогнать анализ под заданные пороги, закэшировать результат."""
    if file_id not in _FILES:
        raise HTTPException(404, "Файл не найден или устарел — загрузите заново")
    df = _FILES[file_id]
    cfg = M.apply_params(values or {})
    registry, base, flags, report = analyze(df, cfg)
    _RESULTS[file_id] = dict(df=df, registry=registry, base=base, flags=flags,
                             report=report, config=cfg,
                             month_info=detect_month_columns(df))
    _prune(_RESULTS)
    return _RESULTS[file_id]


def _summary_payload(res: dict) -> dict:
    registry, flags, report = res["registry"], res["flags"], res["report"]

    n_with_flags = int((registry["кол-во_флагов"] > 0).sum())
    n_high_risk = int((registry["риск_балл"] >= 5).sum())

    # распределение по числу флагов
    vc = registry["кол-во_флагов"].value_counts().sort_index()
    by_flag_count = {"labels": [str(int(k)) for k in vc.index],
                     "values": [int(v) for v in vc.values]}

    # срабатывание каждого флага (по порядку определений)
    flag_names = [f["name"] for f in FLAG_DEFINITIONS if f["name"] in flags.columns]
    per_flag = sorted(
        [{"key": n, "title": M.FLAG_TITLES.get(n, n),
          "color": M.FLAG_COLOR.get(n, "#5AA2FF"), "count": int(flags[n].sum())}
         for n in flag_names],
        key=lambda x: x["count"])

    # сезонная классификация
    sc = registry["сезонность"].value_counts()
    seasons = [{"name": str(k), "color": M.SEASON_COLOR.get(k, "#6F83AC"),
                "count": int(v)} for k, v in sc.items()]

    # реестр целиком (для таблицы, фильтров и селектора абонента на клиенте)
    reg2 = registry.copy()
    reg2.insert(0, "_idx", registry.index)
    rows = json.loads(reg2.to_json(orient="records", force_ascii=False, date_format="iso"))
    columns = [c for c in reg2.columns]
    labels = {c: _label_for(c) for c in columns}

    return {
        "file_id": None,  # проставляется вызывающим
        "report": {
            "total_rows": int(report["total_rows"]),
            "months_detected": int(report["months_detected"]),
            "period_range": report.get("period_range", ""),
            "columns_found": report.get("columns_found", {}),
            "flags_skipped": report.get("flags_skipped", []),
        },
        "metrics": {
            "total_rows": int(report["total_rows"]),
            "months_detected": int(report["months_detected"]),
            "n_with_flags": n_with_flags,
            "n_high_risk": n_high_risk,
        },
        "charts": {"by_flag_count": by_flag_count, "per_flag": per_flag, "seasons": seasons},
        "flag_cols": list(flags.columns),
        "registry": {"columns": columns, "labels": labels, "rows": rows},
    }


# ── Метаданные интерфейса ──────────────────────────────────────────────────
@app.get("/api/meta")
def meta():
    return {
        "flag_icons": M.FLAG_ICON,
        "flag_titles": M.FLAG_TITLES,
        "flag_colors": M.FLAG_COLOR,
        "flag_legend": [{"key": k, "title": M.FLAG_TITLES.get(k, k),
                         "color": M.FLAG_COLOR.get(k, "#5AA2FF"),
                         "icon": M.FLAG_ICON.get(k, ""), "desc": d}
                        for k, d in M.FLAG_LEGEND_DESC.items()],
        "metric_labels": M.METRIC_LABELS,
        "param_groups": M.PARAM_GROUPS,
        "algo_info": M.ALGO_INFO,
    }


# ── Чанковая загрузка ──────────────────────────────────────────────────────
@app.post("/api/upload/chunk")
async def upload_chunk(
    uploadId: str = Form(...),
    index: int = Form(...),
    total: int = Form(...),
    chunk: UploadFile = File(...),
):
    data = await chunk.read()
    slot = _UPLOADS.get(uploadId)
    if slot is None:
        slot = {"total": total, "parts": {}}
        _UPLOADS[uploadId] = slot
        _prune(_UPLOADS)
    slot["parts"][index] = data

    if len(slot["parts"]) < slot["total"]:
        return {"ok": True, "received": len(slot["parts"]), "total": slot["total"]}

    # все куски собраны — склеиваем и парсим Excel
    buf = b"".join(slot["parts"][i] for i in range(slot["total"]))
    _UPLOADS.pop(uploadId, None)
    try:
        df = pd.read_excel(io.BytesIO(buf))
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать Excel: {e}")
    if not detect_month_columns(df):
        raise HTTPException(400, "Не найдены столбцы помесячного потребления "
                                 "(ожидается формат «Январь 2024», «Февраль 2024» …)")
    _FILES[uploadId] = df
    _prune(_FILES)
    return {"ok": True, "complete": True, "file_id": uploadId,
            "rows": int(len(df)), "size": len(buf)}


# ── Анализ ─────────────────────────────────────────────────────────────────
@app.post("/api/analyze")
async def analyze_endpoint(payload: dict):
    file_id = payload.get("file_id")
    values = payload.get("params", {})
    try:
        res = _run_analysis(file_id, values)
    except ValueError as e:
        raise HTTPException(400, str(e))
    out = _summary_payload(res)
    out["file_id"] = file_id
    return JSONResponse(out)


# ── Карточка абонента (данные для экрана) ──────────────────────────────────
@app.get("/api/subscriber/{file_id}/{idx}")
def subscriber(file_id: str, idx: int):
    res = _RESULTS.get(file_id)
    if not res:
        raise HTTPException(404, "Сначала выполните анализ")
    df, registry, flags = res["df"], res["registry"], res["flags"]
    if idx not in registry.index:
        raise HTTPException(404, "Абонент не найден")
    month_info = res["month_info"]
    month_cols = [c for (c, _, _) in month_info]
    s = pd.to_numeric(df.loc[idx, month_cols], errors="coerce")
    series = [{"t": f"{y}-{m:02d}",
               "v": (None if pd.isna(val) else float(val))}
              for (_, y, m), val in zip(month_info, s.values)]

    active = [{"key": n, "title": M.FLAG_TITLES.get(n, n),
               "color": M.FLAG_COLOR.get(n, "#5AA2FF"), "icon": M.FLAG_ICON.get(n, "")}
              for n in flags.columns if bool(flags.loc[idx, n])]

    metrics = []
    for k in M.SUBSCRIBER_METRIC_KEYS:
        if k in registry.columns:
            fv = _fmt(registry.loc[idx, k])
            if fv is not None:
                metrics.append({"label": M.METRIC_LABELS.get(k, k), "value": fv})

    meta = []
    for col in M.SUBSCRIBER_META_COLS:
        if col in registry.columns:
            v = registry.loc[idx, col]
            if pd.notna(v):
                meta.append({"label": col, "value": str(v)})

    return {"idx": idx, "series": series, "flags": active,
            "metrics": metrics, "meta": meta}


# ── Скачивание: полный отчёт ───────────────────────────────────────────────
@app.get("/api/report/{file_id}")
def report_download(file_id: str):
    res = _RESULTS.get(file_id)
    if not res:
        raise HTTPException(404, "Сначала выполните анализ")
    data = build_full_report(res["df"], res["registry"], res["base"], res["flags"],
                             res["report"], res["config"], M.FLAG_TITLES, {},
                             M.METRIC_LABELS, res["month_info"])
    fname = f"анализ_потребления_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(io.BytesIO(data), media_type=XLSX_MIME,
                             headers=_cd(fname))


# ── Скачивание: карточка абонента ──────────────────────────────────────────
@app.get("/api/subscriber/{file_id}/{idx}/card")
def subscriber_card(file_id: str, idx: int):
    res = _RESULTS.get(file_id)
    if not res:
        raise HTTPException(404, "Сначала выполните анализ")
    if idx not in res["registry"].index:
        raise HTTPException(404, "Абонент не найден")
    data = build_subscriber_card(res["df"], res["registry"], res["base"], res["flags"],
                                 idx, M.FLAG_TITLES, {}, M.METRIC_LABELS, res["month_info"])
    return StreamingResponse(io.BytesIO(data), media_type=XLSX_MIME,
                             headers=_cd(f"абонент_{idx}.xlsx"))


# ── Скачивание: текущая выборка реестра ────────────────────────────────────
@app.post("/api/registry/export")
def registry_export(payload: dict):
    file_id = payload.get("file_id")
    indices = payload.get("indices")
    res = _RESULTS.get(file_id)
    if not res:
        raise HTTPException(404, "Сначала выполните анализ")
    registry, flags = res["registry"], res["flags"]
    view = registry if indices is None else registry.loc[[i for i in indices if i in registry.index]]
    display_view = view.rename(columns={
        **M.METRIC_LABELS,
        **{k: M.FLAG_TITLES.get(k, k) for k in flags.columns},
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        display_view.to_excel(w, index=False, sheet_name="Реестр")
    fname = f"выборка_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(io.BytesIO(buf.getvalue()), media_type=XLSX_MIME,
                             headers=_cd(fname))


@app.get("/api/health")
def health():
    return {"ok": True}


# ── Статика и страница ─────────────────────────────────────────────────────
app.mount("/assets", StaticFiles(directory=str(BASE / "assets")), name="assets")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.get("/")
def index():
    return FileResponse(str(BASE / "static" / "index.html"))
