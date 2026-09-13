"""一次性生成 cookies.txt，解锁需要浏览器 cookies 的站点（抖音等）。

用法（先关闭所有 Chrome / Edge 窗口，否则数据库被锁无法读取）：
    python scripts/make_cookies.py edge     # 或 chrome / firefox

成功后项目根目录会生成 cookies.txt，VideoGrab 自动识别，无需其他配置。
说明：抖音只需要匿名 cookies（浏览器打开过抖音即可），不需要登录账号。
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from yt_dlp import YoutubeDL  # noqa: E402


def main() -> None:
    browser = sys.argv[1] if len(sys.argv) > 1 else "edge"
    out = os.path.join(PROJECT_ROOT, "cookies.txt")
    print(f"正在从 {browser} 读取 cookies（浏览器需处于关闭状态）...")
    with YoutubeDL({"cookiesfrombrowser": (browser,), "cookiefile": out}) as ydl:
        ydl.cookiejar.save()
    print(f"已生成 {out}，重启 VideoGrab 后生效。")


if __name__ == "__main__":
    main()
