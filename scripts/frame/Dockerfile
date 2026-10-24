# arm64 builder image for the Steam Frame release (see scripts/build_frame.sh).
# build_release.bat builds and runs it with --platform linux/arm64; on an x86
# host Docker Desktop runs it under QEMU, on an arm64 host it runs natively.
FROM ubuntu:24.04

# Python itself is installed by build_frame.sh (scripts/frame/install_python.sh)
# into the cached build volume, so it is shared with the CI path.
ENV DEBIAN_FRONTEND=noninteractive

COPY apt-packages.txt /tmp/apt-packages.txt
RUN apt-get update -qq \
    && tr -d '\r' < /tmp/apt-packages.txt | grep -vE '^\s*(#|$)' | xargs apt-get install -y -qq --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
