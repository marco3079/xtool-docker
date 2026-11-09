<div align="center">

<img src="panel/static/logo.svg" width="112" alt="xtool Painel">

# xtool Painel

**Desenvolva, instale e publique apps iOS e Android sem Mac, direto pelo navegador.**

[![Versão](https://img.shields.io/badge/versão-1.2.0-4f8cff?style=flat-square)](#changelog)
[![xtool](https://img.shields.io/badge/xtool-1.24.0-7c5cff?style=flat-square)](https://github.com/xtool-org/xtool)
[![Swift](https://img.shields.io/badge/Swift-6.4.2-F05138?style=flat-square&logo=swift&logoColor=white)](https://swift.org)
[![Android](https://img.shields.io/badge/Android-SDK%2036-3DDC84?style=flat-square&logo=android&logoColor=white)](#android-e-google-play)
[![Google Play](https://img.shields.io/badge/Google%20Play-publicação-414141?style=flat-square&logo=googleplay&logoColor=white)](#publicar-no-google-play)
[![Electron](https://img.shields.io/badge/Electron-PC-47848F?style=flat-square&logo=electron&logoColor=white)](#compilar-para-pc-electron)
[![Steam](https://img.shields.io/badge/Steam-publicação-1b2838?style=flat-square&logo=steam&logoColor=white)](#publicar-na-steam)
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
- [Projetos: configurar, compilar e enviar](#projetos-configurar-compilar-e-enviar)
- [Conectar o iPhone](#conectar-o-iphone)
- [Publicar na App Store](#publicar-na-app-store)
- [Android e Google Play](#android-e-google-play)
- [Rodar no celular Android](#rodar-no-celular-android)
- [Publicar no Google Play](#publicar-no-google-play)
- [Compilar para PC (Electron)](#compilar-para-pc-electron)
- [Publicar na Steam](#publicar-na-steam)
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
- **PC:** projetos web e Capacitor viram app desktop com Electron (Windows, Linux e macOS), e o build pode ser enviado para a Steam.
- **Para os dois:** projetos (inclusive um mesmo projeto Capacitor com iOS e Android), repositórios do GitHub, versão do app tirada do próprio projeto e notas de versão escritas por IA.

O xtool 1.24.0 vem dentro do repositório (`base/`), então o painel funciona sem depender do GitHub do xtool.

```
http://localhost:8080
```

## Recursos

| Área | O que faz |
|---|---|
| **Painel** | Mostra num relance as versões do xtool (`base`, do repositório, ou `xtool-org`, baixada pelo painel) e do Swift, a conta Apple em uso, o SDK do iOS, o Android (JDK, Node e SDK), o espaço em disco e a conexão com o iPhone. Avisa quando sai uma versão nova do xtool e atualiza com um clique |
| **Contas** → Apple | Aba **Apple** do menu **Contas**: cadastra várias contas Apple, cada uma com o próprio login, e troca a conta em uso com um clique |
| **Contas** → Google Play | Aba **Google Play** do menu **Contas**: cadastra várias contas do Google Play (chave JSON de conta de serviço) e testa a conexão |
| **Contas** → Steam | Aba **Steam** do menu **Contas**: cadastra contas Steam (nome e usuário de build do Steamworks, sem senha) e faz o login pelo console do steamcmd. Cada conta mostra se está **Conectada**, **Sem login**, **Ocupado…** ou **Não verificado** (checagem com o login salvo, com o botão **↻ Verificar**). O botão **★ Principal** define a conta do topo |
| **Apps da conta** | Aba **Apple**: registro de todos os apps de todas as contas, apps do App Store Connect com o estado de cada versão, bundle IDs com ícone e prévia da página da App Store num iPhone. Aba **Google Play**: apps de cada conta, versões por faixa (interno, fechado, aberto, produção) e prévia da página da Google Play com a ficha do Play Console. Aba **Steam**: apps registrados (todas as contas) com App ID, Depot IDs por plataforma e branch padrão, apps da conta selecionada e botão **Publicar**, que abre Publicar → 🎮 Steam (PC) com o app escolhido |
| **Barra do topo** | Seletores da **conta Steam** (🎮) e da **conta Google Play** (▶): a escolha vira a conta principal salva, usada como padrão nas telas de Publicar e Apps da conta quando o projeto ainda não tem conta própria. Três indicadores iguais, clicáveis (abrem a aba correspondente de Dispositivos): **iPhone** (conectado, desconectado ou "abra o iTunes" quando o serviço Apple do Windows está desligado; a dica lista os aparelhos e se estão por cabo ou Wi-Fi), **Android** (conectado ou desconectado, pelo `adb devices`) e **PC** (conectado ou desconectado, pelo `host.docker.internal`; a dica mostra também se o serviço Apple está ativo), atualizados a cada 5 segundos. O aparelho iPhone padrão agora é escolhido em Dispositivos (★). Em telas com menos de 860 px, o topo esconde esses seletores e indicadores |
| **Projetos** | Cria apps SwiftUI, com repositório do GitHub criado na hora (veja [GitHub](#github)), e reconhece projetos Android e Capacitor; compila em debug ou release; gera `.ipa` e `.apk`; roda no iPhone e no celular Android; gera projeto Xcode; etiquetas em **Projetos**: 🍎 iOS, 🤖 Android, 🖥️ PC (projetos com `package.json`, com ⚙ Configurar, 🔨 Build, 📤 Enviar para a loja e Arquivos) e 🎮 Steam (quando o projeto está vinculado a um app Steam); o **Tipo de código** (automático ou escolhido) do build de PC é salvo por projeto; (veja [Projetos: configurar, compilar e enviar](#projetos-configurar-compilar-e-enviar)); no card, as linhas do app do Google Play e da Steam, com vincular ou trocar, conta e estado |
| **Publicar** | Aba **App Store**: compila em release, gera o ícone (`Assets.car`), assina para distribuição, envia ao App Store Connect, preenche "O que há de novo" e submete para revisão. Aba **Google Play**: gera APK/AAB assinado com a chave de upload, escreve as notas da versão e envia para a faixa escolhida. Aba **🎮 Steam (PC)**: compila o site para Windows, Linux e macOS com Electron, escreve a descrição do build e envia para a Steam pelo steamcmd. O **Tipo de código** do card 2 preenche o comando e a pasta do site |
| **GitHub** | Várias contas; lista os repositórios (inclusive de organizações); importa como projeto; novo projeto cria o repositório na conta escolhida; vincula ou cria repositório; pull automático pelo card do projeto (só fast-forward, com barra de progresso do download); push pelo Terminal ou pelo seu cliente git |
| **IA** | OpenAI, Anthropic, Google Gemini, Mistral, Groq, DeepSeek, xAI, OpenRouter, Together, Ollama e LM Studio (locais) ou qualquer API compatível com OpenAI |
| **Dispositivos** | Abas **📱 iPhone (iOS)**, **🤖 Android** e **🖥️ PC**. iPhone: cadastra vários aparelhos com status em tempo real (cabo, Wi-Fi ou desconectado); instala, abre e remove apps. Android: celulares do `adb`, com pareamento por Wi-Fi, conexão, status, instalação de APK e abertura do app. PC: status do Windows alcançado pelo container, serviço Apple, steamcmd, Node/npx, cache do Electron e os builds de PC dos projetos; card **Instalar .apk** (também na Home): arraste um .apk ou escolha um de `/work`, escolha o celular e instale por adb |
| **Configuração** | `xtool setup` e gerenciamento do SDK do iOS a partir do `Xcode.xip` |
| **Arquivos** | Navega em `/work` e nos Downloads do Windows; envia, baixa e apaga arquivos |
| **Terminal** | Shell interativo dentro do container |
| **Tarefas** | Histórico de todos os comandos, com a saída completa |
| **Tema** | Escuro ou claro, no botão do topo |

Ícones oficiais das plataformas (Apple, Google Play, Steam, Android) em todo o painel.

Todo comando roda num terminal real (PTY). As perguntas interativas, como o código 2FA, a senha ou o caminho do Xcode.xip, são respondidas pelo console do próprio painel.

## Telas

> Dados pessoais (e-mails, nomes, IDs, chaves e aparelhos) aparecem borrados. Clique numa imagem para ver em tamanho real.
>
> Os prints são anteriores à junção das contas num único menu **Contas** (com abas) e aos novos ícones das plataformas; as telas "Contas Apple" e "Contas Google Play" mostram o menu antigo.

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
| **PC** · nada a instalar | O Electron é baixado no primeiro build e fica em cache no container; precisa de internet nesse primeiro build. A imagem padrão tem cerca de 8 GB e inclui ImageMagick. O Wine é opcional (`INSTALL_WINE=1`), é preciso para o ícone e os metadados do `.exe` e adiciona cerca de 3,9 GB |
| **Steam** · conta de parceiro Steamworks | Taxa de US$ 100 por app, paga à Valve; App ID e Depot IDs criados no Steamworks, e um usuário de build com permissão de publicar builds |

## Instalação

```bash
git clone https://github.com/marco3079/xtool-docker.git
cd xtool-docker
docker compose up -d --build
```

Depois abra **http://localhost:8080**. O primeiro build demora alguns minutos, porque compila o `accord` a partir do código-fonte.

## Primeiros passos

1. **SDK do iOS:** coloque o `Xcode_27.x.xip` na pasta Downloads. No painel, vá em **Configuração → Instalar SDK**.
2. **Conta Apple:** em **Contas** → Apple → **Nova conta**, entre com o Apple ID. O código 2FA é pedido no console.
3. **Projeto:** em **Projetos → Novo projeto**, escolha a conta do GitHub (cadastre antes, no menu **GitHub**), o nome do repositório (padrão: o nome do projeto) e se ele é privado (padrão) ou público. O painel cria o projeto e o repositório. Ou importe um repositório em **GitHub → Importar como projeto**.
4. **Rodar no iPhone:** com o iPhone conectado, no card do projeto abra **🔨 Build**, escolha 🍎 iOS em **Debug** e marque **Instalar e abrir no iPhone**.
5. **Android:** projetos com pasta `android/` (Gradle ou Capacitor) aparecem com a etiqueta 🤖 Android. No card, abra **🔨 Build**, escolha 🤖 Android em **Debug** e marque **Instalar e abrir no celular Android** (com o celular pareado, veja [Rodar no celular Android](#rodar-no-celular-android)).
6. **Google Play:** em **Contas** → Google Play, envie o JSON da conta de serviço. Depois adicione o app em **Apps da conta → Google Play**.
7. **PC:** no card do projeto, abra **⚙ Configurar** para definir o PC (sistemas, tipo de código e pasta do site) e **🔨 Build** para gerar o app. Em **Publicar → 🎮 Steam (PC)** você também compila para Windows, Linux e macOS e envia à Steam.
8. **Steam:** no menu **Contas** → Steam, cadastre a conta de build, clique em **Login** e digite a senha e o código do Steam Guard no console. Marque-a como **★ Principal** no topo. Depois cadastre o app em **Apps da conta → Steam** e, em **Publicar → 🎮 Steam (PC)**, envie o build.
9. **Projetos:** no card do projeto, use **⚙ Configurar** → **🔨 Build** → **📤 Enviar para a loja**, como descrito em [Projetos: configurar, compilar e enviar](#projetos-configurar-compilar-e-enviar).

## Projetos: configurar, compilar e enviar

Cada projeto tem um card na aba **Projetos** com até três botões: **⚙ Configurar**, **🔨 Build** e **📤 Enviar para a loja**. Abaixo da linha da Apple, o card mostra a linha do app do Google Play e a da Steam, com **trocar** para vincular ou trocar o app, a conta e o estado (API do Google Play, ou Conectada e Sem login da Steam). Antes de cada diálogo que busca dados (Configurar, Build, Enviar e os vínculos), aparece um popup de carregamento.

1. **⚙ Configurar** (sempre aparece) abre o diálogo completo do projeto, com um interruptor por plataforma: **🍎 iPhone (iOS)**, **🤖 Android** e **🖥️ Steam (PC)**. Cada uma mostra **Pronto**, **Falta configurar** ou **Desativado**; com o interruptor ligado, aparece o motivo se algo faltar. O card ganha a etiqueta **⚙ falta configurar** quando uma plataforma ativada não está pronta. **Salvar** grava tudo de uma vez.
   - **🍎 iPhone (iOS):** o **bundle ID** e o vínculo do app da Apple (**Vincular / trocar app da Apple**, com a conta Apple do projeto). Fica pronto quando há `Package.swift` (projeto xtool, com SwiftPM). Sem ele, o painel explica o motivo: projeto web ou Capacitor não vira iOS aqui, porque o Capacitor iOS exige Xcode num Mac. Nada é criado.
   - **🤖 Android:** o **package name**, o **comando antes do Gradle** (vazio = padrão detectado, `-` = pular), a conta do Google Play e o vínculo do app (**Vincular / trocar app do Google Play**). Fica pronto quando há a pasta `android/` (Gradle). Se não há, mas existe `capacitor.config`, o botão **Adicionar Android** roda `npx cap add android`, que instala as dependências e o `@capacitor/android` se faltarem. Sem Capacitor, o painel só explica o que instalar.
   - **🖥️ Steam (PC):** os sistemas operacionais (Windows, Linux e macOS), o **tipo de código**, o **nome do app**, o **comando antes do build**, a **pasta do site**, a **versão do Electron**, gerar **.zip**, o vínculo do app da Steam (**Vincular / trocar app da Steam**) e a **branch**. Fica pronto quando há um tipo de código (o detectado ou o escolhido).
   - **Versão do projeto:** **Configurar versão…** escolhe a origem da versão (veja [Versão do app](#versão-do-app)).
2. **🔨 Build** (aparece com ao menos uma plataforma ativada e pronta; só essas aparecem no popup): um popup escolhe as plataformas. iOS e Android podem ser Debug ou Release, e o PC pode ter Windows, Linux e macOS. O popup também escolhe a versão (automática, `package.json`, `xtool.yml`, Gradle, Xcode, tag do git ou manual; a origem fica salva por projeto) e se o build é enviado para a loja ao terminar: iOS para o App Store Connect, Android para o Google Play (com faixa e status) e PC para a Steam (com conta, app e branch). O debug não vai para a loja. O texto "O que há de novo" pode ser gerado com IA. Tudo roda em sequência numa única tarefa (ordem: Android, PC, iOS) e para na primeira falha.
3. **📤 Enviar para a loja:** considera só builds release e fica desabilitado enquanto não existir nenhum. Lista as versões prontas (versão, build, tipo, data e tamanho) para você escolher, e envia o arquivo que já existe, **sem recompilar**:
   - **iOS:** o `.ipa` assinado (`xtool/<projeto>-<versão>-<build>.ipa`).
   - **Android:** o `.aab` ou `.apk` de `xtool/android/`, sem `-debug` no nome.
   - **PC:** o zip ou a pasta pronta, enviados à Steam.

   A versão de um build pronto não muda: para outra versão, gere um novo em **🔨 Build**. Antes de enviar, o painel confere que o número do build do iOS ainda não existe no App Store Connect e que o `Info.plist` do `.ipa` bate com a versão, o build e o bundle ID. No Android, o `versionCode` precisa ser maior que o último na Google Play.

Para publicar em cada loja, veja também [Publicar na App Store](#publicar-na-app-store), [Publicar no Google Play](#publicar-no-google-play) e [Publicar na Steam](#publicar-na-steam).

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
2. No painel, vá em **Contas** → Apple, clique em **🔑 Cadastrar API da Apple** no cartão da conta, informe o **Issuer ID**, o **Key ID** e o arquivo `.p8`, e clique em **Testar**. Cada conta tem a sua chave.
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

No card do projeto, o **⚙ Configurar** mostra o Android (pronto, falta configurar ou desativado). Se há Capacitor mas não há a pasta `android/`, o botão **Adicionar Android** roda `npx cap add android`. O APK e o AAB saem pelo **🔨 Build**:

| Como | O que faz |
|---|---|
| **🔨 Build** · Android · Debug | Gera o APK de debug. Com **Instalar e abrir no celular Android** marcado, instala no celular escolhido (aparelhos conectados) e abre o app |
| **🔨 Build** · Android · Release | Gera o AAB assinado. Com **Enviar para a loja ao terminar** marcado, envia para o Google Play |
| **📤 Enviar para a loja** | Envia um AAB ou APK de release já pronto, sem recompilar |

Antes do Gradle, o painel roda o pré-build do projeto. Para Capacitor, o padrão é `npm ci && npm run build… && npx cap sync android`, e dá para trocar ou pular. Os arquivos gerados ficam em `<projeto>/xtool/android/`.

## Rodar no celular Android

A instalação usa o `adb` por Wi-Fi, então não precisa de cabo nem de drivers no Windows.

1. No celular (Android 11+): **Opções do desenvolvedor → Depuração por Wi-Fi → Parear com código**.
2. Em **Publicar → Google Play**, no card **📲 Instalar no celular Android**, informe o `ip:porta` e o código de pareamento e clique em **Parear**.
3. Informe o `ip:porta` de conexão e clique em **Conectar**. O celular aparece na lista de aparelhos do **🔨 Build** (Android, Debug) e em **Dispositivos → Android**.

O PC e o celular precisam estar na mesma rede.

## Publicar no Google Play

### Pré-requisitos (uma vez por conta)

1. No [Google Cloud](https://console.cloud.google.com/iam-admin/serviceaccounts), crie uma **conta de serviço**, gere uma **chave JSON** e ative a **Google Play Android Developer API** no projeto.
2. No [Play Console → Usuários e permissões](https://play.google.com/console/users-and-permissions), convide o e-mail da conta de serviço com permissão para lançar versões.
3. No painel, em **Contas** → Google Play, dê um nome à conta, envie o JSON e clique em **Testar**. Dá para cadastrar várias contas.
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

## Compilar para PC (Electron)

Projetos web e Capacitor viram um app desktop com **Electron**, para **Windows, Linux e macOS** (arquitetura x64). Tudo roda dentro do container, com `@electron/packager` pelo `npx`, que baixa o Electron e guarda no cache em `/root/.cache/electron`.

O painel copia o site já compilado (a pasta `dist/`, `build/`, `www/` ou `out/`, ou o `webDir` do Capacitor) para um app Electron mínimo gerado em `<projeto>/xtool/pc/app/`. O projeto do usuário não é alterado. Os pacotes saem em `<projeto>/xtool/pc/out/<Nome>-<plataforma>-x64/` e, se marcado, são zipados em `<projeto>/xtool/pc/<Nome>-<versão>-<plataforma>-x64.zip`.

O app abre o site pelo protocolo interno `app://` (e não por arquivo), então caminhos absolutos como `/assets/...` funcionam e as rotas de SPA caem no `index.html`.

**Ícone e metadados do `.exe`:** no Windows, com o Wine instalado (`INSTALL_WINE=1`, veja [Atualização](#atualização)), o painel aplica o nome do produto, a descrição, a empresa e o nome do arquivo. O ícone é um PNG do projeto, procurado nesta ordem (vale o primeiro que existir):

1. `resources/icon.png` ou `resources/icon.ico`
2. `public/icon.png`, `public/icons/icon-512x512.png` ou `public/icons/icon-512.png`
3. `assets/icon.png` ou `icon.png` na raiz do projeto
4. Dentro da pasta do site: `icon.png`, `icons/icon-512x512.png`, `icons/icon-512.png`, `favicon.png` ou `apple-touch-icon.png`

O mesmo PNG vira o ícone da janela e da barra de tarefas em todas as plataformas, e é convertido para `.ico` automaticamente. Sem ícone, o `.exe` leva só os metadados e o console avisa. Sem Wine, o console avisa que ícone e metadados do `.exe` não foram aplicados. O ícone do macOS (`.icns`) não é aplicado.

### Pré-requisitos (uma vez)

1. Compile o site antes (ou informe um comando em **Compilar para PC**).
2. Tenha internet no primeiro build, porque é nele que o Electron é baixado.

### Fluxo

Em **Publicar → 🎮 Steam (PC)**, na aba **2·Compilar para PC**:

| Opção | O que faz |
|---|---|
| Plataformas | Windows, Linux e macOS (qualquer combinação) |
| Gerar .zip | Zipa cada pacote gerado em `<projeto>/xtool/pc/` |
| Comando antes do build | Comando rodado antes de pegar o site compilado |
| Pasta do site | Pasta com o site já compilado (`dist/`, `build/`, `www/`, `out/` ou o `webDir` do Capacitor) |
| Versão do Electron | Versão do Electron usada para montar o app |
| Tipo de código | Diz como o site é gerado (tabela abaixo). Preenche o comando antes do build e a pasta do site, que você pode editar depois |

O **Tipo de código** é escolhido por projeto e vale também para o **🔨 Build** do card de Projetos e para o envio à Steam. Ele pode ser **Automático**, que detecta pelo projeto e mostra "Detectado: <tipo>" com a sugestão. Antes de compilar, o painel faz verificações e mostra avisos ou erros embaixo do seletor:

- **TypeScript:** avisa se falta `tsconfig.json`; dá erro se não há script de build nem `tsconfig.json`.
- **JavaScript com build:** dá erro se o `package.json` não tem script de build (`build`, `build:prod`, `build:client` ou `build:client:prod`).
- **JavaScript / HTML puro:** não roda build; procura o `index.html` na raiz, em `public`, `www`, `src` ou `dist`. Na raiz, `node_modules`, `.git`, `xtool`, `android` e `ios` ficam de fora da cópia.
- **Capacitor:** exige `capacitor.config`; não roda `npx cap sync`, porque não é preciso para o PC.
- **Next.js:** precisa de `output: 'export'` no `next.config`; a saída fica em `out`.
- **Nuxt:** usa `npx nuxi generate` (ou `npm run generate`); a saída fica em `.output/public`.
- **SvelteKit:** usa `build` e precisa do adapter-static.
- **Personalizado:** você digita o comando e a pasta; se deixar `-`, não roda nada.

| Tipo | O que roda | Pasta do site |
|---|---|---|
| Automático | É o comportamento padrão: `npm ci` (ou `npm install`) + o primeiro script de build entre `build:client:prod`, `build:prod`, `build:client` e `build`. O tipo sugerido aparece só como dica "Detectado: …" | Pasta detectada (`dist`, `build`, `www` ou `out`) |
| TypeScript | `tsc`, Vite ou Webpack | Saída do build (`dist/`, `build/`, `www/` ou `out/`) |
| JavaScript com build | Vite, Webpack ou Parcel (script de build) | Saída do build (`dist/`, `build/`, `www/` ou `out/`) |
| JavaScript / HTML puro | Nada; copia a pasta | Pasta com o `index.html` (raiz, `public`, `www`, `src` ou `dist`) |
| Capacitor | Só o build web (sem `cap sync`) | O `webDir` do Capacitor |
| Next.js / Nuxt / SvelteKit (exporta estático) | Conforme o framework (lista abaixo) | Conforme o framework (lista abaixo) |
| Personalizado | O comando que você digitar (`-` não roda nada) | A pasta que você digitar |

Para o tipo de frameworks estáticos:

- **Next.js:** `npm run build`; pasta `out` (exige `output: 'export'` no `next.config`).
- **Nuxt:** `npm run generate` ou `npx nuxi generate`; pasta `.output/public`.
- **SvelteKit:** `npm run build`; pasta `build` (exige adapter-static).
- **Astro:** `npm run build`; pasta `dist` (entra no mesmo tipo de frameworks).

Em **Projetos**, o **🔨 Build** com a plataforma PC marcada (Windows, Linux e macOS, com .zip conforme a configuração salva) leva a esses recursos.

Para enviar o build à Steam, o app precisa estar cadastrado em **Apps da conta → Steam** (veja [Publicar na Steam](#publicar-na-steam)). A conta Steam marcada como **★ Principal** no topo é a padrão.

## Publicar na Steam

O painel gera os arquivos do **SteamPipe** (`app_build_<AppID>.vdf` e `depot_build_<DepotID>.vdf`, em `<projeto>/xtool/steam/`) e roda o **steamcmd**, que já vem instalado na imagem, para enviar o build à Steam.

### Pré-requisitos (uma vez)

1. Crie uma **conta de parceiro Steamworks**. Cada app paga uma taxa de **US$ 100**, paga à Valve.
2. No Steamworks, crie o **App ID** do app e um **Depot ID** para cada plataforma (Windows, Linux e macOS).
3. Crie um **usuário de build** com permissão de publicar builds e ative o **Steam Guard** dele.
4. No painel, em **Contas** → Steam, cadastre a conta (nome e usuário de build; a senha não é gravada) e clique em **Login**. A senha e o código do Steam Guard são digitados no console, direto no steamcmd. O login fica em `/root/Steam`, no volume `xtool-home`. Quando o login salvo vale, o card da conta mostra **Conectada**.
5. Cadastre o app em **Apps da conta → Steam**, com o App ID, o nome, o Depot ID de cada plataforma e a branch padrão. O Steamworks não tem API pública para listar apps, então cada app é cadastrado à mão. O botão **Publicar** dessa linha abre **Publicar → 🎮 Steam (PC)** já com o app escolhido.
6. Marque a conta com **★ Principal** no topo para usá-la como padrão nas telas de Publicar e Apps da conta, enquanto o projeto não tiver conta própria.

### Fluxo

Na seção **Publicar → 🎮 Steam (PC)**:

1. **Versão:** escolha a origem da versão (as mesmas da versão do app).
2. **Compilar para PC:** plataformas, gerar .zip, comando antes do build, pasta do site e versão do Electron.
3. **Descrição do build:** até 200 caracteres. Pode ser gerada com IA a partir dos commits.
4. **Compilar e enviar:** enviar para a Steam (sim ou não), compilar antes de enviar e a branch a liberar.

| Etapa | O que acontece |
|---|---|
| 1/5 | Confere a conta, o app e os depots |
| 2/5 | Compila para PC com Electron |
| 3/5 | Gera os arquivos `.vdf` do SteamPipe |
| 4/5 | Roda `steamcmd +login <usuário> +run_app_build` |
| 5/5 | Registra a última publicação |

Se a branch ficar em branco, o build só é enviado, e você libera a versão no site do Steamworks. A branch `default` não pode ser liberada pelo steamcmd.

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
- **Novo projeto:** exige um repositório do GitHub de uma conta cadastrada. No formulário **Novo projeto** (aba Projetos), escolha a conta, o nome do repositório (padrão: o nome do projeto) e se ele é privado (padrão) ou público. O painel cria o projeto com `xtool new`, faz `git init` e o primeiro commit, cria o repositório com `gh repo create`, faz o primeiro push e grava o vínculo no projeto. Sem conta cadastrada, o botão fica desabilitado. Nada é criado se já existir um projeto com esse nome em `/work` ou um repositório com esse nome no GitHub.
- **Importar:** clona um repositório como novo projeto em `/work`.
- **Vincular:** liga um projeto existente a um repositório e cria o repositório como privado se ele não existir.
- **Pull automático:** o painel faz `git fetch` de cada projeto vinculado ao GitHub a cada 2 minutos (na primeira vez, 20 s depois de abrir o painel) e só atualiza por fast-forward quando a árvore está limpa e não há commits locais à frente. Nunca usa pull com merge ou rebase, reset nem stash. Projetos com tarefa rodando na pasta são pulados. Durante o download, o card mostra uma barra de progresso com a fase (Preparando, Compactando no servidor, Baixando ou Montando), o percentual, o volume baixado e a velocidade; sem percentual, a barra fica animada. A barra é atualizada a cada 2 segundos. O fetch tem até 15 minutos (repositórios grandes demoram), e um download cancelado apaga os próprios restos (`tmp_pack_*`). Com a seção **Projetos** aberta, o card se atualiza sozinho a cada 2 minutos.
- **Estado no card:** o card mostra **atualizado automaticamente (+N)**, **baixando atualizações…**, **em dia**, **pull automático em espera: há alterações locais**, **divergente: faça o pull à mão** ou **pull automático falhou**. O card também mostra o código curto do último commit e o número sequencial dele (`#N`, a quantidade de commits da branch).
- **Push:** o botão saiu do card. Para enviar (push), use o Terminal do painel ou o seu cliente git.

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
│ pc.py       Electron: site → app → Win/Linux/macOS → .zip     │
│ steam.py    SteamPipe (.vdf) e steamcmd: login e envio        │
│ versions.py versão do app (package.json, Gradle, Xcode, git)  │
│ github.py   gh CLI (várias contas)   ai.py  provedores de IA  │
│ xtool · accord · rcodesign · gh · git · libimobiledevice      │
│ JDK 21 · Node 22 · Android SDK 36 · Gradle · adb              │
└──────┬──────────────────┬──────────────────┬────────────────┘
       │ host.docker.     │ adb por Wi-Fi    │ HTTPS
       │ internal:27015   │                  │
   Serviço Apple do   Celular Android   Apple · Google Play
   Windows ⇄ iPhone                     GitHub · IA · Steam
```

| Arquivo | Função |
|---|---|
| `Dockerfile` | Imagem com xtool, accord (compilado a partir do código), rcodesign, gh, Python, JDK, Node, SDK do Android, steamcmd e ImageMagick (Wine opcional) |
| `base/` | xtool 1.24.0 zipado (versão base, instalada no build sem baixar do GitHub do xtool) |
| `docker-compose.yml` | Porta, volumes e acesso ao serviço da Apple |
| `panel/server.py` | Servidor HTTP, tarefas em PTY, contas, aparelhos, contas principais e barra do topo (`/api/topbar`, `/api/defaults/set`), status do PC (`/api/pc/status`), perfil do tipo de projeto do build de PC (`/api/pc/profile`), conexão das contas Steam (`/api/steam/check`), visão geral e configuração dos projetos (`/api/project/overview`, `/api/project/settings`), as ações `init.android` e `multi` e rotas |
| `panel/release.py` | Pipeline de publicação na App Store, executado como tarefa; com `ipaFile` envia um `.ipa` de release pronto, sem compilar |
| `panel/android.py` | Build Android (Gradle), chaves de upload, instalação por adb e envio ao Google Play; com `existing` envia um `.aab` ou `.apk` de release pronto, sem compilar |
| `panel/play.py` | Cliente da Google Play Developer API |
| `panel/pc.py` | Build Electron para PC (Windows, Linux e macOS): copia o site, gera o app e zipa |
| `panel/steam.py` | Arquivos `.vdf` do SteamPipe e chamadas ao steamcmd (login e envio); com `fromZips` envia zips de PC já prontos, sem recompilar |
| `panel/versions.py` | Lê a versão do app de cada origem do projeto |
| `panel/asc.py` | Cliente da API do App Store Connect |
| `panel/github.py` | Contas e repositórios do GitHub |
| `panel/ai.py` | Provedores de IA e geração do "O que há de novo" |
| `panel/store.py` | Configurações e segredos salvos, inclusive as contas principais (`defaults.json`, sem segredos) |
| `panel/static/` | Interface (`index.html`) e logo |
| `panel/static/devices.js` | Telas de Dispositivos: iPhone, Android (adb) e PC (status do Windows, serviço Apple, steamcmd, Node, cache do Electron e builds de PC) |
| `panel/builds.py` | Plataformas de cada projeto (iOS, Android e PC), lista de builds e script de `init` do Android (`npx cap add android`) |
| `panel/static/projects.js` | Projetos: diálogos **⚙ Configurar** e **🔨 Build** |
| `panel/static/deliver.js` | Projetos: diálogo **📤 Enviar para a loja** (só builds release já prontos) |

## Dados e volumes

| Volume | Caminho | Conteúdo |
|---|---|---|
| `xtool-home` | `/root` | Logins Apple, chaves das APIs e contas do Google Play (`.config/xtool-panel/secrets.json`), chaves de upload do Android (`.config/xtool-panel/android-keys/`), certificados de distribuição, contas do GitHub, SDK do iOS, versões do xtool baixadas pelo painel (`.xtool/`), contas e apps Steam (`.config/xtool-panel/steam_accounts.json` e `steam_apps.json`, sem senhas), contas principais Steam e Google Play (`.config/xtool-panel/defaults.json`, sem segredos), login do steamcmd (`/root/Steam`) e cache do Electron (`/root/.cache/electron`) |
| `xtool-work` | `/work` | Projetos (os builds ficam em `<projeto>/xtool/`, os do Android em `<projeto>/xtool/android/`, os de PC em `<projeto>/xtool/pc/` e a pasta da Steam em `<projeto>/xtool/steam/`) |
| Downloads do Windows | `/downloads` | `Xcode.xip`, `.ipa` e `.apk` |

> **Backup:** o volume `xtool-home` guarda os seus certificados e as chaves de upload do Android. Perder a chave de upload impede de atualizar o app na Google Play: baixe o backup de cada uma pelo painel e guarde fora do container.

## Segurança

- O painel **não tem login** e executa comandos no container. Por isso ele só escuta em `127.0.0.1`. **Não exponha a porta 8080 na rede.**
- As chaves de API e os JSON das contas de serviço do Google Play ficam em `secrets.json`, com permissão `600`, e nunca voltam completos para o navegador.
- As chaves de upload do Android ficam em `android-keys/`. As senhas delas (geradas pelo painel, ou as que você informou ao importar) ficam no `secrets.json` e não voltam para o navegador.
- As senhas Apple vão direto para o xtool pelo console. O painel não as grava.
- A senha da Steam nunca é gravada pelo painel: é digitada no console, direto no steamcmd.
- O login Apple por senha usa APIs privadas da Apple. Para contas importantes, prefira o modo **API Key**.

## Limitações conhecidas

- **Ícone para a App Store:** o `Assets.car` é gerado pelo accord, um projeto novo. Ainda não houve um envio de verdade que comprove que a Apple aceita esse arquivo. Se a validação recusar o ícone, a mensagem da Apple aparece no console.
- **Primeira versão:** as capturas de tela e os metadados obrigatórios precisam ser preenchidos no site do App Store Connect.
- **Recursos avançados:** extensões (widgets), App Groups e outras capacidades especiais podem exigir perfis com permissões extras.
- **USB direto:** o Docker Desktop não repassa USB. Use o serviço da Apple (recomendado) ou o usbipd. No Android, use o adb por Wi-Fi.
- **Apps novos na Google Play:** a API do Google não cria apps nem preenche a ficha da loja. Crie o app e envie a primeira versão pelo Play Console; depois o painel cuida das atualizações.
- **Lista de apps do Google Play:** a API não lista os apps da conta, então cada app é adicionado pelo package name.
- **macOS no PC:** o app sai sem assinatura nem notarização e sem ícone `.icns`, então o Gatekeeper pede liberação manual. Na Steam, o macOS exige essa assinatura para rodar bem.
- **Ícone e metadados do `.exe`:** precisam do Wine, que não vem por padrão (`INSTALL_WINE=1`). Sem ele, o `.exe` sai sem ícone e sem metadados; só o ícone da janela é aplicado.
- **App de PC sem Steamworks:** o app Electron é só uma janela que abre o site. Não inclui o Steamworks SDK, conquistas nem overlay.
- **Apps novos na Steam:** precisam de Depots e da página da loja aprovada no Steamworks. O envio para a Steam ainda não foi testado numa conta real.

## Solução de problemas

| Sintoma | Solução |
|---|---|
| "Conexão iPhone: desligado" | Abra o iTunes ou o Dispositivos Apple no Windows |
| iPhone não aparece | Desbloqueie a tela, toque em **Confiar** e confira o Modo de Desenvolvedor |
| `chave da API … não configurada` | Cadastre a chave no cartão da conta em **Contas** → Apple |
| "não existe app no App Store Connect" | Crie o app com o mesmo bundle ID no site da Apple |
| "máximo de certificados de distribuição" | Revogue um certificado antigo em developer.apple.com → Certificates |
| "Google recusou a chave da conta de serviço" | Gere uma chave JSON nova da conta de serviço e envie de novo em **Contas** → Google Play |
| `Google Play 403` / "permission" | Convide o e-mail da conta de serviço no Play Console com permissão para lançar versões e ative a Google Play Android Developer API |
| `Google Play 404` / "package not found" | O app ainda não existe no Play Console, ou o package name está diferente |
| A Play recusa o `versionCode` | Deixe o código em **auto**: o painel usa o próximo depois do maior que já está na Play |
| Celular Android não aparece | Pareie de novo (o código muda a cada vez), confira a mesma rede e clique em **Conectar** com a porta de conexão, que é diferente da de pareamento |
| A IA não conecta (Ollama/LM Studio) | Abra o app no Windows e confira se o servidor local está ligado |
| `no configuration file provided` | Rode o `docker compose` dentro da pasta do repositório |
| O `.exe` está com o ícone padrão do Electron | Coloque um PNG de 512x512 em `resources/icon.png` do projeto e gere o build de PC de novo. Se o `.exe` continuar sem o ícone, reconstrua a imagem com `INSTALL_WINE=1 docker compose up -d --build` (o Wine não vem por padrão) e confira no console se o Wine está instalado |
| Erro do tipo de projeto antes do build | Leia o aviso ou o erro embaixo do seletor **Tipo de código** e ajuste o tipo, o comando ou a pasta do site |
| "📤 Enviar para a loja" está travado | Falta um build release: gere um em **🔨 Build** com o modo **Release** |
| "Android não configurado" | O projeto não tem Capacitor ou falta rodar **⚙ Configurar**. Sem Capacitor, instale-o (veja [Projetos: configurar, compilar e enviar](#projetos-configurar-compilar-e-enviar)); com ele, clique em **Adicionar Android** no **⚙ Configurar** |
| "Pull automático em espera" ou "divergente" no card | Há alterações locais ou commits locais: resolva no Terminal (`git status`) |
| Pull parado em "baixando atualizações…" | Repositórios grandes podem levar até 15 minutos; a barra mostra a fase e a velocidade. Se cancelar, os restos do download são apagados sozinhos |
| Não consigo criar um projeto novo | Cadastre uma conta do GitHub (menu **GitHub**) e confira se o nome do projeto ou do repositório já existe (em `/work` ou no GitHub) |
| `o steamcmd não está instalado` | Reconstrua a imagem com `docker compose up -d --build`, porque o steamcmd vem na imagem |
| "Steam Guard" ou senha pedida | Digite a senha ou o código no console. Se for preciso, rode **Login** de novo na conta Steam |
| "Conta Steam: Sem login" | Clique em **Login**, digite a senha e o Steam Guard no console e espere a pill virar **Conectada** (ou clique em **↻ Verificar**) |
| "Conta Steam: Ocupado…" | Há uma tarefa do steamcmd rodando; espere terminar |
| "Android desconectado no topo" | Pareie ou conecte o celular por Wi-Fi (adb, veja [Rodar no celular Android](#rodar-no-celular-android)) e clique em **Atualizar** |
| "PC desconectado no topo" | O Docker Desktop precisa estar rodando no Windows. O nome `host.docker.internal` não existe em Linux sem configuração extra |

## Atualização

**xtool:** a versão **base** (1.24.0) vem do repositório, em `base/`, e é instalada no build da imagem sem acessar o GitHub do xtool. Com internet, o painel consulta a cada hora os [Releases do xtool](https://github.com/xtool-org/xtool/releases). Quando sai uma versão nova, o card **xtool** mostra **⬆ Atualizar**. A versão baixada aparece como **xtool-org**, fica em `/root/.xtool`, no volume, e continua valendo depois de reiniciar o container. Sem internet, o painel segue com a versão base.

**Painel inteiro** (imagem, ferramentas e interface):

```bash
git pull
docker compose up -d --build
```

As versões ficam fixas no `Dockerfile` (`XTOOL_VERSION`, `RCODESIGN_VERSION`, `ACCORD_VERSION`, `NODE_VERSION`, `ANDROID_PLATFORM`, `ANDROID_BUILD_TOOLS`, `INSTALL_WINE`). A imagem agora também fixa o `STEAMCMD_URL`, um `ARG` do Dockerfile. A imagem padrão tem cerca de 8 GB e inclui ImageMagick. O Wine não vem por padrão: para o ícone e os metadados do `.exe`, reconstrua com `INSTALL_WINE=1 docker compose up -d --build` (no PowerShell: `$env:INSTALL_WINE=1; docker compose up -d --build`, ou escreva `INSTALL_WINE=1` num arquivo `.env` ao lado do `docker-compose.yml`). O Wine adiciona cerca de 3,9 GB (a imagem vai a cerca de 11,8 GB) e o primeiro build com Wine demora alguns minutos a mais.

A página é servida com `Cache-Control: no-cache`: depois de atualizar a imagem, basta recarregar a aba do navegador.

## Changelog

### 1.2.0

- Menu Contas único, com abas Apple, Google Play e Steam
- Ícones oficiais das plataformas no lugar dos emojis
- **Compilar para PC:** projetos web e Capacitor viram app com Electron para Windows, Linux e macOS (x64), com opção de gerar .zip
- **Contas e apps Steam:** cadastro de contas de build (sem gravar a senha) e login pelo console do steamcmd
- Contas Steam mostram se estão conectadas (verificação com o login salvo do steamcmd) e o seletor do topo mostra 🟢/⚪
- Barra do topo com conta Steam e conta Google Play principais, e indicadores de Android e PC conectados
- Dispositivos em abas: 📱 iPhone (iOS), 🤖 Android (adb por Wi-Fi) e 🖥️ PC (status do Windows, serviço Apple, steamcmd e cache do Electron)
- Etiquetas em Projetos: 🍎 iOS, 🤖 Android, 🖥️ PC e 🎮 Steam
- Página servida sem cache (`no-cache`): depois de atualizar a imagem, basta recarregar a aba
- Apps da Steam em Apps da conta → Steam (como Apple e Google Play); Contas Steam só com contas
- **Publicar na Steam:** arquivos do SteamPipe (.vdf) e envio pelo steamcmd, com branch e registro da última publicação
- Descrição do build com IA, a partir dos commits
- steamcmd instalado na imagem Docker
- App de PC abre o site por `app://` (caminhos absolutos funcionam)
- Ícone da janela do app de PC; ícone e metadados do `.exe` com Wine opcional (`INSTALL_WINE=1`)
- Tipo de código no build de PC, com verificações antes do build: 7 tipos: Automático, TypeScript, JavaScript com build, JavaScript / HTML puro, Capacitor, frameworks estáticos (Next.js, Nuxt, SvelteKit, Astro) e Personalizado
- **Projetos:** ⚙ Configurar mostra o que falta em cada plataforma (iOS, Android e PC) e adiciona o Android ao Capacitor; 🔨 Build compila as plataformas marcadas numa única tarefa
- **Enviar para a loja:** envia um build release pronto (iOS, Android ou PC), sem recompilar, com conferência de versão e build
- Card do projeto mostra o último commit (código e número) e faz pull automático (só fast-forward com árvore limpa); botão push removido
- Barra de progresso do pull automático e fetch de até 15 minutos (sem deixar restos de download)
- Novo projeto exige um repositório do GitHub (criado automaticamente na conta escolhida)

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

**xtool Painel 1.2.0** · By [marco3079](https://github.com/marco3079)

</div>
