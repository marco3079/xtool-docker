<div align="center">

<img src="panel/static/logo.svg" width="112" alt="xtool Painel">

# xtool Painel

**Desenvolva, instale e publique apps iOS sem Mac, direto pelo navegador.**

[![Versão](https://img.shields.io/badge/versão-1.0.0-4f8cff?style=flat-square)](#changelog)
[![xtool](https://img.shields.io/badge/xtool-1.24.0-7c5cff?style=flat-square)](https://github.com/xtool-org/xtool)
[![Swift](https://img.shields.io/badge/Swift-6.4.2-F05138?style=flat-square&logo=swift&logoColor=white)](https://swift.org)
[![Docker](https://img.shields.io/badge/Docker-pronto-2496ED?style=flat-square&logo=docker&logoColor=white)](#instalação)
[![Plataforma](https://img.shields.io/badge/host-Windows%20%7C%20Linux-555?style=flat-square)](#requisitos)

By **[marco3079](https://github.com/marco3079)**

</div>

---

## Sumário

- [Visão geral](#visão-geral)
- [Recursos](#recursos)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Primeiros passos](#primeiros-passos)
- [Conectar o iPhone](#conectar-o-iphone)
- [Publicar na App Store](#publicar-na-app-store)
- [IA para notas de versão](#ia-para-notas-de-versão)
- [GitHub](#github)
- [Arquitetura](#arquitetura)
- [Dados e volumes](#dados-e-volumes)
- [Segurança](#segurança)
- [Limitações conhecidas](#limitações-conhecidas)
- [Solução de problemas](#solução-de-problemas)
- [Atualização](#atualização)
- [Changelog](#changelog)
- [Créditos](#créditos)

## Visão geral

O **xtool Painel** coloca o [xtool](https://github.com/xtool-org/xtool) (uma alternativa ao Xcode que roda em qualquer sistema) dentro de um container Docker e adiciona um painel web completo. No navegador você gerencia todo o ciclo de um app iOS: contas Apple, aparelhos, projetos, repositórios do GitHub, compilação, assinatura, envio ao App Store Connect e publicação. O texto "O que há de novo" de cada versão pode ser escrito por IA.

```
http://localhost:8080
```

## Recursos

| Área | O que faz |
|---|---|
| **Painel** | Mostra num relance as versões do xtool e do Swift, a conta Apple em uso, o SDK do iOS, o espaço em disco e a conexão com o iPhone. Avisa quando sai uma versão nova do xtool e atualiza com um clique |
| **Contas Apple** | Cadastra várias contas Apple, cada uma com o próprio login, e troca a conta em uso com um clique |
| **Apps da conta** | Registro de todos os apps de todas as contas (com a conta dona e se ela tem API da Apple), apps do App Store Connect com o estado de cada versão, bundle IDs com ícone e prévia da página da App Store em um iPhone |
| **Projetos** | Cria apps SwiftUI; compila em debug ou release; gera `.ipa`; roda no iPhone; gera projeto Xcode |
| **Publicar** | Compila em release, gera o ícone (`Assets.car`), assina para distribuição, envia ao App Store Connect, preenche "O que há de novo" e submete para revisão |
| **GitHub** | Várias contas; lista os repositórios (inclusive de organizações); importa como projeto; vincula ou cria repositório; pull e push |
| **IA** | OpenAI, Anthropic, Google Gemini, Mistral, Groq, DeepSeek, xAI, OpenRouter, Together, Ollama e LM Studio (locais) ou qualquer API compatível com OpenAI |
| **Dispositivos** | Cadastra vários aparelhos com status em tempo real (cabo, Wi-Fi ou desconectado); instala, abre e remove apps |
| **Configuração** | `xtool setup` e gerenciamento do SDK do iOS a partir do `Xcode.xip` |
| **Arquivos** | Navega em `/work` e nos Downloads do Windows; envia, baixa e apaga arquivos |
| **Terminal** | Shell interativo dentro do container |
| **Tarefas** | Histórico de todos os comandos, com a saída completa |

Todo comando roda num terminal real (PTY). As perguntas interativas, como o código 2FA, a senha ou o caminho do Xcode.xip, são respondidas pelo console do próprio painel.

## Requisitos

| Item | Observação |
|---|---|
| Docker Desktop (Windows) ou Docker Engine (Linux) | Com o Compose v2 |
| ~15 GB livres | Imagem, SDK do iOS e builds |
| Xcode 27.x (`.xip`) | Baixe em [developer.apple.com/download](https://developer.apple.com/download/all/?q=Xcode) |
| Apple ID | Qualquer conta serve para instalar no próprio iPhone |
| Apple Developer Program | **Necessário para publicar na App Store**, junto com uma chave da API do App Store Connect |
| iTunes ou Dispositivos Apple (Windows) | Faz a ponte com o iPhone por cabo ou Wi-Fi |

## Instalação

```bash
git clone https://github.com/marco3079/xtool-docker.git
cd xtool-docker
docker compose up -d --build
```

Depois abra **http://localhost:8080**. O primeiro build demora alguns minutos, porque compila o `accord` a partir do código-fonte.

## Primeiros passos

1. **SDK do iOS:** coloque o `Xcode_27.x.xip` na pasta Downloads. No painel, vá em **Configuração → Instalar SDK**.
2. **Conta Apple:** em **Contas Apple → Nova conta**, entre com o Apple ID. O código 2FA é pedido no console.
3. **Projeto:** em **Projetos → Novo projeto**, ou importe um repositório em **GitHub → Importar como projeto**.
4. **Rodar no iPhone:** com o iPhone conectado, clique em **▶ Rodar no iPhone**.

## Conectar o iPhone

O container usa o serviço da Apple que roda no Windows, por meio de `USBMUXD_SOCKET_ADDRESS=host.docker.internal:27015`, então não precisa de usbipd.

1. Deixe o **iTunes** ou o **Dispositivos Apple** aberto.
2. Conecte o iPhone pelo cabo uma vez e toque em **Confiar**.
3. Para usar sem fio: no iTunes, marque **Sincronizar com este iPhone via Wi-Fi**.
4. No iPhone, ative **Ajustes → Privacidade e Segurança → Modo de Desenvolvedor**.

O status de cada aparelho aparece em **Dispositivos** e se atualiza a cada 5 segundos.

## Publicar na App Store

### Pré-requisitos (uma vez por conta)

1. Crie uma **chave de equipe** em [App Store Connect → Usuários e Acesso → Integrações](https://appstoreconnect.apple.com/access/integrations/api) com a função **App Manager** (ou Admin) e baixe o `.p8`.
2. No painel, vá em **Contas Apple**, clique em **🔑 Cadastrar API da Apple** no cartão da conta, informe o **Issuer ID**, o **Key ID** e o arquivo `.p8`, e clique em **Testar**. Cada conta tem a sua chave.
3. Crie o registro do app em **App Store Connect → Apps → +**, com o mesmo bundle ID do `xtool.yml`.
4. Para a primeira versão, preencha no site da Apple as capturas de tela, a descrição, a classificação etária e a privacidade. A API não cuida dessa parte.

### Fluxo

Na seção **Publicar**: escolha o projeto, confira a versão (o build é automático), gere ou escreva o "O que há de novo" e clique em **🚀 Iniciar**.

| Etapa | O que acontece |
|---|---|
| 1 | Localiza o app no App Store Connect e calcula o próximo número de build |
| 2 | `xtool dev build -c release` |
| 3 | Grava no `Info.plist` a versão e os dados do Xcode (`DTXcode`, `DTSDKName`…) e compila os ícones em `Assets.car` com o [accord](https://github.com/MiloLug/dine-accord) |
| 4 | Cria ou reaproveita o certificado **Apple Distribution** e o perfil **App Store**, depois assina com o [rcodesign](https://github.com/indygreg/apple-platform-rs) |
| 5 | Envia o `.ipa` pela API oficial `buildUploads` e espera a validação da Apple |
| 6 | Espera o processamento, cria ou atualiza a versão, grava "O que há de novo", vincula o build e, se marcado, envia para revisão |

Cada etapa pode ser desligada. Por exemplo, dá para só gerar o `.ipa` assinado ou só enviar para o TestFlight.

## IA para notas de versão

Em **IA**, configure um ou mais provedores e marque um como padrão (★). Ao publicar, o painel junta os commits feitos desde a última publicação e pede à IA um texto curto, voltado ao usuário final, em cada idioma escolhido. O texto sempre pode ser revisado antes de enviar.

| Provedor | Tipo | URL padrão |
|---|---|---|
| OpenAI · Gemini · Mistral · Groq · DeepSeek · xAI · OpenRouter · Together | Nuvem (compatível com OpenAI) | Preenchida automaticamente |
| Anthropic (Claude) | Nuvem (API própria) | `https://api.anthropic.com/v1` |
| Ollama | Local | `http://host.docker.internal:11434/v1` |
| LM Studio | Local | `http://host.docker.internal:1234/v1` |
| Outro | Qualquer API compatível com OpenAI | Você informa |

O botão **Listar** busca os modelos disponíveis direto na API do provedor.

## GitHub

- **Várias contas:** entre pelo navegador (código de dispositivo) ou com um token.
- **Importar:** clona um repositório como novo projeto em `/work`.
- **Vincular:** liga um projeto existente a um repositório e cria o repositório como privado se ele não existir.
- **Pull / Push:** pelo card do projeto, com o autor da conta escolhida.

## Arquitetura

```
┌───────────────────────── Navegador ─────────────────────────┐
│  painel (HTML + xterm.js)  ⇄  HTTP/JSON  ⇄  console PTY      │
└──────────────────────────────┬──────────────────────────────┘
                               │ 127.0.0.1:8080
┌──────────────── Container (swift:6.4.2) ─────────────────────┐
│ server.py   jobs PTY · contas · aparelhos · rotas             │
│ release.py  build → Info.plist → accord → rcodesign → upload  │
│ asc.py      App Store Connect API (JWT ES256)                 │
│ github.py   gh CLI (várias contas)   ai.py  provedores de IA  │
│ xtool · accord · rcodesign · gh · git · libimobiledevice      │
└──────┬─────────────────────────────┬─────────────────────────┘
       │ host.docker.internal:27015  │ HTTPS
   Serviço Apple do Windows    Apple · GitHub · IA
   (iTunes) ⇄ iPhone
```

| Arquivo | Função |
|---|---|
| `Dockerfile` | Imagem com xtool, accord (compilado a partir do código), rcodesign, gh e Python |
| `docker-compose.yml` | Porta, volumes e acesso ao serviço da Apple |
| `panel/server.py` | Servidor HTTP, tarefas em PTY, contas, aparelhos e rotas |
| `panel/release.py` | Pipeline de publicação, executado como tarefa |
| `panel/asc.py` | Cliente da API do App Store Connect |
| `panel/github.py` | Contas e repositórios do GitHub |
| `panel/ai.py` | Provedores de IA e geração do "O que há de novo" |
| `panel/store.py` | Configurações e segredos salvos |
| `panel/static/` | Interface (`index.html`) e logo |

## Dados e volumes

| Volume | Caminho | Conteúdo |
|---|---|---|
| `xtool-home` | `/root` | Logins Apple, chaves (`.config/xtool-panel/secrets.json`), certificados de distribuição, contas do GitHub, SDK do iOS |
| `xtool-work` | `/work` | Projetos |
| Downloads do Windows | `/downloads` | `Xcode.xip` e `.ipa` |

> **Backup:** o volume `xtool-home` guarda os seus certificados e chaves. Faça backup antes de apagá-lo.

## Segurança

- O painel **não tem login** e executa comandos no container. Por isso ele só escuta em `127.0.0.1`. **Não exponha a porta 8080 na rede.**
- As chaves de API ficam em `secrets.json`, com permissão `600`, e nunca voltam completas para o navegador.
- As senhas Apple vão direto para o xtool pelo console. O painel não as grava.
- O login Apple por senha usa APIs privadas da Apple. Para contas importantes, prefira o modo **API Key**.

## Limitações conhecidas

- **Ícone para a App Store:** o `Assets.car` é gerado pelo accord, um projeto novo. Ainda não houve um envio de verdade que comprove que a Apple aceita esse arquivo. Se a validação recusar o ícone, a mensagem da Apple aparece no console.
- **Primeira versão:** as capturas de tela e os metadados obrigatórios precisam ser preenchidos no site do App Store Connect.
- **Recursos avançados:** extensões (widgets), App Groups e outras capacidades especiais podem exigir perfis com permissões extras.
- **USB direto:** o Docker Desktop não repassa USB. Use o serviço da Apple (recomendado) ou o usbipd.

## Solução de problemas

| Sintoma | Solução |
|---|---|
| "Conexão iPhone: desligado" | Abra o iTunes ou o Dispositivos Apple no Windows |
| iPhone não aparece | Desbloqueie a tela, toque em **Confiar** e confira o Modo de Desenvolvedor |
| `chave da API … não configurada` | Cadastre a chave no cartão da conta em **Contas Apple** |
| "não existe app no App Store Connect" | Crie o app com o mesmo bundle ID no site da Apple |
| "máximo de certificados de distribuição" | Revogue um certificado antigo em developer.apple.com → Certificates |
| A IA não conecta (Ollama/LM Studio) | Abra o app no Windows e confira se o servidor local está ligado |
| `no configuration file provided` | Rode o `docker compose` dentro da pasta do repositório |

## Atualização

**xtool:** o painel consulta a cada hora os [Releases do xtool](https://github.com/xtool-org/xtool/releases). Quando sai uma versão nova, o card **xtool** mostra **⬆ Atualizar**. A versão nova é instalada em `/root/.xtool`, no volume, e continua valendo depois de reiniciar o container.

**Painel inteiro** (imagem, ferramentas e interface):

```bash
git pull
docker compose up -d --build
```

As versões ficam fixas no `Dockerfile` (`XTOOL_VERSION`, `RCODESIGN_VERSION`, `ACCORD_VERSION`).

## Changelog

### 1.0.0

- Painel web com console interativo, tarefas, arquivos e terminal
- Várias contas Apple e vários dispositivos, com status de conexão em tempo real
- Conexão com o iPhone pelo serviço da Apple do Windows (cabo ou Wi-Fi)
- Registro de apps de todas as contas, com a conta dona e se ela tem API da Apple
- Chave da API da Apple cadastrada no cartão de cada conta
- Projetos vinculados a um app da conta (define a conta e o bundle ID usados na publicação)
- Ícone dos apps e prévia da página da App Store (publicada e próxima versão)
- Publicação na App Store: build, ícones, assinatura de distribuição, envio, "O que há de novo" e revisão
- Integração com GitHub (várias contas, importar, vincular, pull e push)
- IA para notas de versão com 11 provedores, inclusive locais
- Aviso de nova versão do xtool e atualização com um clique

## Créditos

- [xtool](https://github.com/xtool-org/xtool), de kabiroberai e colaboradores
- [accord / dine-accord](https://github.com/MiloLug/dine-accord), compilador de asset catalogs para Linux
- [apple-codesign (rcodesign)](https://github.com/indygreg/apple-platform-rs), de Gregory Szorc
- [xterm.js](https://xtermjs.org) e [GitHub CLI](https://cli.github.com)

<div align="center">

---

**xtool Painel 1.0.0** · By [marco3079](https://github.com/marco3079)

</div>
