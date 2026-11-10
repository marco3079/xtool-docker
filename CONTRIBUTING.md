# Como contribuir

Obrigado pelo interesse no **xtool Painel**. Este guia resume como propor mudanças sem atrapalhar a `main`.

## Antes de começar

1. Abra uma [issue](../../issues) descrevendo o problema ou a mudança: o que acontece, o que deveria acontecer e como reproduzir.
2. Espere um retorno antes de mudanças grandes (novas telas, rotas ou integrações com lojas).

## Branches e pull requests

- Só o dono do repositório faz commit, push ou merge na `main`.
- Trabalhe numa branch com o seu login na frente: `<seu-login>/<nome>` (ex.: `WasDevFullStack/nova-tela`).
- Abra um pull request da sua branch para a `main`, com a descrição do que mudou e de como testar.

> [!IMPORTANT]
> A Action [Guarda das branches](.github/workflows/guarda-branches.yml) confere cada push. Se alguém que não é o dono mexer na `main` ou numa branch que não é a dele, o push é desfeito na hora. Os commits não se perdem: ficam numa branch `bloqueado/<login>-<commit>`, e uma issue avisa o que aconteceu.

## Padrões

- **Commits em português**, com uma linha de resumo clara (ex.: `Painel 1.5.1: corrige X em Gerenciar lojas`).
- **Painel:** Python só com a biblioteca padrão em `panel/*.py` e JavaScript clássico (sem build) em `panel/static/`.
- **Documentação:** se a mudança afetar o uso, atualize o [README](README.md) (e o [README.en.md](README.en.md) quando possível) e acrescente uma entrada no **Changelog**.
- **Versão:** mudanças visíveis sobem o `VERSION` em `panel/server.py` e a versão citada no README.
- **Segredos:** nunca inclua chaves, JSON de contas de serviço, keystores, senhas ou prints com dados pessoais.

## Testar

Teste a mudança no container antes de abrir o pull request:

```bash
docker compose up -d --build
```

Depois abra `http://localhost:8080` e confira a tela que você alterou. Para mudanças em JavaScript, `node --check panel/static/<arquivo>.js` pega erros de sintaxe.

## Segurança

Falhas de segurança não devem ir para issues públicas. Veja [SECURITY.md](SECURITY.md).
