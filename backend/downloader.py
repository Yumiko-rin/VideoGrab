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

# 出海站点（TikTok / X / Instagram）在国内网络需要代理：VIDEOGRAB_PROXY=http://127.0.0.1:7890
PROXY = os.environ.get("VIDEOGRAB_PROXY", "").strip() or None

# YouTube 机器人验证是间歇性的（依赖当次请求指纹），轮换播放器客户端可显著提高通过率
_BOT_CHECK_MARKER = "Sign in to confirm"
_YT_CLIENT_FALLBACKS = [
    None,  # 先用 yt-dlp 默认客户端
    {"youtube": {"player_client": ["tv"]}},
    {"youtube": {"player_client": ["ios", "android_vr"]}},
]


def _is_bot_check(err_text: str) -> bool:
    return _BOT_CHECK_MARKER in err_text


# ---------- Cookies 配置：cookies.txt 文件 > 环境变量指定浏览器 > 抖音自动 ttwid ----------

COOKIES_FILE = os.path.join(PROJECT_ROOT, "cookies.txt")


def _user_cookie_opts() -> dict:
    """用户显式配置的 cookies：根目录 cookies.txt（Netscape 格式）
    或环境变量 VIDEOGRAB_COOKIES_BROWSER（edge/chrome/firefox）。"""
    if os.path.isfile(COOKIES_FILE):
        return {"cookiefile": COOKIES_FILE}
    browser = os.environ.get("VIDEOGRAB_COOKIES_BROWSER", "").strip().lower()
    if browser:
        return {"cookiesfrombrowser": (browser,)}
    return {}


def _cookie_opts_for(url: str) -> dict:
    if _user_cookie_opts():
        return _user_cookie_opts()
    if is_douyin_url(url):
        return _douyin_session_opts(url)
    if re.search(r"bilibili\.com|b23\.tv", url, re.IGNORECASE):
        return _bilibili_cookie_opts()
    return {}


def cookies_status() -> str:
    if os.path.isfile(COOKIES_FILE):
        return "cookies.txt"
    browser = os.environ.get("VIDEOGRAB_COOKIES_BROWSER", "").strip().lower()
    if browser:
        return f"browser:{browser}"
    return "自动（抖音 Playwright 自举 + B站 buvid）"


# ---------- 抖音：Playwright 真内核自举会话 + yt-dlp 提取（无需用户 cookies） ----------
# 抖音要求 ttwid + s_v_web_id 等匿名 cookie（无需登录，但必须来自真实浏览器环境）。
# 用无头 Chromium 访问抖音生成一整套会话 cookie 并导出，yt-dlp 携带后即可正常
# 解析与下载；cookie 缓存 2 小时，过期自动重新生成。

DOUYIN_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/126.0.0.0 Safari/537.36")
_DOUYIN_HOST_RE = re.compile(r"douyin\.com|iesdouyin\.com", re.IGNORECASE)
DOUYIN_SESSION_FILE = os.path.join(PROJECT_ROOT, ".douyin_session.cookies")
DOUYIN_SESSION_TTL = 2 * 3600


def is_douyin_url(url: str) -> bool:
    return bool(_DOUYIN_HOST_RE.search(url))


def normalize_douyin_url(url: str) -> str:
    """抖音变体链接归一化：yt-dlp 的 Douyin 提取器只认 /video/<id>。
    精选页 /jingxuan?modal_id=<id>、个人页弹窗 ?modal_id= 等都携带真实视频 id，
    重写为标准视频页链接即可解析。"""
    match = re.search(r"modal_id=(\d{15,})", url)
    if match:
        return f"https://www.douyin.com/video/{match.group(1)}"
    return url


def douyin_playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _write_netscape_cookies(path: str, cookies: list[dict]):
    import time as _time
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            expires = int(c.get("expires") or 0)
            if expires <= 0:
                expires = int(_time.time()) + 86400 * 30
            domain = c.get("domain") or ".douyin.com"
            fh.write(f"{domain if domain.startswith('.') else '.' + domain.lstrip('.')}\tTRUE\t"
                     f"{c.get('path') or '/'}\t{'TRUE' if c.get('secure') else 'FALSE'}\t"
                     f"{expires}\t{c['name']}\t{c['value']}\n")


