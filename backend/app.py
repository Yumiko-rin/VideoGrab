"""VideoGrab 后端入口：FastAPI 应用与静态页面托管。

启动：uvicorn backend.app:app --host 127.0.0.1 --port 8100
"""
import asyncio
import os
import re
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from .downloader import (
    DOWNLOAD_DIR,
    FFMPEG_AVAILABLE,
    JS_RUNTIMES,
    cancel_task,
    cookies_status,
    get_tasks,
    list_files,
    parse_url,
    start_download,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PARSE_TIMEOUT_SECONDS = 60

URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)

app = FastAPI(title="VideoGrab", version="0.1.0")


class ParseRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not URL_PATTERN.match(v):
            raise ValueError("链接格式不正确，需要以 http(s):// 开头")
        return v


class DownloadRequest(BaseModel):
    url: str
    format_id: str | None = None
    audio_only: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not URL_PATTERN.match(v):
            raise ValueError("链接格式不正确，需要以 http(s):// 开头")
        return v


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "ffmpeg": FFMPEG_AVAILABLE,
        "js_runtime": next(iter(JS_RUNTIMES), "default(deno)"),
        "cookies": cookies_status(),
        "yt_dlp": yt_dlp.version.__version__,
    }


@app.post("/api/parse")
async def api_parse(req: ParseRequest):
    try:
        info = await asyncio.wait_for(
            asyncio.to_thread(parse_url, req.url), timeout=PARSE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="解析超时，站点响应过慢或网络受限") from None
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(status_code=422, detail=_clean_error(str(exc))) from None
    return info


@app.post("/api/downloads")
async def api_create_download(req: DownloadRequest):
    task_id = start_download(req.url, req.format_id, req.audio_only)
    return {"task_id": task_id}


@app.get("/api/tasks")
async def api_tasks():
    return get_tasks()


@app.delete("/api/tasks/{task_id}")
async def api_cancel_task(task_id: str):
    if not cancel_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@app.get("/api/files")
async def api_files():
    return list_files()


@app.get("/files/{name}")
async def api_file(name: str):
    # 只允许访问 downloads 目录内的文件，路径穿越防护
    safe = Path(name).name
    path = Path(DOWNLOAD_DIR) / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=safe)


@app.post("/api/open-folder")
async def api_open_folder():
    """在系统资源管理器中打开下载目录（本工具面向本机使用）。"""
    try:
        os.startfile(DOWNLOAD_DIR)  # noqa: S606 - Windows 资源管理器打开目录
    except (OSError, AttributeError) as exc:
        raise HTTPException(status_code=500, detail=f"无法打开文件夹：{exc}") from None
    return {"ok": True}


def _clean_error(raw: str) -> str:
    """把 yt-dlp 的长报错压缩成一句用户能看懂的话。"""
    raw = raw.replace("ERROR: ", "").strip()
    if "Unsupported URL" in raw:
        return "暂不支持该链接，可尝试更新 yt-dlp：pip install -U yt-dlp"
    if "Video unavailable" in raw:
        return "视频不可用（可能已删除、设为私享或地区限制）"
    if "Sign in to confirm" in raw:
        return "YouTube 风控拦截：已自动轮换多个客户端仍被拦，请稍后重试；频繁出现时需为 yt-dlp 配置浏览器 cookies"
    if "Fresh cookies" in raw or "cookies" in raw.lower():
        return ("该站点需要浏览器 cookies：在项目根目录放置 cookies.txt（Netscape 格式），"
                "或设置环境变量 VIDEOGRAB_COOKIES_BROWSER=edge 后重启，配置方法见 README")
    if "is not a valid URL" in raw:
        return "链接格式不正确"
    return raw[:180]


# API 路由注册之后再挂载静态站点，保证 /api/* 优先匹配
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
