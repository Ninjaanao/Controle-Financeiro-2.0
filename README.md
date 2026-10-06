# Controle Financeiro

Aplicacao web simples para registrar receitas, despesas, categorias, usuarios e gerar relatorios financeiros.

## Tecnologias

- FastAPI
- SQLite para uso local
- PostgreSQL opcional em producao
- Frontend HTML, CSS e JavaScript puro

## Como rodar localmente

```bash
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Depois acesse:

```text
http://127.0.0.1:8000
```

Usuario inicial padrao:

```text
usuario: admin
senha: admin123
```

Altere essa senha antes de usar em producao.

## Variaveis de ambiente recomendadas

```text
SECRET_KEY=uma-chave-grande-e-secreta
INIT_ADMIN_USER=admin
INIT_ADMIN_PASSWORD=uma-senha-forte
DATABASE_URL=postgresql://usuario:senha@host:porta/banco
CORS_ORIGINS=https://seu-dominio.com
```

Se `DATABASE_URL` nao for definida, a aplicacao usa SQLite em `DB_PATH`.

## Publicacao barata

Como este projeto tem backend e banco, as opcoes mais praticas sao:

- Railway: recomendado para este projeto por unir app FastAPI e PostgreSQL no mesmo painel.
- Fly.io: boa opcao tecnica, mas exige mais configuracao.
- Koyeb: alternativa interessante, mas a camada gratuita de banco tem limite forte de horas.

GitHub Pages, Netlify e Vercel gratuitos sao otimos para sites estaticos, mas este projeto precisa de API e banco para login e persistencia.

Veja o passo a passo em `DEPLOY_RAILWAY.md`.