def _douyin_session_opts(url: str) -> dict:
    """确保存在新鲜的抖音会话 cookie 文件；缺失或过期时用 Playwright 现生成。
    生成方式：无头 Chromium 依次访问抖音首页与目标视频页（让风控脚本完整执行），
    然后导出整套 cookie。失败时返回空配置，由上游给出可操作的错误指引。"""
    if os.path.isfile(DOUYIN_SESSION_FILE) and \
            time.time() - os.path.getmtime(DOUYIN_SESSION_FILE) < DOUYIN_SESSION_TTL:
        return {"cookiefile": DOUYIN_SESSION_FILE}
    if not douyin_playwright_available():
        return {}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled", "--no-sandbox"])
            try:
                ctx = browser.new_context(
                    user_agent=DOUYIN_UA,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"})
                page = ctx.new_page()
                page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(4000)
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(8000)
                cookies = ctx.cookies("https://www.douyin.com")
            finally:
                browser.close()
        if not any(c["name"] == "s_v_web_id" for c in cookies):
            return {}  # 风控脚本未执行完整，宁缺毋滥，交给上游报错
        _write_netscape_cookies(DOUYIN_SESSION_FILE, cookies)
        return {"cookiefile": DOUYIN_SESSION_FILE}
    except Exception:  # noqa: BLE001 - 任何自举失败都降级为无 cookie
        return {}


# ---------- 小红书：直连笔记页解析 __INITIAL_STATE__（与 RuiC-VideoGrab 同源思路） ----------
# 无 cookie 尽力而为；被要求登录（461）时给出可操作指引。

_XHS_HOST_RE = re.compile(r"xiaohongshu\.com|xhslink\.com", re.IGNORECASE)


def is_xhs_url(url: str) -> bool:
    return bool(_XHS_HOST_RE.search(url))


def _xhs_find_note(html: str, note_id: str) -> dict | None:
    """从笔记页 HTML 解析 note 对象；页面 JSON 含非标准 undefined，先规范为 null。"""
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", html, re.DOTALL)
    if not match:
        return None
    import json as _json
    try:
        state = _json.loads(re.sub(r":\s*undefined([,}])", r":null\1", match.group(1)))
    except ValueError:
        return None
    note_map = (state.get("note") or {}).get("noteDetailMap") or {}
    note = (note_map.get(note_id) or {}).get("note")
    if not isinstance(note, dict):
        # 兼容旧版结构：map 键名可能不是 note_id，按 noteId 字段匹配
        for entry in note_map.values():
            candidate = entry.get("note") if isinstance(entry, dict) else None
            if isinstance(candidate, dict) and candidate.get("noteId") == note_id:
                return candidate
        return None
    return note


def _xhs_note_id(url: str) -> str | None:
    match = re.search(r"/(?:explore|discovery/item)/([0-9a-f]{24})", url)
    return match.group(1) if match else None


def _xhs_video_stream(note: dict) -> str | None:
    try:
        streams = note["video"]["media"]["stream"]
        for codec in ("h264", "h265", "av1"):
            items = streams.get(codec) or []
            if items:
                return items[0].get("masterUrl") or (items[0].get("backupUrls") or [None])[0]
    except (KeyError, IndexError, TypeError):
        return None
    return None


def _xhs_fetch_note(url: str) -> dict:
    """跟随短链重定向（保留 xsec_token 分享参数），抓取并解析笔记。"""
    import urllib.request

    req = urllib.request.Request(url, headers={
        "User-Agent": DOUYIN_UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            final_url, html = resp.geturl(), resp.read().decode("utf-8", "ignore")
    except OSError as exc:
        raise yt_dlp.utils.DownloadError(f"小红书页面请求失败：{exc}") from exc

    note_id = _xhs_note_id(final_url) or _xhs_note_id(url)
    if not note_id:
        raise yt_dlp.utils.DownloadError("无法解析小红书笔记 ID，请检查链接是否完整")
    if "登录后查看" in html:
        raise yt_dlp.utils.DownloadError(
            "小红书需要登录 cookies：在项目根目录放置 cookies.txt 后重试（见 README）")
    note = _xhs_find_note(html, note_id)
    if not isinstance(note, dict):
        raise yt_dlp.utils.DownloadError("未找到笔记内容：可能已删除、仅粉丝可见，或需要登录 cookies")

    images = [img.get("urlDefault") or img.get("url")
              for img in (note.get("imageList") or []) if img.get("urlDefault") or img.get("url")]
    stream = _xhs_video_stream(note) if note.get("type") == "video" else None
    if not stream and not images:
        raise yt_dlp.utils.DownloadError("笔记里没有可下载的视频或图片（可能需要登录 cookies）")

    if note.get("type") == "video":
        video = (note.get("video") or {}).get("media") or {}
        formats = [{
            "format_id": "xhs-video",
            "kind": "video", "ext": "mp4", "height": 0,
            "tier": _quality_tier(video.get("height") or 0, video.get("width") or 0), "fps": 0,
            "vcodec": "avc1", "acodec": "mp4a", "tbr": 0,
            "filesize": None, "progressive": True,
        }]
    else:
        formats = [{
            "format_id": "xhs-images", "kind": "video", "ext": "zip", "height": 0,
            "tier": None, "fps": 0, "vcodec": "", "acodec": "", "tbr": 0,
            "filesize": None, "progressive": True, "images_count": len(images),
        }]

    return {
        "title": (note.get("title") or "").strip()
                 or f"{(note.get('user') or {}).get('nickname', '')}的笔记",
        "thumbnail": images[0] if images else None,
        "duration": None,
        "uploader": (note.get("user") or {}).get("nickname") or "",
        "webpage_url": url,
        "platform": "小红书",
        "extractor": "Xhs",
        "formats": formats,
        "ffmpeg": FFMPEG_AVAILABLE,
    }


def _run_xhs_direct(task: dict, url: str):
    """小红书直链下载：视频流式落盘；图集逐张下载后打包 zip。"""
    import urllib.request
    import zipfile

    def _fetch(u: str) -> urllib.request.Request:
        return urllib.request.Request(u, headers={
            "User-Agent": DOUYIN_UA, "Referer": "https://www.xiaohongshu.com/"})

    def _stream_to(path: str, u: str):
        req = _fetch(u)
        done = 0
        started = time.time()
        with urllib.request.urlopen(req, timeout=60) as resp, open(path, "wb") as fh:
            length = int(resp.headers.get("Content-Length") or 0)
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if task.get("cancel"):
                    raise yt_dlp.utils.DownloadError("用户已取消下载")
                task.update(state="downloading", speed=done / max(time.time() - started, 0.001),
                            downloaded=done,
                            percent=round(done / length * 100, 1) if length else None)
                _capture_filename(task, {"filename": path})

    path = None
    try:
        note_id = _xhs_note_id(url)
        info = _xhs_fetch_note(url)
        note_id = note_id or _xhs_note_id(info["webpage_url"])
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", info["title"]).strip() or "小红书笔记"

        # 重新抓一次页面拿原始 note（下载阶段需要完整的 imageList / 视频流）
        with urllib.request.urlopen(urllib.request.Request(
                info["webpage_url"],
                headers={"User-Agent": DOUYIN_UA, "Accept": "text/html,application/xhtml+xml"}),
                timeout=25) as resp:
            html = resp.read().decode("utf-8", "ignore")
        note = _xhs_find_note(html, note_id) or {}
        images = [img.get("urlDefault") or img.get("url")
                  for img in (note.get("imageList") or []) if img.get("urlDefault") or img.get("url")]
        stream = _xhs_video_stream(note) if note.get("type") == "video" else None

        if stream:
            path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp4")
            _stream_to(path, stream)
        elif images:
            buffers = []
            for i, img in enumerate(images):
                if task.get("cancel"):
                    raise yt_dlp.utils.DownloadError("用户已取消下载")
                with urllib.request.urlopen(_fetch(img), timeout=60) as resp:
                    buffers.append((f"{i + 1:02d}.jpg", resp.read()))
                task.update(state="downloading", percent=round((i + 1) / len(images) * 100, 1),
                            speed=None, eta=None, downloaded=i + 1)
                _capture_filename(task, {"filename": f"{safe_title}.zip"})
            path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.zip")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
                for name, data in buffers:
                    zf.writestr(name, data)
        else:
            raise yt_dlp.utils.DownloadError("笔记里没有可下载的视频或图片")
        task.update(state="completed", percent=100.0, eta=None, speed=None)
    except yt_dlp.utils.DownloadError as exc:
        if task.get("cancel"):
            task.update(state="cancelled")
        else:
            task.update(state="error", error=str(exc).strip() or "小红书下载失败")
        if path and task["state"] != "completed" and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    finally:
        task["ended_at"] = time.time()


# ---------- 快手：Playwright 拦截作品 GraphQL（参考 KS-Downloader，真内核过风控） ----------

_KS_HOST_RE = re.compile(r"kuaishou\.com|gifshow\.com", re.IGNORECASE)


def is_kuaishou_url(url: str) -> bool:
    return bool(_KS_HOST_RE.search(url))


def _ks_fetch_photo(url: str) -> dict:
    """Playwright 打开作品页，拦截页面自身发出的 visionVideoDetail GraphQL 响应。
    快手 GraphQL 有风控 token 校验（脚本签发），只有真实浏览器环境能通过——
    API 直连（含 curl_cffi TLS 伪装）会被要求验证码。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise yt_dlp.utils.DownloadError(
            "快手解析需要 Playwright：pip install playwright && playwright install chromium") from None

    result: dict = {}

    def _on_response(resp):
        try:
            if resp.request.method == "POST" and "graphql" in resp.url:
                body = resp.json()
                detail = (body.get("data") or {}).get("visionVideoDetail") or {}
                photo = detail.get("photo")
                if isinstance(photo, dict) and photo.get("photoUrl"):
                    result.setdefault("photo", photo)
        except Exception:
            pass

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled", "--no-sandbox"])
            try:
                ctx = browser.new_context(
                    user_agent=DOUYIN_UA,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN")
                page = ctx.new_page()
                page.on("response", _on_response)
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(8000)
            finally:
                browser.close()
    except yt_dlp.utils.DownloadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise yt_dlp.utils.DownloadError(f"快手解析失败：{str(exc)[:120]}") from exc

    photo = result.get("photo")
    if not photo:
        raise yt_dlp.utils.DownloadError("未能从快手页面获取作品数据（可能触发验证码风控，请稍后重试）")

    photo_url = photo.get("photoUrl")
    if isinstance(photo_url, list):
        photo_url = photo_url[0] if photo_url else None
    if not photo_url:
        raise yt_dlp.utils.DownloadError("作品没有可下载的视频地址（可能需要登录）")
    author = photo.get("author") or {}
    return {
        "title": (photo.get("caption") or "").strip() or "快手作品",
        "uploader": (author.get("name") or "") if isinstance(author, dict) else "",
        "duration": (photo.get("duration") or 0) / 1000 or None,
        "thumbnail": photo.get("coverUrl") if isinstance(photo.get("coverUrl"), str) else None,
        "video_url": photo_url,
        "filesize": None,
        "webpage_url": url,
        "ext": "mp4",
    }


def _ks_parse(url: str) -> dict:
    photo = _ks_fetch_photo(url)
    return {
        "title": photo["title"],
        "thumbnail": photo["thumbnail"],
        "duration": photo["duration"],
        "uploader": photo["uploader"],
        "webpage_url": photo["webpage_url"],
        "platform": "快手",
        "extractor": "Kuaishou",
        "formats": [{
            "format_id": "ks-nowm",
            "kind": "video",
            "ext": photo["ext"],
            "height": 0,
            "tier": None,
            "fps": 0,
            "vcodec": "avc1",
            "acodec": "mp4a",
            "tbr": 0,
            "filesize": photo["filesize"],
            "progressive": True,
        }],
        "ffmpeg": FFMPEG_AVAILABLE,
    }


def _run_ks_direct(task: dict, url: str):
    """快手直链下载：photoUrl 带时效与防盗链，任务开始时重新解析。"""
    import urllib.request

    path = None
    try:
        photo = _ks_fetch_photo(url)
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", photo["title"]).strip() or "快手作品"
        path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp4")
        req = urllib.request.Request(photo["video_url"], headers={
            "User-Agent": DOUYIN_UA, "Referer": "https://www.kuaishou.com/"})
        started = time.time()
        done = 0
        with urllib.request.urlopen(req, timeout=60) as resp, open(path, "wb") as fh:
            length = int(resp.headers.get("Content-Length") or 0) or photo["filesize"] or 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if task.get("cancel"):
                    raise yt_dlp.utils.DownloadError("用户已取消下载")
                task.update(
                    state="downloading",
                    percent=round(done / length * 100, 1) if length else None,
                    speed=done / max(time.time() - started, 0.001),
                    eta=None, downloaded=done,
                )
                _capture_filename(task, {"filename": path})
        task.update(state="completed", percent=100.0, eta=None, speed=None)
    except yt_dlp.utils.DownloadError as exc:
        if task.get("cancel"):
            task.update(state="cancelled")
        else:
            task.update(state="error", error=str(exc).strip() or "快手下载失败")
        if path and task["state"] != "completed" and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    finally:
        task["ended_at"] = time.time()


# ---------- B 站风控自举：官方指纹接口生成 buvid3/buvid4，绕过 412 ----------

_BILI_SPI_URL = "https://api.bilibili.com/x/frontend/finger/spi"
_BILI_BOOTSTRAP_FILE = os.path.join(PROJECT_ROOT, ".bilibili_bootstrap.cookies")
_BILI_BOOTSTRAP_TTL = 6 * 3600


def _bilibili_cookie_opts() -> dict:
    if os.path.isfile(_BILI_BOOTSTRAP_FILE) and \
            time.time() - os.path.getmtime(_BILI_BOOTSTRAP_FILE) < _BILI_BOOTSTRAP_TTL:
        return {"cookiefile": _BILI_BOOTSTRAP_FILE}
    import json as _json
    import urllib.request
    try:
        req = urllib.request.Request(_BILI_SPI_URL, headers={"User-Agent": DOUYIN_UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = (_json.loads(resp.read().decode()) or {}).get("data") or {}
        b3, b4 = data.get("b_3"), data.get("b_4")
        if not b3 or not b4:
            return {}
        with open(_BILI_BOOTSTRAP_FILE, "w", encoding="utf-8") as fh:
            fh.write("# Netscape HTTP Cookie File\n")
            fh.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\tbuvid3\t{b3}\n")
            fh.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\tbuvid4\t{b4}\n")
        return {"cookiefile": _BILI_BOOTSTRAP_FILE}
    except OSError:
        return {}

PLATFORM_PATTERNS = [
    (r"bilibili\.com|b23\.tv", "Bilibili"),
    (r"youtube\.com|youtu\.be", "YouTube"),
    (r"douyin\.com|iesdouyin\.com", "抖音"),
    (r"xiaohongshu\.com|xhslink\.com", "小红书"),
    (r"tiktok\.com", "TikTok"),
    (r"twitter\.com|x\.com", "X (Twitter)"),
    (r"instagram\.com", "Instagram"),
    (r"kuaishou\.com|gifshow\.com", "快手"),
    (r"channels\.weixin\.qq\.com", "微信视频号"),
    (r"ixigua\.com", "西瓜视频"),
    (r"weibo\.com|weibo\.cn", "微博"),
    (r"vimeo\.com", "Vimeo"),
    (r"twitch\.tv", "Twitch"),
    (r"nicovideo\.jp", "niconico"),
]

MAX_VIDEO_FORMATS = 14
MAX_AUDIO_FORMATS = 6

_STANDARD_HEIGHTS = [4320, 2160, 1440, 1080, 720, 480, 360, 240, 144]


def _quality_tier(height, width):
    """按 YouTube 口径换算清晰度档位：超宽幅视频（如 3840×1920）以 16:9
    等效高度命名（=2160p/4K），而不是真实像素高度 1920。"""
    if not height and not width:
        return None
    effective = max(height or 0, round((width or 0) * 9 / 16))
    return min(_STANDARD_HEIGHTS, key=lambda s: abs(s - effective))

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
                "tier": _quality_tier(height, f.get("width")),
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
    # 小红书 / 快手走专用引擎：直连作品页解析（无需 cookies）
    if is_xhs_url(url):
        return _xhs_fetch_note(url)
    if is_kuaishou_url(url):
        return _ks_parse(url)
    if is_douyin_url(url):
        url = normalize_douyin_url(url)

    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 20,
    }
    if JS_RUNTIMES:
        base_opts["js_runtimes"] = JS_RUNTIMES
    if PROXY:
        base_opts["proxy"] = PROXY

    info, last_exc = None, None
    for client_args in _YT_CLIENT_FALLBACKS:
        opts = dict(base_opts)
        opts.update(_cookie_opts_for(url))
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

    # 小红书 / 快手走专用引擎（视频流 / 图集 zip；直链有时效，任务开始时重新解析）
    if is_xhs_url(url):
        _run_xhs_direct(task, url)
        return
    if is_kuaishou_url(url):
        _run_ks_direct(task, url)
        return
    if is_douyin_url(url):
        url = normalize_douyin_url(url)

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
    if PROXY:
        base_opts["proxy"] = PROXY
    if FFMPEG_AVAILABLE and not audio_only:
        base_opts["merge_output_format"] = "mp4"
    if JS_RUNTIMES:
        base_opts["js_runtimes"] = JS_RUNTIMES

    info, last_exc = None, None
    for client_args in _YT_CLIENT_FALLBACKS:
        if task.get("cancel"):
            break
        opts = dict(base_opts)
        opts.update(_cookie_opts_for(url))
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
