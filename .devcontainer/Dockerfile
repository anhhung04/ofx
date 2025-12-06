FROM --platform=linux/amd64 mcr.microsoft.com/devcontainers/python:3.14

ENV UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    llvm \
    llvm-dev \
    clang \
    libclang-dev \
    zlib1g-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV CODON_DIR=/opt/codon
ENV PATH="${CODON_DIR}/bin:${PATH}"
ENV CODON_PYTHON=/usr/local/bin/python

RUN mkdir -p $CODON_DIR \
    && cd /tmp \
    && wget -q https://github.com/exaloop/codon/releases/download/v0.16.3/codon-linux-x86_64.tar.gz \
    && tar -xzf codon-linux-x86_64.tar.gz -C $CODON_DIR --strip-components=1 \
    && rm codon-linux-x86_64.tar.gz \
    && chmod +x $CODON_DIR/bin/codon

ENV PYTHONPATH=/workspace/ofx/src:${PYTHONPATH}
