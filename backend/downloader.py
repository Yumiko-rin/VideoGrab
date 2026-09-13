"""yt-dlp 封装：视频解析、下载任务管理与进度上报。

下载任务在线程池中执行，进度通过 yt-dlp 的 progress_hooks 写入内存任务表，
前端以 ~1s 间隔轮询 /api/tasks 获取实时进度。取消下载通过在进度钩子中
抛出 DownloadError 实现（yt-dlp 官方支持的中断方式）。
"""
import os
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _detect_js_runtime() -> dict:
    """yt-dlp 2025.10+ 解析 YouTube 需要 JS 运行时解签名挑战，默认只认 deno；
    本机装有 node 时自动切换，避免触发 YouTube 机器人验证。"""
    if shutil.which("node"):
        return {"node": {}}
    return {}  # 留空保持 yt-dlp 默认行为


JS_RUNTIMES = _detect_js_runtime()

# YouTube 机器人验证是间歇性的（依赖当次请求指纹），轮换播放器客户端可显著提高通过率
_BOT_CHECK_MARKER = "Sign in to confirm"
_YT_CLIENT_FALLBACKS = [
    None,  # 先用 yt-dlp 默认客户端
    {"youtube": {"player_client": ["tv"]}},
    {"youtube": {"player_client": ["ios", "android_vr"]}},
]


def _is_bot_check(err_text: str) -> bool:
    return _BOT_CHECK_MARKER in err_text

PLATFORM_PATTERNS = [
    (r"bilibili\.com|b23\.tv", "Bilibili"),
    (r"youtube\.com|youtu\.be", "YouTube"),
    (r"douyin\.com|iesdouyin\.com", "抖音"),
    (r"tiktok\.com", "TikTok"),
    (r"twitter\.com|x\.com", "X (Twitter)"),
    (r"instagram\.com", "Instagram"),
    (r"kuaishou\.com", "快手"),
    (r"ixigua\.com", "西瓜视频"),
    (r"weibo\.com|weibo\.cn", "微博"),
    (r"vimeo\.com", "Vimeo"),
    (r"twitch\.tv", "Twitch"),
    (r"nicovideo\.jp", "niconico"),
]

MAX_VIDEO_FORMATS = 14
MAX_AUDIO_FORMATS = 6

_tasks: dict[str, dict] = {}
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="grab")


def detect_platform(url: str) -> str:
    for pattern, name in PLATFORM_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return name
    return "未知站点"


def _first_size(fmt: dict):
    return fmt.get("filesize") or fmt.get("filesize_approx")


def _normalize_formats(info: dict) -> list[dict]:
    """把 yt-dlp 的原始 format 列表压缩成前端友好的两档列表（视频/音频）。"""
    raw = info.get("formats") or []
    videos: dict[tuple, dict] = {}
    audios: dict[tuple, dict] = {}

    for f in raw:
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        if f.get("format_note") == "storyboard" or f.get("ext") == "mhtml":
            continue

        if vcodec != "none":
            height = f.get("height") or 0
            fps = int(f.get("fps") or 0)
            key = (height, fps, f.get("ext"))
            entry = {
                "format_id": f["format_id"],
                "kind": "video",
                "ext": f.get("ext"),
                "height": height,
                "fps": fps,
                "vcodec": (vcodec or "").split(".")[0],
                "acodec": (acodec or "none").split(".")[0],
                "tbr": f.get("tbr") or 0,
                "filesize": _first_size(f),
                "progressive": acodec != "none",
            }
            # 同一分辨率+扩展名保留码率最高的一条
            if key not in videos or entry["tbr"] > videos[key]["tbr"]:
                videos[key] = entry
        elif acodec != "none":
            abr = f.get("abr") or 0
            key = (f.get("ext"), round(abr))
            entry = {
                "format_id": f["format_id"],
                "kind": "audio",
                "ext": f.get("ext"),
                "abr": round(abr) if abr else None,
                "acodec": (acodec or "").split(".")[0],
                "filesize": _first_size(f),
            }
            if key not in audios or (entry["abr"] or 0) >= (audios[key]["abr"] or 0):
                audios[key] = entry

    video_list = sorted(videos.values(), key=lambda e: (e["height"], e["tbr"]), reverse=True)
    audio_list = sorted(audios.values(), key=lambda e: e["abr"] or 0, reverse=True)
    return video_list[:MAX_VIDEO_FORMATS] + audio_list[:MAX_AUDIO_FORMATS]


