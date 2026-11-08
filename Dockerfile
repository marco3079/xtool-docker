# xtool (cross-platform Xcode replacement) + web management panel

# --- accord: actool replacement that compiles Assets.car on Linux (no prebuilt binaries)
FROM rust:1.91-bookworm AS accord
ARG ACCORD_VERSION=v2.3.0
RUN cargo install --locked --git https://github.com/MiloLug/dine-accord --tag ${ACCORD_VERSION} --root /out \
 || cargo install --git https://github.com/MiloLug/dine-accord --tag ${ACCORD_VERSION} --root /out

FROM swift:6.4.2

# Pinned versions (change to upgrade)
ARG XTOOL_VERSION=1.24.0
ARG RCODESIGN_VERSION=0.29.0

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl ca-certificates python3 python3-jwt python3-cryptography \
      usbmuxd libimobiledevice-utils git gh openssl zip unzip \
 && rm -rf /var/lib/apt/lists/*

# AppImages need FUSE, which containers don't have: extract it instead.
RUN cd /opt \
 && curl -fL "https://github.com/xtool-org/xtool/releases/download/${XTOOL_VERSION}/xtool-$(uname -m).AppImage" -o xtool.AppImage \
 && chmod +x xtool.AppImage \
 && ./xtool.AppImage --appimage-extract >/dev/null \
 && mv squashfs-root xtool \
 && rm xtool.AppImage \
 && ln -s /opt/xtool/AppRun /usr/local/bin/xtool

# rcodesign: signs .app bundles for App Store distribution on Linux
RUN curl -fL "https://github.com/indygreg/apple-platform-rs/releases/download/apple-codesign%2F${RCODESIGN_VERSION}/apple-codesign-${RCODESIGN_VERSION}-$(uname -m)-unknown-linux-musl.tar.gz" \
      | tar xz -C /tmp \
 && mv /tmp/apple-codesign-*/rcodesign /usr/local/bin/ \
 && rm -rf /tmp/apple-codesign-*

COPY --from=accord /out/bin/accord /usr/local/bin/accord

# git pushes/pulls authenticate with the GitHub account chosen in the panel
RUN git config --system credential.helper '!gh auth git-credential' \
 && git config --system init.defaultBranch main

COPY panel /opt/panel

LABEL org.opencontainers.image.title="xtool Painel" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.authors="marco3079" \
      org.opencontainers.image.source="https://github.com/marco3079/xtool-docker" \
      org.opencontainers.image.description="xtool + painel web para compilar, instalar e publicar apps iOS sem Mac"

WORKDIR /work
EXPOSE 8080
CMD ["python3", "-u", "/opt/panel/server.py"]
