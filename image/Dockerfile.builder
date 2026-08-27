FROM debian:trixie-slim

ARG RPI_IMAGE_GEN_VERSION=v2.6.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && git clone --branch "$RPI_IMAGE_GEN_VERSION" --depth 1 \
        https://github.com/raspberrypi/rpi-image-gen.git /opt/rpi-image-gen \
    && cd /opt/rpi-image-gen \
    && ./install_deps.sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/rpi-image-gen
