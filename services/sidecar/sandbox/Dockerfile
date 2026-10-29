# 由用户预构建；Agent 执行时不联网拉取镜像或安装依赖。
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends bash coreutils git ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace /home/agent
USER 65532:65532
WORKDIR /workspace
