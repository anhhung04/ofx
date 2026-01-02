FROM ubuntu:22.04

RUN apt-get update && \
    apt-get install -y nasm binutils xxd && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY compile.sh /compile.sh
RUN chmod +x /compile.sh

ENTRYPOINT ["/compile.sh"]