def parse_url(url: str) -> dict:
    """提取视频元信息与可选格式列表，不下载。YouTube 风控时自动轮换客户端重试。"""
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 20,
    }
    if JS_RUNTIMES:
        base_opts["js_runtimes"] = JS_RUNTIMES

    info, last_exc = None, None
    for client_args in _YT_CLIENT_FALLBACKS:
        opts = dict(base_opts)
        if client_args:
            opts["extractor_args"] = client_args
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            break
        except yt_dlp.utils.DownloadError as exc:
            last_exc = exc
            if not _is_bot_check(str(exc)):
                raise
            continue
    if info is None:
        raise last_exc  # type: ignore[misc]

    # 命中播放列表时取第一个条目
    if "entries" in info:
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise yt_dlp.utils.DownloadError("未能从该链接提取到视频")
        info = entries[0]

    return {
        "title": info.get("title") or "未知标题",
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "",
        "webpage_url": info.get("webpage_url") or url,
        "platform": detect_platform(info.get("webpage_url") or url),
        "extractor": info.get("extractor_key") or "",
        "formats": _normalize_formats(info),
        "ffmpeg": FFMPEG_AVAILABLE,
    }


def _capture_filename(task: dict, d: dict):
    """显示名只记录一次：去掉 yt-dlp 的中间流后缀（.f30016.mp4），保持稳定。"""
    if task.get("filename"):
        return
    raw_name = os.path.basename(d.get("filename") or "")
    if raw_name:
        task["filename"] = re.sub(r"\.f\d+(\.[A-Za-z0-9]+)$", r"\1", raw_name)


def _hook(task_id: str, d: dict):
    task = _tasks.get(task_id)
    if task is None:
        return
    if task.get("cancel"):
        raise yt_dlp.utils.DownloadError("用户已取消下载")

    status = d.get("status")
    if status == "downloading":
        total = d.get("total_bytes") or d.get("_total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0
        task.update(
            state="downloading",
            # HLS/分片流总大小未知 → percent=None，前端显示不定进度
            percent=round(done / total * 100, 1) if total else None,
            speed=d.get("speed"),
            eta=d.get("eta"),
            downloaded=done,
        )
        _capture_filename(task, d)
    elif status == "finished":
        task["percent"] = 99.0
        task["state"] = "processing"
        _capture_filename(task, d)


def _run_download(task_id: str, url: str, format_id: str | None, audio_only: bool):
    task = _tasks[task_id]

    if audio_only:
        fmt = "bestaudio/best"
    elif format_id:
        fmt = f"{format_id}+bestaudio/{format_id}/best" if FFMPEG_AVAILABLE else format_id
    else:
        fmt = "best"

    base_opts = {
        "format": fmt,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "windowsfilenames": True,
        "progress_hooks": [lambda d: _hook(task_id, d)],
    }
    if FFMPEG_AVAILABLE and not audio_only:
        base_opts["merge_output_format"] = "mp4"
    if JS_RUNTIMES:
        base_opts["js_runtimes"] = JS_RUNTIMES

    info, last_exc = None, None
    for client_args in _YT_CLIENT_FALLBACKS:
        if task.get("cancel"):
            break
        opts = dict(base_opts)
        if client_args:
            opts["extractor_args"] = client_args
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if not _is_bot_check(str(exc)):
                break
            continue  # 仅对风控拦截轮换客户端重试

    try:
        if info is not None:
            # 从最终下载结果取文件名（文件已存在被跳过时钩子不会触发，这里兜底）
            requested = info.get("requested_downloads") or []
            final_path = (requested[0].get("filepath") if requested else None) or info.get("filename")
            if final_path:
                task["filename"] = os.path.basename(final_path)
            task.update(state="completed", percent=100.0, eta=None, speed=None)
        elif task.get("cancel"):
            task.update(state="cancelled")
        else:
            task.update(state="error", error=str(last_exc).strip() or "下载失败")
    finally:
        task["ended_at"] = time.time()


def start_download(url: str, format_id: str | None = None, audio_only: bool = False) -> str:
    task_id = uuid.uuid4().hex[:12]
    with _lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "url": url,
            "format_id": format_id,
            "audio_only": audio_only,
            "state": "pending",
            "percent": 0.0,
            "downloaded": 0,
            "speed": None,
            "eta": None,
            "filename": "",
            "error": None,
            "created_at": time.time(),
            "ended_at": None,
            "cancel": False,
        }
    _executor.submit(_run_download, task_id, url, format_id, audio_only)
    return task_id


def cancel_task(task_id: str) -> bool:
    task = _tasks.get(task_id)
    if not task:
        return False
    task["cancel"] = True
    if task["state"] == "pending":
        task.update(state="cancelled", ended_at=time.time())
    return True


def get_tasks() -> list[dict]:
    with _lock:
        tasks = sorted(_tasks.values(), key=lambda t: t["created_at"], reverse=True)
        return [{k: v for k, v in t.items() if k != "cancel"} for t in tasks]


def list_files() -> list[dict]:
    files = []
    for name in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, name)
        if os.path.isfile(path):
            st = os.stat(path)
            files.append({"name": name, "size": st.st_size, "mtime": st.st_mtime})
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return files
