# VideoGrab

<div align="center">

**粘贴链接（或整段分享文案），全平台视频一键下载**

本地运行的网页版视频解析下载器 · 实测覆盖 Bilibili / YouTube / 抖音 / 快手 / 微博 · 液态玻璃 UI · 支持 Docker

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![yt-dlp](https://img.shields.io/badge/yt--dlp-驱动-0A84FF)
![Docker](https://img.shields.io/badge/Docker-实测通过-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-6366F1)

</div>

---

## 功能特性

- **粘贴即下载**：支持纯链接，也支持直接粘贴整段分享文案（如「8.64 复制打开抖音… https://v.douyin.com/xxx/ SQo:/」），自动提取链接
- **风控自愈**：主流站点的签名挑战、验证码风控、412 拦截均有自动化对抗策略（Playwright 会话自举 / 客户端轮换 / 指纹 cookie），日常使用**无需手动配 cookies**
- **格式任选**：按分辨率 / 码率列出全部可选格式，支持「仅音频」；音视频自动合并（ffmpeg）
- **下载体验**：实时进度 + 速度 + 剩余时间，随时取消；HLS 流总大小未知时显示不定进度与已下载量；21:9 宽幅按 YouTube 口径换算档位（3840×1920 → 2160p 4K）
- **液态玻璃 UI**：由 [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) 设计系统驱动，零构建单页应用，键盘可达、响应式、`prefers-reduced-motion` 适配
- **完全本地**：无账号、无上传、无遥测，解析与下载全部在本机完成

## 站点支持与实测状态

> 下表为**真实链接实测结果**（每个 ✅ 都在本机 `downloads/` 目录有对应视频文件），非理论支持。

| 站点 | 实测状态 | 实现方式 |
|---|---|---|
| Bilibili（含 b23.tv 短链） | ✅ 实测下载 71.7 MB | yt-dlp + 官方 `finger/spi` 接口自举 buvid3/buvid4 指纹 cookie，预防 412 风控 |
| YouTube（含 youtu.be 短链） | ✅ 实测下载 100.2 MB（1080p 合并） | yt-dlp + 自动探测 node/deno 解签名挑战；风控时自动轮换 tv / ios / android_vr 客户端 |
| 抖音（含 v.douyin.com 短链、分享文案） | ✅ 实测下载 33.8 MB | Playwright 无头 Chromium 自举匿名会话 cookie（ttwid + s_v_web_id，**无需登录**），yt-dlp 携带后解析下载；缓存 2 小时自动刷新 |
| 快手（含 v.kuaishou.com 短链、分享文案） | ✅ 实测下载 1.5 MB（无水印原画） | 专用引擎：Playwright 打开作品页拦截 `visionVideoDetail` GraphQL——风控 token 必须由页面脚本签发，API 直连（含 TLS 伪装）会被验证码拦截 |
| 微博 | ✅ 实测下载 1.7 MB | yt-dlp 直连 `m.weibo.cn/detail/<id>` 解析 |
| 小红书（含 xhslink.com 短链） | ⚠️ 引擎已实现，需条件 | 专用引擎直连笔记页解析 `__INITIAL_STATE__`（兼容非标准 `undefined` JSON、保留 `xsec_token`），视频笔记直下、图集自动打包 zip；笔记页现要求**带 token 的 App 分享链接**或登录 cookies.txt |
| TikTok / X (Twitter) / Instagram | ⚠️ 需网络条件 | 国内网络无法直连：设置 `VIDEOGRAB_PROXY=http://127.0.0.1:7890` 走代理；X 的媒体多数需登录态，配合 cookies.txt 使用 |
| 其他 yt-dlp 支持的站点（1000+） | 尽力而为 | yt-dlp 通用引擎，欢迎提 issue 附 `GET /api/health` 返回 |

## 快速开始

### 方式一：Windows 一键启动（推荐）

双击 **`启动VideoGrab.bat`**：

- 首次运行自动创建虚拟环境并安装依赖（约 1-2 分钟），随后自动拉起服务并打开浏览器
- 再次运行 3 秒内启动；关闭窗口即停止服务
- 若提示 8100 端口被占用，说明服务已在运行（Docker 版或上次实例），脚本会直接帮你打开页面

### 方式二：手动运行

```bash
pip install -r requirements.txt
playwright install chromium   # 抖音/快手支持需要，一次性下载约 130MB
uvicorn backend.app:app --host 127.0.0.1 --port 8100
# 打开 http://127.0.0.1:8100
```

可选：安装 [ffmpeg](https://ffmpeg.org/download.html) 并加入 PATH，高清音视频自动合并体验更佳。

### 方式三：Docker 部署

```bash
docker compose up -d          # 推荐
# 或
docker build -t videograb . && docker run -d --name videograb -p 8100:8100 -v ./downloads:/app/downloads videograb
```

镜像内已含 ffmpeg、nodejs 与 Playwright Chromium，开箱即用；`./downloads` 挂载到宿主机。构建默认使用国内镜像源（debian→USTC、pypi→阿里、Chromium→npmmirror），海外可用 `--build-arg` 覆盖（见 Dockerfile 注释）。

## Cookies 配置

五大主流站点已内置免 cookie 方案。需要登录态的场景（Instagram、私密笔记、会员视频、X 媒体）按任一方式配置：

1. **一键脚本**：关闭所有 Chrome / Edge 窗口后运行 `python scripts/make_cookies.py edge`（或 chrome），根目录生成 `cookies.txt`（已 gitignore），重启生效
2. **浏览器扩展**：用 "Get cookies.txt LOCALLY" 导出 Netscape 格式，存为根目录 `cookies.txt`
3. **环境变量**：`set VIDEOGRAB_COOKIES_BROWSER=edge` 后启动（浏览器需处于关闭状态）

优先级：`cookies.txt` > `VIDEOGRAB_COOKIES_BROWSER` > 内置自动策略。当前状态见 `GET /api/health` 的 `cookies` 字段。

## 常见问题

- **小红书提示需要 cookies？** 笔记页有登录墙：请从 App 分享功能复制带 `xsec_token` 的链接重试，或配置 cookies.txt
- **TikTok / X 报网络错误？** 国内网络不可直连：`set VIDEOGRAB_PROXY=http://127.0.0.1:7890`（换成你的代理端口）后重启
- **提示 8100 端口被占用？** 已有实例在运行（bat 或 Docker），直接访问 http://127.0.0.1:8100；要切换部署方式先停掉另一个
- **抖音/快手首次解析很慢？** 首次需无头浏览器自举会话（约 10-20 秒），之后缓存内秒解析

## 项目结构

```
videograb/
├── backend/
│   ├── app.py          # FastAPI 入口：解析/下载/任务/文件 API，分享文案提链
│   └── downloader.py   # 站点路由核心：yt-dlp 封装 + 抖音/快手/小红书/B站专用引擎 + cookies/代理策略
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
| 站点路由 | 专用引擎优先（抖音 / 快手 / 小红书），其余走 yt-dlp 通用管线——同类项目（TikTokDownload、XHS-Downloader、KS-Downloader、MediaCrawler 等）的主流架构 |
| 抖音会话自举 | 无头 Chromium 访问抖音生成匿名会话 cookie 并导出，yt-dlp 携带解析；比 API 逆向抗变动，比无 cookie 稳定 |
| 快手 GraphQL 拦截 | 风控 token 必须由页面 JS 签发，仅真实浏览器环境可通过；无头 Chromium 拦截 `visionVideoDetail` 响应取无水印原画直链 |
| 小红书笔记解析 | 直连笔记页 `__INITIAL_STATE__`，兼容非标准 `undefined` JSON，短链重定向保留 `xsec_token` |
| YouTube 对抗 | JS 运行时自动探测（node/deno）+ 播放器客户端轮换（默认 → tv → ios/android_vr） |
| B 站防 412 | 官方指纹接口自举 buvid3/buvid4，缓存 6 小时 |
| 格式归一化 | 按「分辨率×扩展名」去重取最高码率；HLS 未知大小不做假估算 |
| 任务管理 | 线程池并发 + progress_hooks 实时上报 + 钩子内抛错实现取消 + 半成品清理 |
| 安全健壮 | 路径穿越防护、URL/文案校验、报错清洗为可读文案、分享文案提链前后端双实现 |

## 免责声明

本项目仅供个人学习、研究与离线备份使用。请遵守目标站点的服务条款，尊重内容创作者的版权，勿将下载内容用于商业传播。

## 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — 核心解析与下载引擎
- [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) — 前端设计系统检索
- 同类开源项目设计思路参考：[RuiC-VideoGrab](https://github.com/HRuiCcc/RuiC-VideoGrab)、[TikTokDownload](https://github.com/JoeanAmier/TikTokDownload)、[XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader)、[KS-Downloader](https://github.com/JoeanAmier/KS-Downloader)、[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)
