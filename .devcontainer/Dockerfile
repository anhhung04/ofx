FROM  ubuntu:22.04

RUN apt update && apt upgrade -y

RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    llvm \
    llvm-dev \
    clang \
    libclang-dev \
    zlib1g-dev \
    python3-dev \
    graphviz

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PYTHONPATH=/workspace/ofx/src:${PYTHONPATH}
