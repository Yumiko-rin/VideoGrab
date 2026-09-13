# VideoGrab

<div align="center">

**粘贴链接（或整段分享文案），全平台视频一键下载**

本地运行的网页版视频解析下载器 · Bilibili / YouTube / 抖音 / 小红书 开箱即用 · 1000+ 站点 · 数据不出本机

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![yt-dlp](https://img.shields.io/badge/yt--dlp-驱动-0A84FF)
![Docker](https://img.shields.io/badge/Docker-支持-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-6366F1)

</div>

---

## 功能特性

- **粘贴即解析**：支持直接粘贴整段分享文案（如「7.64 复制打开抖音… https://v.douyin.com/xxx/」），自动提取链接
- **格式任选**：按分辨率 / 码率列出全部清晰度，支持「仅音频」；HLS 流自动显示不定进度与已下载量
- **实时进度**：百分比、实时速度、剩余时间，随时取消；音视频自动合并（ffmpeg）
- **风控自愈**：各主流站点的验证码 / 412 / 签名挑战均有自动化对抗策略（见下表），无需手动配 cookies 即可覆盖绝大多数场景
- **苹果液态玻璃 UI**：由 [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) 设计系统驱动，暗色 / 浅色玻璃材质、骨架屏、键盘可达、响应式
- **完全本地**：无账号、无上传、无遥测；解析与下载全部在本机完成

## 站点支持

| 站点 | 开箱即用 | 实现方式 |
|---|---|---|
| Bilibili（含 b23.tv） | ✅ | yt-dlp + 官方 `finger/spi` 接口自举 buvid3/buvid4 指纹 cookie，预防 412 风控 |
| YouTube（含 youtu.be） | ✅ | yt-dlp + 自动探测 node/deno 解签名挑战；风控时自动轮换 tv / ios / android_vr 客户端 |
| 抖音（含 v.douyin.com 短链） | ✅ | Playwright 无头 Chromium 自举匿名会话 cookie（ttwid + s_v_web_id，**无需登录**），yt-dlp 携带后解析下载；cookie 缓存 2 小时自动刷新 |
| 小红书（含 xhslink.com） | ✅ 视频笔记 / 图集 | 专用引擎直连笔记页解析 `__INITIAL_STATE__`（兼容非标准 `undefined` JSON、保留 `xsec_token`），图集自动打包 zip |
| TikTok / X (Twitter) / 微博 / 快手 / 西瓜视频 等 | 视站点风控而定 | yt-dlp 通用引擎（支持 1000+ 站点），个别站点被风控时按 [Cookies 配置](#cookies-配置) 处理 |
| 其他任意 yt-dlp 支持的站点 | 尽力而为 | 同上，欢迎提 issue 反馈 |

> 站点风控策略随时会变，遇到新的拦截方式请提 issue，附上 `GET /api/health` 的返回。

## 快速开始

### 方式一：Windows 一键启动（推荐）

双击 **`启动VideoGrab.bat`** 即可——自动创建虚拟环境、安装依赖、拉起服务并打开浏览器。再次使用时双击即秒开。

### 方式二：手动运行

```bash
pip install -r requirements.txt
playwright install chromium   # 抖音支持需要，一次性下载约 130MB
uvicorn backend.app:app --host 127.0.0.1 --port 8100
# 打开 http://127.0.0.1:8100
```

可选：安装 [ffmpeg](https://ffmpeg.org/download.html) 并加入 PATH，高清音视频自动合并体验更佳（Windows 下 bat 启动同样推荐）。

### 方式三：Docker 部署

```bash
# docker compose（推荐）
docker compose up -d

# 或纯 docker
docker build -t videograb .
docker run -d --name videograb -p 8100:8100 -v ./downloads:/app/downloads videograb
```

镜像内已含 ffmpeg、nodejs 与 Playwright Chromium，开箱即用；`./downloads` 挂载到宿主机，下载的文件直接可见。需要登录态站点时追加挂载 cookies：

```yaml
volumes:
  - ./downloads:/app/downloads
  - ./cookies.txt:/app/cookies.txt:ro
```

## Cookies 配置

Bilibili / YouTube / 抖音 / 小红书均已内置免 cookie 方案。**需要登录态**的站点（如 Instagram、私密笔记、会员视频）按任一方式配置：

1. **一键脚本**：关闭所有 Chrome / Edge 窗口后运行
   ```bash
   python scripts/make_cookies.py edge    # 或 chrome / firefox
   ```
   根目录生成 `cookies.txt`（已 gitignore），重启即生效。
2. **浏览器扩展**：用 "Get cookies.txt LOCALLY" 导出 Netscape 格式，存为根目录 `cookies.txt`。
3. **环境变量**：`set VIDEOGRAB_COOKIES_BROWSER=edge` 后启动（浏览器需处于关闭状态）。

优先级：`cookies.txt` > 环境变量 > 内置自动策略。当前状态见 `GET /api/health` 的 `cookies` 字段。

## 项目结构

```
videograb/
├── backend/
│   ├── app.py          # FastAPI 入口：解析/下载/任务/文件 API，分享文案提链
│   └── downloader.py   # 站点路由核心：yt-dlp 封装 + 抖音/小红书/B站专用引擎 + cookies 策略
├── frontend/
│   └── index.html      # 零构建单页应用（液态玻璃设计系统 + 内联 SVG 图标）
├── scripts/
│   └── make_cookies.py # 一键导出浏览器 cookies
├── design-system/
│   └── VideoGrab/MASTER.md   # 视觉规范 Source of Truth
├── Dockerfile / docker-compose.yml / .dockerignore
└── 启动VideoGrab.bat   # Windows 一键启动
```

## 技术要点

| 模块 | 说明 |
|---|---|
| 站点路由 | 专用引擎优先（抖音 / 小红书），其余走 yt-dlp 通用管线——同类项目（TikTokDownload、XHS-Downloader、MediaCrawler 等）的主流架构 |
| 抖音风控自举 | 无头 Chromium 访问抖音生成匿名会话 cookie 并导出，yt-dlp 携带解析；比纯 API 逆向更抗变动，比无 cookie 稳定 |
| YouTube 对抗 | JS 运行时自动探测（node/deno）+ 播放器客户端轮换（默认 → tv → ios/android_vr） |
| 格式归一化 | 按「分辨率×扩展名」去重取最高码率；21:9 宽幅按 YouTube 口径换算档位（3840×1920 → 2160p 4K） |
| 任务管理 | 线程池并发 + progress_hooks 实时上报 + 钩子内抛错实现取消；HLS 总大小未知时显示不定进度 |
| 安全与健壮 | 路径穿越防护、URL/文案校验、yt-dlp 报错清洗为用户可读文案、半成品文件清理 |

## 免责声明

本项目仅供个人学习、研究与离线备份使用。请遵守目标站点的服务条款，尊重内容创作者的版权，勿将下载内容用于商业传播。

## 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — 核心解析与下载引擎
- [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) — 前端设计系统检索
- 同类开源项目的设计思路参考：[RuiC-VideoGrab](https://github.com/HRuiCcc/RuiC-VideoGrab)、[TikTokDownload](https://github.com/JoeanAmier/TikTokDownload)、[XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader)、[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)
