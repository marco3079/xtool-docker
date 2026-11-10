# Política de segurança

## Versões com suporte

Só a versão mais recente do **xtool Painel** (a da `main`) recebe correções de segurança.

## Modelo de uso

O painel foi feito para rodar **na sua própria máquina**:

- Ele **não tem login** e executa comandos dentro do container. Por isso a porta 8080 só escuta em `127.0.0.1`.
- Chaves de API e JSON de contas de serviço ficam em `secrets.json` (permissão `600`) e nunca voltam completos para o navegador.
- Senhas da Apple e da Steam são digitadas no console, direto no xtool ou no steamcmd, e o painel não as grava.

> [!WARNING]
> Não exponha a porta 8080 na rede nem na internet (port forwarding, túnel, proxy reverso sem autenticação). Quem acessar o painel controla o container e as contas cadastradas nele.

## Como relatar uma vulnerabilidade

**Não abra uma issue pública.** Use o relato privado do GitHub:

1. Abra a aba **Security** do repositório.
2. Clique em **Report a vulnerability** (Security Advisories).
3. Descreva o problema, a versão do painel (rodapé da barra lateral), os passos para reproduzir e o impacto.

A resposta vem assim que possível. Depois da correção, o advisory pode ser publicado com os créditos para quem relatou, se você quiser.

## Fora do escopo

- Problemas que exigem expor a porta 8080 na rede, contrariando as instruções acima.
- Falhas no xtool (`base/`), no steamcmd, no Android SDK ou nas APIs da Apple, do Google e da Valve: relate ao projeto de origem.
