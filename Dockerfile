# VideoGrab 后端镜像：ffmpeg（音视频合并）+ nodejs（YouTube 签名挑战）
# + Playwright Chromium（抖音会话自举）
#
# 国内网络默认使用镜像源加速构建；海外用户可覆盖：
#   docker build --build-arg DEBIAN_MIRROR=deb.debian.org \
#                --build-arg PIP_INDEX=https://pypi.org/simple \
#                --build-arg PLAYWRIGHT_DL=https://cdn.playwright.dev .
FROM python:3.12-slim

ARG DEBIAN_MIRROR=mirrors.ustc.edu.cn
ARG PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/
ARG PLAYWRIGHT_DL=https://cdn.npmmirror.com/binaries/playwright

# debian 软件源 + pip 镜像 + Playwright 二进制下载源
RUN sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && pip config set global.index-url "${PIP_INDEX}"

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg nodejs ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
ENV PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DL}
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY backend ./backend
COPY frontend ./frontend

RUN mkdir -p downloads
VOLUME ["/app/downloads"]

EXPOSE 8100

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8100"]
