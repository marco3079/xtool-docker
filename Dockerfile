# xtool (cross-platform Xcode replacement) + web management panel (iOS, Android e PC/Steam)

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
      openjdk-21-jdk-headless xz-utils \
 && rm -rf /var/lib/apt/lists/*

# Base xtool comes from the repository (base/xtool-<version>-<arch>.zip), so building and
# starting don't depend on github.com/xtool-org. Newer versions installed from the panel
# go to the volume and take precedence; this one stays as the fallback.
# AppImages need FUSE, which containers don't have: extract it instead.
COPY base/xtool-${XTOOL_VERSION}-x86_64.zip /tmp/xtool.zip
RUN cd /opt \
 && [ "$(uname -m)" = x86_64 ] || { echo "base/ só tem o xtool x86_64"; exit 1; } \
 && unzip -q /tmp/xtool.zip -d /tmp/xtool-zip \
 && mv /tmp/xtool-zip/xtool-${XTOOL_VERSION}-x86_64.AppImage xtool.AppImage \
 && rm -rf /tmp/xtool.zip /tmp/xtool-zip \
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

# Node.js 22 (official binary) for Capacitor/npm projects
ARG NODE_VERSION=22.21.1
RUN case "$(uname -m)" in x86_64) ARCH=x64 ;; aarch64) ARCH=arm64 ;; *) echo "unsupported architecture" >&2; exit 1 ;; esac \
 && curl -fL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${ARCH}.tar.xz" \
      | tar -xJ --strip-components=1 -C /usr/local \
 && node --version

# Android SDK: command-line tools, platform and build-tools for Gradle builds
ARG ANDROID_CMDLINE_TOOLS=13114758
ARG ANDROID_PLATFORM=android-36
ARG ANDROID_BUILD_TOOLS=36.0.0
ENV ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk
RUN curl -fL "https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_CMDLINE_TOOLS}_latest.zip" -o /tmp/cmdline-tools.zip \
 && mkdir -p /opt/android-sdk/cmdline-tools \
 && unzip -q /tmp/cmdline-tools.zip -d /opt/android-sdk/cmdline-tools \
 && mv /opt/android-sdk/cmdline-tools/cmdline-tools /opt/android-sdk/cmdline-tools/latest \
 && rm /tmp/cmdline-tools.zip \
 && yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses >/dev/null \
 && /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --install "platform-tools" "platforms;${ANDROID_PLATFORM}" "build-tools;${ANDROID_BUILD_TOOLS}"
ENV PATH=$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/build-tools/36.0.0

# steamcmd: envia builds para a Steam (SteamPipe). Precisa das bibliotecas de 32 bits.
RUN apt-get update \
 && apt-get install -y --no-install-recommends lib32gcc-s1 lib32stdc++6 \
 && rm -rf /var/lib/apt/lists/*
# O steamcmd.sh calcula a própria pasta a partir de $0, então um symlink quebraria o
# programa: por isso um wrapper em /usr/local/bin em vez de link simbólico.
# O `+quit` inicial já baixa as atualizações do steamcmd para dentro da imagem.
# `|| true` porque essa atualização inicial pode sair com código != 0 sem ser fatal.
ARG STEAMCMD_URL=https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz
RUN mkdir -p /opt/steamcmd \
 && curl -fL "${STEAMCMD_URL}" | tar xz -C /opt/steamcmd \
 && (/opt/steamcmd/steamcmd.sh +quit || true) \
 && printf '#!/bin/sh\nexec /opt/steamcmd/steamcmd.sh "$@"\n' > /usr/local/bin/steamcmd \
 && chmod +x /usr/local/bin/steamcmd

# ImageMagick: converte PNG em .ico para o ícone do .exe. Sempre instalado (é pequeno).
RUN apt-get update \
 && apt-get install -y --no-install-recommends imagemagick \
 && rm -rf /var/lib/apt/lists/*

# Wine: só entra com `--build-arg INSTALL_WINE=1` (padrão 0). Serve para aplicar ícone e
# metadados dentro do .exe do Windows, porque o @electron/packager usa o rcedit, que roda sob
# Wine quando o build é em Linux. Custa cerca de +3,9 GB na imagem. Sem ele, o .exe sai sem
# ícone nem metadados (o resto do painel funciona igual).
ARG INSTALL_WINE=0
# Estas variáveis ficam sempre definidas; sem o Wine instalado não fazem nada.
ENV WINEPREFIX=/opt/wineprefix \
    WINEARCH=win64 \
    WINEDEBUG=-all
# Com o Wine: instala wine64 (só 64 bits, sem i386) e o Xvfb, que dá um display virtual para o
# Wine iniciar sem tela (headless). O prefixo é inicializado no build, para o primeiro uso não
# demorar nem imprimir ruído. WINEDLLOVERRIDES desliga o instalador de wine-mono/gecko no init,
# que travaria sem tela.
RUN if [ "$INSTALL_WINE" = "1" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends wine64 wine xvfb \
      && rm -rf /var/lib/apt/lists/* \
      && xvfb-run -a env WINEDLLOVERRIDES="mscoree,mshtml=" wineboot --init; \
    fi

# --- accord: actool replacement (copied after the toolchain layers so they stay cached)
COPY --from=accord /out/bin/accord /usr/local/bin/accord

# git pushes/pulls authenticate with the GitHub account chosen in the panel
RUN git config --system credential.helper '!gh auth git-credential' \
 && git config --system init.defaultBranch main

COPY panel /opt/panel

LABEL org.opencontainers.image.title="xtool Painel" \
      org.opencontainers.image.version="1.2.0" \
      org.opencontainers.image.authors="marco3079" \
      org.opencontainers.image.source="https://github.com/marco3079/xtool-docker" \
      org.opencontainers.image.description="xtool + painel web para compilar, instalar e publicar apps iOS (App Store), Android (Google Play) e PC (Steam) sem Mac"

WORKDIR /work
EXPOSE 8080
CMD ["python3", "-u", "/opt/panel/server.py"]
