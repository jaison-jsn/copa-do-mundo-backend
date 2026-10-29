# Mister Copa: backend

API do chatbot especialista em Copas do Mundo de futebol. Usa Flask para o servidor e a API da Groq para as respostas. O frontend fica em um repositório separado: `copa-do-mundo-frontend`.

## Estrutura

- `app.py`: rotas `/health` e `/api/chat`
- `prompts/system_prompt.txt`: instruções do assistente, incluindo a regra de recusa
- `data/copa_fatos.json`: base de fatos sobre as edições da Copa, de 1930 a 2026
- `.env.example`: modelo das variáveis de ambiente

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GROQ_API_KEY` | Sim | Chave da API da Groq. Nunca versionar. |
| `GROQ_MODEL` | Não | Modelo usado. Padrão: `openai/gpt-oss-120b`. |
| `FRONTEND_ORIGIN` | Sim, em produção | Origem do frontend, só protocolo e domínio, sem caminho. Exemplo: `https://jaison-jsn.github.io` |

## Execução local

Pré-requisito: [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env        # depois edite o .env com sua chave
uv sync
uv run python app.py
```

O servidor sobe em `http://127.0.0.1:5000`. Para testar:

```bash
curl http://127.0.0.1:5000/health
```

## Endpoints

- `GET /health`: retorna o status e a quantidade de edições na base.
- `POST /api/chat`: recebe `{"mensagem": "..."}` e retorna `{"resposta": "..."}`. A mensagem tem no máximo 500 caracteres.

## Deploy no Render

| Campo | Valor |
|---|---|
| Tipo | Web Service |
| Runtime | Python |
| Build Command | `pip install uv && uv sync --frozen` |
| Start Command | `uv run gunicorn app:app --bind 0.0.0.0:$PORT` |
| Variáveis | `GROQ_API_KEY`, `GROQ_MODEL`, `FRONTEND_ORIGIN` |

Cada push na branch `main` dispara um novo deploy automaticamente.

## Observações

- No plano gratuito, o serviço hiberna após um período sem uso. A primeira requisição pode demorar cerca de 50 segundos.
- A resposta do modelo depende da base de fatos. Dados ausentes da base devem ser tratados como "não confirmado", e não preenchidos por suposição.

## Variáveis opcionais

| Variável | Padrão | Para que serve |
|---|---|---|
| `PAINEL_TOKEN` | vazio | Liga o painel de uso em `/api/uso`. Sem ela, a rota responde 404. |
| `LIMITE_CHAT` | `20 per minute` | Limite de perguntas por IP em `/api/chat`. |
| `LIMITE_ATIVO` | `1` | Use `0` para desligar o limite. |
| `FLASK_DEBUG` | `0` | Use `1` só em desenvolvimento local. |

## Validar a base

```bash
uv run python scripts/validar_base.py
```

O mesmo script e os testes rodam no GitHub Actions a cada push (`.github/workflows/testes.yml`).
