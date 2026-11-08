# xtool (cross-platform Xcode replacement) + web management panel
FROM swift:6.4.2

# Pinned xtool release (change to upgrade)
ARG XTOOL_VERSION=1.24.0

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl ca-certificates python3 usbmuxd libimobiledevice-utils \
 && rm -rf /var/lib/apt/lists/*

# AppImages need FUSE, which containers don't have: extract it instead.
RUN cd /opt \
 && curl -fL "https://github.com/xtool-org/xtool/releases/download/${XTOOL_VERSION}/xtool-$(uname -m).AppImage" -o xtool.AppImage \
 && chmod +x xtool.AppImage \
 && ./xtool.AppImage --appimage-extract >/dev/null \
 && mv squashfs-root xtool \
 && rm xtool.AppImage \
 && ln -s /opt/xtool/AppRun /usr/local/bin/xtool

COPY panel /opt/panel

WORKDIR /work
EXPOSE 8080
CMD ["python3", "-u", "/opt/panel/server.py"]
