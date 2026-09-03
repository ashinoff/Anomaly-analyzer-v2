"""Анализатор ПУ · ТП — раздача статики.

Вся логика (парсинг выгрузки, алгоритмы S1–S14, баланс, калибровка) выполняется
В БРАУЗЕРЕ внутри index.html. Файлы выгрузки НЕ загружаются на сервер — поэтому
лимит тела запроса прокси Amvera (HTTP 413) здесь не играет роли вовсе.

Библиотека чтения Excel (static/xlsx.full.min.js) лежит локально в репозитории:
страница работает и без доступа в интернет.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
app = FastAPI(title="Анализатор ПУ · ТП")


@app.middleware("http")
async def _no_cache_page(request, call_next):
    """index.html — no-cache, чтобы после «Пересобрать» на Amvera браузер сразу
    подхватывал новую версию; статика ревалидируется по ETag."""
    resp = await call_next(request)
    if request.url.path in ("/", "/index.html"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(BASE / "index.html")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(BASE / "static" / "favicon.svg", media_type="image/svg+xml")


@app.get("/health")
def health():
    return {"status": "ok"}
