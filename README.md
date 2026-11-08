<div align="center">

<img src="panel/static/logo.svg" width="112" alt="xtool Painel">

# xtool Painel

**Desenvolva, instale e publique apps iOS e Android sem Mac, direto pelo navegador.**

[![Versão](https://img.shields.io/badge/versão-1.1.0-4f8cff?style=flat-square)](#changelog)
[![xtool](https://img.shields.io/badge/xtool-1.24.0-7c5cff?style=flat-square)](https://github.com/xtool-org/xtool)
[![Swift](https://img.shields.io/badge/Swift-6.4.2-F05138?style=flat-square&logo=swift&logoColor=white)](https://swift.org)
[![Android](https://img.shields.io/badge/Android-SDK%2036-3DDC84?style=flat-square&logo=android&logoColor=white)](#android-e-google-play)
[![Google Play](https://img.shields.io/badge/Google%20Play-publicação-414141?style=flat-square&logo=googleplay&logoColor=white)](#publicar-no-google-play)
[![Docker](https://img.shields.io/badge/Docker-pronto-2496ED?style=flat-square&logo=docker&logoColor=white)](#instalação)
[![Plataforma](https://img.shields.io/badge/host-Windows%20%7C%20Linux-555?style=flat-square)](#requisitos)

By **[marco3079](https://github.com/marco3079)**

</div>

---

## Sumário

- [Visão geral](#visão-geral)
- [Recursos](#recursos)
- [Telas](#telas)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Primeiros passos](#primeiros-passos)
- [Conectar o iPhone](#conectar-o-iphone)
- [Publicar na App Store](#publicar-na-app-store)
- [Android e Google Play](#android-e-google-play)
- [Rodar no celular Android](#rodar-no-celular-android)
- [Publicar no Google Play](#publicar-no-google-play)
- [Versão do app](#versão-do-app)
- [IA para notas de versão](#ia-para-notas-de-versão)
- [GitHub](#github)
- [Arquitetura](#arquitetura)
- [Dados e volumes](#dados-e-volumes)
- [Segurança](#segurança)
- [Limitações conhecidas](#limitações-conhecidas)
- [Solução de problemas](#solução-de-problemas)
- [Atualização](#atualização)
- [Changelog](#changelog)
- [Como contribuir](#como-contribuir)
- [Créditos](#créditos)

## Visão geral

O **xtool Painel** coloca o [xtool](https://github.com/xtool-org/xtool) (uma alternativa ao Xcode que roda em qualquer sistema) e o **SDK do Android** dentro de um container Docker e adiciona um painel web completo. No navegador você gerencia todo o ciclo de um app:

- **iOS:** contas Apple, iPhones, compilação, assinatura, envio ao App Store Connect e publicação na App Store.
- **Android:** contas do Google Play, compilação de APK e AAB com Gradle, chave de assinatura, instalação no celular por Wi-Fi e publicação nas faixas da Google Play.
- **Para os dois:** projetos (inclusive um mesmo projeto Capacitor com iOS e Android), repositórios do GitHub, versão do app tirada do próprio projeto e notas de versão escritas por IA.

O xtool 1.24.0 vem dentro do repositório (`base/`), então o painel funciona sem depender do GitHub do xtool.

```
http://localhost:8080
```

## Recursos

| Área | O que faz |
|---|---|
| **Painel** | Mostra num relance as versões do xtool (`base`, do repositório, ou `xtool-org`, baixada pelo painel) e do Swift, a conta Apple em uso, o SDK do iOS, o Android (JDK, Node e SDK), o espaço em disco e a conexão com o iPhone. Avisa quando sai uma versão nova do xtool e atualiza com um clique |
| **Contas Apple** | Cadastra várias contas Apple, cada uma com o próprio login, e troca a conta em uso com um clique |
| **Contas Google Play** | Cadastra várias contas do Google Play (chave JSON de conta de serviço) e testa a conexão |
| **Apps da conta** | Aba **Apple**: registro de todos os apps de todas as contas, apps do App Store Connect com o estado de cada versão, bundle IDs com ícone e prévia da página da App Store num iPhone. Aba **Google Play**: apps de cada conta, versões por faixa (interno, fechado, aberto, produção) e prévia da página da Google Play com a ficha do Play Console |
| **Projetos** | Cria apps SwiftUI e reconhece projetos Android e Capacitor; compila em debug ou release; gera `.ipa` e `.apk`; roda no iPhone e no celular Android; gera projeto Xcode |
| **Publicar** | Aba **App Store**: compila em release, gera o ícone (`Assets.car`), assina para distribuição, envia ao App Store Connect, preenche "O que há de novo" e submete para revisão. Aba **Google Play**: gera APK/AAB assinado com a chave de upload, escreve as notas da versão e envia para a faixa escolhida |
| **GitHub** | Várias contas; lista os repositórios (inclusive de organizações); importa como projeto; vincula ou cria repositório; pull e push |
| **IA** | OpenAI, Anthropic, Google Gemini, Mistral, Groq, DeepSeek, xAI, OpenRouter, Together, Ollama e LM Studio (locais) ou qualquer API compatível com OpenAI |
| **Dispositivos** | Cadastra vários aparelhos com status em tempo real (cabo, Wi-Fi ou desconectado); instala, abre e remove apps |
| **Configuração** | `xtool setup` e gerenciamento do SDK do iOS a partir do `Xcode.xip` |
| **Arquivos** | Navega em `/work` e nos Downloads do Windows; envia, baixa e apaga arquivos |
| **Terminal** | Shell interativo dentro do container |
| **Tarefas** | Histórico de todos os comandos, com a saída completa |
| **Tema** | Escuro ou claro, no botão do topo |

Todo comando roda num terminal real (PTY). As perguntas interativas, como o código 2FA, a senha ou o caminho do Xcode.xip, são respondidas pelo console do próprio painel.

## Telas

> Dados pessoais (e-mails, nomes, IDs, chaves e aparelhos) aparecem borrados. Clique numa imagem para ver em tamanho real.

<table>
<tr>
<td width="50%" valign="top"><b>Painel</b><br><sub>Versões do xtool (base ou xtool-org), Swift, conta Apple, SDK do iOS, disco, conexão com o iPhone e Android.</sub><br><a href="docs/telas/01-painel.png"><img src="docs/telas/01-painel.png" alt="Painel"></a></td>
<td width="50%" valign="top"><b>Tema claro</b><br><sub>Alterna entre claro e escuro no botão do topo; o painel lembra a escolha.</sub><br><a href="docs/telas/19-tema-claro.png"><img src="docs/telas/19-tema-claro.png" alt="Tema claro"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>Configuração</b><br><sub>xtool setup e SDK do iOS a partir do Xcode.xip.</sub><br><a href="docs/telas/02-configuracao.png"><img src="docs/telas/02-configuracao.png" alt="Configuração"></a></td>
<td width="50%" valign="top"><b>Contas Apple</b><br><sub>Várias contas Apple, cada uma com o próprio login.</sub><br><a href="docs/telas/03-contas-apple.png"><img src="docs/telas/03-contas-apple.png" alt="Contas Apple"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>Contas Google Play</b><br><sub>Contas de serviço do Google Play (chave JSON).</sub><br><a href="docs/telas/04-contas-google-play.png"><img src="docs/telas/04-contas-google-play.png" alt="Contas Google Play"></a></td>
<td width="50%" valign="top"><b>Projetos</b><br><sub>Compilar, gerar .ipa/.apk e rodar no iPhone ou no Android.</sub><br><a href="docs/telas/05-projetos.png"><img src="docs/telas/05-projetos.png" alt="Projetos"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>Apps da conta · Apple</b><br><sub>Apps registrados, App Store Connect e bundle IDs.</sub><br><a href="docs/telas/06-apps-apple.png"><img src="docs/telas/06-apps-apple.png" alt="Apps da conta · Apple"></a></td>
<td width="50%" valign="top"><b>Apps da conta · Google Play</b><br><sub>Apps de cada conta Google Play e suas faixas.</sub><br><a href="docs/telas/07-apps-google-play.png"><img src="docs/telas/07-apps-google-play.png" alt="Apps da conta · Google Play"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>Prévia da App Store</b><br><sub>Como a página do app aparece na App Store do iPhone.</sub><br><a href="docs/telas/17-previa-app-store.png"><img src="docs/telas/17-previa-app-store.png" alt="Prévia da App Store"></a></td>
<td width="50%" valign="top"><b>Prévia da Google Play</b><br><sub>Como a página do app aparece na Google Play, com a ficha do Play Console.</sub><br><a href="docs/telas/18-previa-google-play.png"><img src="docs/telas/18-previa-google-play.png" alt="Prévia da Google Play"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>Publicar · App Store</b><br><sub>Versão, notas com IA, compilar, assinar, enviar e submeter.</sub><br><a href="docs/telas/08-publicar-app-store.png"><img src="docs/telas/08-publicar-app-store.png" alt="Publicar · App Store"></a></td>
<td width="50%" valign="top"><b>Publicar · Google Play</b><br><sub>APK/AAB assinado, chave de upload, notas da versão e faixas.</sub><br><a href="docs/telas/09-publicar-google-play.png"><img src="docs/telas/09-publicar-google-play.png" alt="Publicar · Google Play"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>GitHub</b><br><sub>Contas, repositórios e vínculo com projetos.</sub><br><a href="docs/telas/10-github.png"><img src="docs/telas/10-github.png" alt="GitHub"></a></td>
<td width="50%" valign="top"><b>Dispositivos</b><br><sub>Aparelhos com status em tempo real; instala, abre e remove apps.</sub><br><a href="docs/telas/11-dispositivos.png"><img src="docs/telas/11-dispositivos.png" alt="Dispositivos"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>Developer Services</b><br><sub>Times, certificados, bundle IDs, aparelhos e perfis.</sub><br><a href="docs/telas/12-developer-services.png"><img src="docs/telas/12-developer-services.png" alt="Developer Services"></a></td>
<td width="50%" valign="top"><b>IA</b><br><sub>Provedores para escrever as notas de versão.</sub><br><a href="docs/telas/13-ia.png"><img src="docs/telas/13-ia.png" alt="IA"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>Arquivos</b><br><sub>Navega em /work e nos Downloads; envia, baixa e apaga.</sub><br><a href="docs/telas/14-arquivos.png"><img src="docs/telas/14-arquivos.png" alt="Arquivos"></a></td>
<td width="50%" valign="top"><b>Terminal</b><br><sub>Shell interativo dentro do container.</sub><br><a href="docs/telas/15-terminal.png"><img src="docs/telas/15-terminal.png" alt="Terminal"></a></td>
</tr>
<tr>
<td width="50%" valign="top"><b>Tarefas</b><br><sub>Histórico de todos os comandos, com a saída completa.</sub><br><a href="docs/telas/16-tarefas.png"><img src="docs/telas/16-tarefas.png" alt="Tarefas"></a></td>
</tr>
</table>

## Requisitos

| Item | Observação |
|---|---|
| Docker Desktop (Windows) ou Docker Engine (Linux) | Com o Compose v2 |
| ~20 GB livres | Imagem, SDK do iOS, SDK do Android e builds |
| **iOS** · Xcode 27.x (`.xip`) | Baixe em [developer.apple.com/download](https://developer.apple.com/download/all/?q=Xcode) |
| **iOS** · Apple ID | Qualquer conta serve para instalar no próprio iPhone |
| **iOS** · Apple Developer Program | **Necessário para publicar na App Store**, junto com uma chave da API do App Store Connect |
| **iOS** · iTunes ou Dispositivos Apple (Windows) | Faz a ponte com o iPhone por cabo ou Wi-Fi |
| **Android** · nada a instalar | JDK 21, Node 22 e o SDK do Android (plataforma 36, build-tools 36) já vêm na imagem |
| **Android** · Conta de desenvolvedor Google Play | **Necessária para publicar**, junto com uma conta de serviço do Google Cloud com acesso ao Play Console |
| **Android** · Celular com Android 11+ | Para instalar por Wi-Fi (depuração sem fio), na mesma rede do PC |

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
5. **Android:** projetos com pasta `android/` (Gradle ou Capacitor) aparecem com a etiqueta 🤖 Android. Clique em **Gerar .apk** ou, com o celular pareado, em **▶ Rodar no Android**.
6. **Google Play:** em **Contas Google Play**, envie o JSON da conta de serviço. Depois adicione o app em **Apps da conta → Google Play**.

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

## Android e Google Play

O painel reconhece como Android qualquer projeto com Gradle na raiz ou numa pasta `android/`. Projetos **Capacitor** são detectados pelo `capacitor.config.*`. Um mesmo projeto pode ser iOS e Android ao mesmo tempo, e aparece com as duas etiquetas em **Projetos**.

| Botão (em Projetos) | O que faz |
|---|---|
| **Gerar .apk** | Só gera o APK, sem enviar para a loja. Sai assinado se o app tiver chave de upload; senão, em debug |
| **▶ Rodar no Android** | Gera o APK de debug, instala no celular escolhido e abre o app |
| **🤖 Android** | Abre **Publicar → Google Play** com o projeto já escolhido |

Antes do Gradle, o painel roda o pré-build do projeto. Para Capacitor, o padrão é `npm ci && npm run build… && npx cap sync android`, e dá para trocar ou pular. Os arquivos gerados ficam em `<projeto>/xtool/android/`.

## Rodar no celular Android

A instalação usa o `adb` por Wi-Fi, então não precisa de cabo nem de drivers no Windows.

1. No celular (Android 11+): **Opções do desenvolvedor → Depuração por Wi-Fi → Parear com código**.
2. Em **Publicar → Google Play**, no card **📲 Instalar no celular Android**, informe o `ip:porta` e o código de pareamento e clique em **Parear**.
3. Informe o `ip:porta` de conexão e clique em **Conectar**. O celular aparece na lista e em **Projetos → Rodar no Android (adb)**.

O PC e o celular precisam estar na mesma rede.

## Publicar no Google Play

### Pré-requisitos (uma vez por conta)

1. No [Google Cloud](https://console.cloud.google.com/iam-admin/serviceaccounts), crie uma **conta de serviço**, gere uma **chave JSON** e ative a **Google Play Android Developer API** no projeto.
2. No [Play Console → Usuários e permissões](https://play.google.com/console/users-and-permissions), convide o e-mail da conta de serviço com permissão para lançar versões.
3. No painel, em **Contas Google Play**, dê um nome à conta, envie o JSON e clique em **Testar**. Dá para cadastrar várias contas.
4. O app precisa já existir no Play Console, porque a API do Google não cria apps. Adicione-o pelo package name em **Apps da conta → Google Play**.
5. Na primeira vez, gere ou importe a **chave de upload** do app no card **🔑 Chave de assinatura**. Clique em **Baixar backup** e guarde o arquivo: sem essa chave não dá para atualizar o app na Play.

### Fluxo

Na seção **Publicar → Google Play**: escolha o projeto e a conta, confira a versão, gere ou escreva as notas da versão (até 500 caracteres por idioma), escolha a faixa e o status e clique em **🚀 Iniciar**.

| Etapa | O que acontece |
|---|---|
| 1/5 | Lê a versão e busca na Play o maior `versionCode` já enviado, para usar o próximo |
| 2/5 | Roda o pré-build do projeto web (Capacitor) |
| 3/5 | Compila com Gradle, grava `versionName`/`versionCode` e assina com a chave de upload |
| 4/5 | Junta o `.aab` e o `.apk` e confere a versão gravada dentro deles |
| 5/5 | Envia o AAB pela Google Play Developer API, grava as notas e lança na faixa escolhida |

| Faixa | Na Play |
|---|---|
| Teste interno | Até 100 testadores, liberado na hora |
| Teste fechado | Grupos de testadores (alpha) |
| Teste aberto | Qualquer pessoa pode entrar (beta) |
| Produção | Todos os usuários; dá para fazer lançamento gradual |

Com **Enviar para o Google Play** desmarcado, o painel só gera os arquivos assinados. Se o app nunca foi publicado, a Play só aceita o lançamento como rascunho, e o painel avisa no console.

## Versão do app

Cada projeto escolhe de onde vem a versão, tanto no Publicar da App Store quanto no da Google Play:

| Origem | De onde lê |
|---|---|
| Automático | Próxima versão depois da última enviada para a loja |
| `package.json` | Campo `version` |
| `xtool.yml` | Campo `version` (quando não é o número do esquema) |
| Gradle | `versionName` do `build.gradle` do Android |
| Xcode | `MARKETING_VERSION` do projeto iOS |
| Tag do git | Última tag, como `v1.2.0` |
| Manual | Você digita a cada envio |

O número do build (`CFBundleVersion` no iOS, `versionCode` no Android) é sempre calculado para ficar acima do último enviado.

## IA para notas de versão

Em **IA**, configure um ou mais provedores e marque um como padrão (★). Ao publicar, na App Store ou na Google Play, o painel junta os commits feitos desde a última publicação e pede à IA um texto curto, voltado ao usuário final, em cada idioma escolhido. Na Google Play, o painel pede à IA no máximo 500 caracteres (o limite da loja) e mostra um contador em cada idioma. O texto sempre pode ser revisado antes de enviar.

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
│ android.py  pré-build → Gradle → assinatura → AAB/APK → Play  │
│ play.py     Google Play Developer API (JWT RS256)             │
│ versions.py versão do app (package.json, Gradle, Xcode, git)  │
│ github.py   gh CLI (várias contas)   ai.py  provedores de IA  │
│ xtool · accord · rcodesign · gh · git · libimobiledevice      │
│ JDK 21 · Node 22 · Android SDK 36 · Gradle · adb              │
└──────┬──────────────────┬──────────────────┬────────────────┘
       │ host.docker.     │ adb por Wi-Fi    │ HTTPS
       │ internal:27015   │                  │
   Serviço Apple do   Celular Android   Apple · Google Play
   Windows ⇄ iPhone                     GitHub · IA
```

| Arquivo | Função |
|---|---|
| `Dockerfile` | Imagem com xtool, accord (compilado a partir do código), rcodesign, gh, Python, JDK, Node e SDK do Android |
| `base/` | xtool 1.24.0 zipado (versão base, instalada no build sem baixar do GitHub do xtool) |
| `docker-compose.yml` | Porta, volumes e acesso ao serviço da Apple |
| `panel/server.py` | Servidor HTTP, tarefas em PTY, contas, aparelhos e rotas |
| `panel/release.py` | Pipeline de publicação na App Store, executado como tarefa |
| `panel/android.py` | Build Android (Gradle), chaves de upload, instalação por adb e envio ao Google Play |
| `panel/play.py` | Cliente da Google Play Developer API |
| `panel/versions.py` | Lê a versão do app de cada origem do projeto |
| `panel/asc.py` | Cliente da API do App Store Connect |
| `panel/github.py` | Contas e repositórios do GitHub |
| `panel/ai.py` | Provedores de IA e geração do "O que há de novo" |
| `panel/store.py` | Configurações e segredos salvos |
| `panel/static/` | Interface (`index.html`) e logo |

## Dados e volumes

| Volume | Caminho | Conteúdo |
|---|---|---|
| `xtool-home` | `/root` | Logins Apple, chaves das APIs e contas do Google Play (`.config/xtool-panel/secrets.json`), chaves de upload do Android (`.config/xtool-panel/android-keys/`), certificados de distribuição, contas do GitHub, SDK do iOS, versões do xtool baixadas pelo painel (`.xtool/`) |
| `xtool-work` | `/work` | Projetos (os builds ficam em `<projeto>/xtool/`, e os do Android em `<projeto>/xtool/android/`) |
| Downloads do Windows | `/downloads` | `Xcode.xip`, `.ipa` e `.apk` |

> **Backup:** o volume `xtool-home` guarda os seus certificados e as chaves de upload do Android. Perder a chave de upload impede de atualizar o app na Google Play: baixe o backup de cada uma pelo painel e guarde fora do container.

## Segurança

- O painel **não tem login** e executa comandos no container. Por isso ele só escuta em `127.0.0.1`. **Não exponha a porta 8080 na rede.**
- As chaves de API e os JSON das contas de serviço do Google Play ficam em `secrets.json`, com permissão `600`, e nunca voltam completos para o navegador.
- As chaves de upload do Android ficam em `android-keys/`. As senhas delas (geradas pelo painel, ou as que você informou ao importar) ficam no `secrets.json` e não voltam para o navegador.
- As senhas Apple vão direto para o xtool pelo console. O painel não as grava.
- O login Apple por senha usa APIs privadas da Apple. Para contas importantes, prefira o modo **API Key**.

## Limitações conhecidas

- **Ícone para a App Store:** o `Assets.car` é gerado pelo accord, um projeto novo. Ainda não houve um envio de verdade que comprove que a Apple aceita esse arquivo. Se a validação recusar o ícone, a mensagem da Apple aparece no console.
- **Primeira versão:** as capturas de tela e os metadados obrigatórios precisam ser preenchidos no site do App Store Connect.
- **Recursos avançados:** extensões (widgets), App Groups e outras capacidades especiais podem exigir perfis com permissões extras.
- **USB direto:** o Docker Desktop não repassa USB. Use o serviço da Apple (recomendado) ou o usbipd. No Android, use o adb por Wi-Fi.
- **Apps novos na Google Play:** a API do Google não cria apps nem preenche a ficha da loja. Crie o app e envie a primeira versão pelo Play Console; depois o painel cuida das atualizações.
- **Lista de apps do Google Play:** a API não lista os apps da conta, então cada app é adicionado pelo package name.

## Solução de problemas

| Sintoma | Solução |
|---|---|
| "Conexão iPhone: desligado" | Abra o iTunes ou o Dispositivos Apple no Windows |
| iPhone não aparece | Desbloqueie a tela, toque em **Confiar** e confira o Modo de Desenvolvedor |
| `chave da API … não configurada` | Cadastre a chave no cartão da conta em **Contas Apple** |
| "não existe app no App Store Connect" | Crie o app com o mesmo bundle ID no site da Apple |
| "máximo de certificados de distribuição" | Revogue um certificado antigo em developer.apple.com → Certificates |
| "Google recusou a chave da conta de serviço" | Gere uma chave JSON nova da conta de serviço e envie de novo em **Contas Google Play** |
| `Google Play 403` / "permission" | Convide o e-mail da conta de serviço no Play Console com permissão para lançar versões e ative a Google Play Android Developer API |
| `Google Play 404` / "package not found" | O app ainda não existe no Play Console, ou o package name está diferente |
| A Play recusa o `versionCode` | Deixe o código em **auto**: o painel usa o próximo depois do maior que já está na Play |
| Celular Android não aparece | Pareie de novo (o código muda a cada vez), confira a mesma rede e clique em **Conectar** com a porta de conexão, que é diferente da de pareamento |
| A IA não conecta (Ollama/LM Studio) | Abra o app no Windows e confira se o servidor local está ligado |
| `no configuration file provided` | Rode o `docker compose` dentro da pasta do repositório |

## Atualização

**xtool:** a versão **base** (1.24.0) vem do repositório, em `base/`, e é instalada no build da imagem sem acessar o GitHub do xtool. Com internet, o painel consulta a cada hora os [Releases do xtool](https://github.com/xtool-org/xtool/releases). Quando sai uma versão nova, o card **xtool** mostra **⬆ Atualizar**. A versão baixada aparece como **xtool-org**, fica em `/root/.xtool`, no volume, e continua valendo depois de reiniciar o container. Sem internet, o painel segue com a versão base.

**Painel inteiro** (imagem, ferramentas e interface):

```bash
git pull
docker compose up -d --build
```

As versões ficam fixas no `Dockerfile` (`XTOOL_VERSION`, `RCODESIGN_VERSION`, `ACCORD_VERSION`, `NODE_VERSION`, `ANDROID_PLATFORM`, `ANDROID_BUILD_TOOLS`).

## Changelog

### 1.1.0

- **Android:** build de APK e AAB com Gradle (inclusive Capacitor), em debug ou assinado com a chave de upload
- Chave de upload por app: gerar, importar e baixar o backup
- Instalar e abrir o app no celular Android por adb Wi-Fi (**▶ Rodar no Android**)
- **Google Play:** várias contas (conta de serviço), apps por conta com as faixas e publicação em teste interno, fechado, aberto ou produção
- Prévia da página da Google Play com a ficha do Play Console (ícone, capturas, recurso gráfico, descrição, novidades e contato)
- Versão do app escolhida por projeto: automática, `package.json`, `xtool.yml`, Gradle, Xcode, tag do git ou manual
- Menu reorganizado: **Apps da conta** e **Publicar** com abas Apple / Google Play
- xtool 1.24.0 dentro do repositório (`base/`), identificado no painel como **base**; versões baixadas aparecem como **xtool-org**
- Tema claro, barras de rolagem novas e capturas de tela arrastáveis nas prévias das lojas
- IDs de desenvolvimento do xtool (`XTL-…`) escondidos da lista de apps

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

## Como contribuir

- Só o dono do repositório faz commit, push ou merge na `main`.
- Cada colaborador trabalha em branches com o próprio login na frente: `<seu-login>/<nome>` (ex.: `WasDevFullStack/nova-tela`), e abre um pull request para a `main`.

A Action [Guarda das branches](.github/workflows/guarda-branches.yml) confere cada push: se alguém que não é o dono mexer na `main` ou numa branch que não é a dele, o push é desfeito na hora. Os commits não se perdem: ficam numa branch `bloqueado/<login>-<commit>`, e uma issue avisa o que aconteceu.

## Créditos

- [xtool](https://github.com/xtool-org/xtool), de kabiroberai e colaboradores
- [accord / dine-accord](https://github.com/MiloLug/dine-accord), compilador de asset catalogs para Linux
- [apple-codesign (rcodesign)](https://github.com/indygreg/apple-platform-rs), de Gregory Szorc
- [xterm.js](https://xtermjs.org) e [GitHub CLI](https://cli.github.com)
- [Android SDK](https://developer.android.com/tools), [Gradle](https://gradle.org) e [Google Play Developer API](https://developers.google.com/android-publisher)

<div align="center">

---

**xtool Painel 1.1.0** · By [marco3079](https://github.com/marco3079)

</div>
