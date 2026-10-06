# Deploy no Railway

Este projeto pode ser publicado no Railway com um servico web FastAPI e um banco PostgreSQL.

## 1. Subir o codigo para o GitHub

Crie um repositorio no GitHub e envie estes arquivos do projeto.

Nao suba o banco local `financeiro-local.db`. Ele esta ignorado no `.gitignore`.

## 2. Criar o projeto no Railway

1. Acesse https://railway.com
2. Crie uma conta ou entre com GitHub.
3. Clique em **New Project**.
4. Escolha **Deploy from GitHub repo**.
5. Selecione o repositorio deste projeto.

O Railway deve detectar o projeto Python e usar o `Procfile`:

```text
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

## 3. Adicionar PostgreSQL

Dentro do projeto no Railway:

1. Clique em **New**.
2. Escolha **Database**.
3. Escolha **PostgreSQL**.

Depois disso, conecte o banco ao servico web. O Railway deve disponibilizar a variavel `DATABASE_URL`.

## 4. Configurar variaveis de ambiente

No servico web, abra **Variables** e configure:

```text
SECRET_KEY=gere-uma-chave-grande-e-secreta
INIT_ADMIN_USER=admin
INIT_ADMIN_PASSWORD=troque-por-uma-senha-forte
CORS_ORIGINS=*
```

Para gerar uma chave localmente:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 5. Fazer o deploy

Depois de configurar as variaveis, rode um novo deploy no Railway.

Ao abrir a URL publica, use:

```text
Usuario: valor de INIT_ADMIN_USER
Senha: valor de INIT_ADMIN_PASSWORD
```

## Observacoes importantes

- O primeiro usuario admin so e criado automaticamente quando o banco ainda esta vazio.
- Depois do primeiro deploy, se voce trocar `INIT_ADMIN_PASSWORD`, a senha do usuario ja criado nao muda automaticamente.
- Para producao real, use uma senha forte e nao deixe `SECRET_KEY` com valor padrao.
