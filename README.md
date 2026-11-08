# xtool no Docker + painel web

Ambiente Docker com [xtool](https://github.com/xtool-org/xtool) **1.24.0** (a alternativa ao Xcode que roda fora do Mac) e Swift **6.4.2**, mais um painel web para gerenciar tudo pelo navegador.

## Subir

```bash
docker compose up -d --build
```

Depois abra **http://localhost:8080**.

## O que o painel faz

| Seção | Funções |
|---|---|
| **Painel** | Mostra a versão do xtool e do Swift, o login Apple, o SDK do iOS, o espaço em disco e o USB |
| **Configuração** | `xtool setup`; login, status e logout da conta Apple; instalar, atualizar, gerar e remover o SDK a partir do `Xcode.xip` |
| **Projetos** | `xtool new`; build (debug/release); gerar `.ipa` assinado; rodar no iPhone; gerar projeto Xcode; baixar os builds |
| **Dispositivos** | Listar aparelhos (USB/rede); instalar `.ipa` (com upload por arrastar); abrir e desinstalar apps |
| **Developer Services** | `xtool ds` para times, certificados, bundle IDs, dispositivos, perfis e anisette |
| **Arquivos** | Navegar em `/work` e nos Downloads do Windows; enviar, baixar e apagar arquivos |
| **Terminal** | Qualquer comando ou um shell bash interativo |
| **Tarefas** | Histórico dos comandos, com a saída de cada um |

Todo comando roda num terminal real (PTY). As perguntas interativas, como modo de login, Apple ID, código 2FA e caminho do Xcode.xip, são respondidas digitando no console da parte de baixo da tela.

## Primeira configuração

1. Baixe o **Xcode 27.1** (`.xip`) em <https://developer.apple.com/download/all/?q=Xcode> e salve na pasta **Downloads** do Windows.
2. No painel, vá em **Configuração → Iniciar setup**, escolha o modo de login e, quando ele pedir o caminho, informe `/downloads/Xcode_27.1.xip`.

## Volumes

- `xtool-home` → `/root`: guarda o login Apple e o SDK do iOS
- `xtool-work` → `/work`: guarda os projetos
- `~/Downloads` → `/downloads`: o `.xip` e os `.ipa` do Windows

## USB no Windows

O Docker Desktop não repassa USB para o container. Para instalar no iPhone, passe o aparelho para o WSL com [usbipd](https://learn.microsoft.com/windows/wsl/connect-usb) ou use conexão pela rede.

## Atualizar o xtool

Troque `XTOOL_VERSION` no `Dockerfile` e rode `docker compose up -d --build`.

## Segurança

O painel não tem senha e executa comandos no container. Por isso ele só escuta em `127.0.0.1`. Não exponha a porta na rede.
