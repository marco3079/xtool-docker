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
      openjdk-21-jdk-headless xz-utils \
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

# --- accord: actool replacement (copied after the toolchain layers so they stay cached)
COPY --from=accord /out/bin/accord /usr/local/bin/accord

# git pushes/pulls authenticate with the GitHub account chosen in the panel
RUN git config --system credential.helper '!gh auth git-credential' \
 && git config --system init.defaultBranch main

COPY panel /opt/panel

LABEL org.opencontainers.image.title="xtool Painel" \
      org.opencontainers.image.version="1.1.0" \
      org.opencontainers.image.authors="marco3079" \
      org.opencontainers.image.source="https://github.com/marco3079/xtool-docker" \
      org.opencontainers.image.description="xtool + painel web para compilar, instalar e publicar apps iOS (App Store) e Android (Google Play) sem Mac"

WORKDIR /work
EXPOSE 8080
CMD ["python3", "-u", "/opt/panel/server.py"]
