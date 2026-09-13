# VideoGrab

<div align="center">

**粘贴链接，全平台视频一键下载**

基于 yt-dlp 的本地视频解析下载器 · 支持 1000+ 站点 · 数据不出本机

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![yt-dlp](https://img.shields.io/badge/yt--dlp-驱动-0A84FF)
![License](https://img.shields.io/badge/License-MIT-6366F1)
[![Live Demo](https://img.shields.io/badge/在线演示-GitHub_Pages-0A84FF?logo=githubpages)](https://yumiko-rin.github.io/VideoGrab/)
[![Deploy Pages](https://github.com/Yumiko-rin/VideoGrab/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/Yumiko-rin/VideoGrab/actions/workflows/deploy-pages.yml)

</div>

---

## 功能特性

- **一键解析**：粘贴 Bilibili / YouTube / 抖音 / TikTok / X 等站点链接，自动提取标题、封面、UP主与全部可选格式
- **格式任选**：按分辨率 / 码率列出全部清晰度，支持「仅音频」模式；自动探测 ffmpeg，无 ffmpeg 时优雅降级为单流下载
- **实时进度**：百分比、实时速度、剩余时间，随时可取消（yt-dlp progress_hooks 驱动）
- **下载管理**：任务队列并发控制、断点续传（yt-dlp 内建）、历史文件列表一键打开
- **完全本地**：无账号、无上传、无遥测，解析与下载全部在本机完成
- **设计系统驱动**：UI 按 [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) 检索生成的苹果液态玻璃（Liquid Glass）设计系统实现，规范见 [design-system/VideoGrab/MASTER.md](design-system/VideoGrab/MASTER.md)

## 快速开始

```bash
# 1. 安装依赖（建议使用虚拟环境）
pip install -r requirements.txt

# 2. 启动服务
uvicorn backend.app:app --host 127.0.0.1 --port 8100

# 3. 打开浏览器
# http://127.0.0.1:8100
```

可选：安装 [ffmpeg](https://ffmpeg.org/download.html) 并加入 PATH，即可解锁 1080p+ 音视频自动合并（Bilibili / YouTube 高清源为分离流，必需）。

## 在线演示（GitHub Pages）

[https://yumiko-rin.github.io/VideoGrab/](https://yumiko-rin.github.io/VideoGrab/) —— 由 GitHub Actions 在每次 push 到 `main` 时自动发布。

演示站只包含液态玻璃 UI 壳：可以预览交互与视觉，但**不含解析后端**（页面会自动进入演示模式并提示）。解析与下载必须在本机运行后端，原因有三：

1. GitHub Pages 仅支持静态托管，无法运行 FastAPI / yt-dlp；
2. GitHub 服务条款禁止把 Actions 当作常驻网络服务使用；
3. 云端数据中心 IP 会稳定触发 YouTube / Bilibili 的机器人风控（本工具的客户端轮换策略只对家宽 IP 有效）。

想要"随时随地访问"的真·部署：在本机运行后 `cloudflared tunnel --url http://127.0.0.1:8100`（内网穿透），或自行容器化部署到 PaaS——后者需要自备 cookies 且注意平台服务条款。

## 项目结构

```
videograb/
├── backend/
│   ├── app.py          # FastAPI 入口：/api/parse、/api/downloads、/api/tasks、/api/files
│   └── downloader.py   # yt-dlp 封装：格式归一化、任务线程池、进度钩子、取消机制
├── frontend/
│   └── index.html      # 零构建单页应用（设计系统 token + 内联 SVG 图标）
├── design-system/
│   └── VideoGrab/MASTER.md   # 视觉规范 Source of Truth（色板/字体/动效/UX 硬规则）
├── downloads/          # 下载产物（自动创建，已 gitignore）
└── requirements.txt
```

## 技术要点

| 模块 | 说明 |
|---|---|
| 格式归一化 | 将 yt-dlp 原始 format 列表按「分辨率×扩展名」去重，保留最高码率，视频/音频分档 |
| 任务管理 | `ThreadPoolExecutor` 并发下载，progress_hooks 实时上报，取消 = 钩子内抛出 `DownloadError` |
| 优雅降级 | 启动时探测 ffmpeg：有 → `format+bestaudio` 自动合并 mp4；无 → 锁定渐进式单流格式并提示 |
| 安全 | 下载路径穿越防护、URL 校验、错误信息清洗（Unsupported URL / 需登录 / 视频不可用 → 用户可读文案） |
| YouTube 兼容 | 自动探测 node/deno JS 运行时解签名挑战；遇机器人验证自动轮换 tv / ios / android_vr 客户端重试；HLS 流总大小未知时显示不定进度与已下载量 |
| 前端 | 零依赖单文件 SPA：内联校验（blur 触发 + aria-describedby）、骨架屏、`prefers-reduced-motion` 适配 |

## Roadmap

- [ ] 批量解析（播放列表 / 收藏夹）
- [ ] SOCKS 代理配置
- [ ] 下载完成后系统通知
- [ ] 多语言（EN）

## 免责声明

本项目仅供个人学习、研究与离线备份使用。请遵守目标站点的服务条款，尊重内容创作者的版权，勿将下载内容用于商业传播。

## 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — 核心解析与下载引擎
- [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) — 前端设计系统检索
