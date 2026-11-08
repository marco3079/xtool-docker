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
| **Configuração** | `xtool setup`; instalar, atualizar, gerar e remover o SDK a partir do `Xcode.xip` |
| **Contas Apple** | Cadastra **várias contas Apple**; cada uma guarda o próprio login e dá para trocar a conta em uso com um clique (também pelo seletor no topo); login, status, logout, renomear e remover |
| **Projetos** | `xtool new`; build (debug/release); gerar `.ipa` assinado; rodar no aparelho escolhido; gerar projeto Xcode; baixar os builds |
| **Dispositivos** | Cadastra **vários aparelhos** (detecta e salva com um clique, ou cadastro manual com nome e UDID) e marca um como padrão; instalar `.ipa` (com upload por arrastar); abrir e desinstalar apps |
| **Developer Services** | `xtool ds` para times, certificados, bundle IDs, dispositivos, perfis e anisette |
| **Arquivos** | Navegar em `/work` e nos Downloads do Windows; enviar, baixar e apagar arquivos |
| **Terminal** | Qualquer comando ou um shell bash interativo |
| **Tarefas** | Histórico dos comandos, com a saída de cada um |

Todo comando roda num terminal real (PTY). As perguntas interativas, como modo de login, Apple ID, código 2FA e caminho do Xcode.xip, são respondidas digitando no console da parte de baixo da tela.

## Primeira configuração

1. Baixe o **Xcode 27.1** (`.xip`) em <https://developer.apple.com/download/all/?q=Xcode> e salve na pasta **Downloads** do Windows.
2. No painel, vá em **Configuração → Iniciar setup**, escolha o modo de login e, quando ele pedir o caminho, informe `/downloads/Xcode_27.1.xip`.

## Volumes

- `xtool-home` → `/root`: guarda os logins Apple (`.config/xtool-panel/accounts/<id>`), os aparelhos cadastrados e o SDK do iOS
- `xtool-work` → `/work`: guarda os projetos
- `~/Downloads` → `/downloads`: o `.xip` e os `.ipa` do Windows

## Conectar o iPhone (cabo ou Wi-Fi, sem usbipd)

O container fala com o iPhone através do serviço da Apple que roda no Windows, pela variável `USBMUXD_SOCKET_ADDRESS=host.docker.internal:27015` no compose.

1. Instale o **iTunes** ou o **Dispositivos Apple** pela Microsoft Store e **deixe aberto**. O serviço só fica ativo assim.
2. Conecte o iPhone com o cabo uma vez e toque em **Confiar**.
3. Para usar só por Wi-Fi: no iTunes, abra o iPhone e marque **"Sincronizar com este iPhone via Wi-Fi"**. Depois disso o cabo pode sair, desde que o iPhone e o PC estejam na mesma rede.
4. No iPhone, ative **Ajustes → Privacidade e Segurança → Modo de Desenvolvedor**.
5. No painel, use **Dispositivos → Listar dispositivos**.

## Atualizar o xtool

Troque `XTOOL_VERSION` no `Dockerfile` e rode `docker compose up -d --build`.

## Segurança

O painel não tem senha e executa comandos no container. Por isso ele só escuta em `127.0.0.1`. Não exponha a porta na rede.
