import hmac
import json
import os
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from groq import Groq
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

BASE = Path(__file__).parent
SYSTEM_PROMPT = (BASE / "prompts" / "system_prompt.txt").read_text(encoding="utf-8")
FATOS = json.loads((BASE / "data" / "copa_fatos.json").read_text(encoding="utf-8"))

RECUSA = (
    "Não possuo informações sobre este tema. "
    "Posso ajudar com dados e fatos sobre as Copas do Mundo de Futebol."
)
MAX_CARACTERES = 500

app = Flask(__name__)
# Atrás do proxy do Render, o IP real do cliente vem no cabeçalho X-Forwarded-For.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
CORS(app, origins=[os.getenv("FRONTEND_ORIGIN", "*")])

# Limite de perguntas por IP (item 9). Pode ser ajustado ou desligado por variável de ambiente.
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
    enabled=os.getenv("LIMITE_ATIVO", "1") == "1",
)
LIMITE_CHAT = os.getenv("LIMITE_CHAT", "20 per minute")

# Cache de respostas (item 10): perguntas repetidas não chamam a Groq de novo.
_CACHE_MAX = 200
_cache = OrderedDict()
_cache_lock = threading.Lock()


def _chave_cache(mensagem):
    return " ".join(mensagem.lower().split())

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
_client = None


def get_client():
    """Cria o cliente Groq sob demanda, para o servidor subir mesmo sem a chave."""
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY não configurada.")
        _client = Groq(api_key=api_key)
    return _client


# ----- Painel de uso (item 38) -----
# Guarda apenas contagens: por dia (total, recusadas, erros) e por tema.
# O texto das perguntas não é armazenado. Os contadores ficam na memória
# e zeram quando o servidor reinicia.
_uso_lock = threading.Lock()
_uso_dias = {}
_uso_temas = {}
_TEMAS = [
    ("sedes", ("sede", "sediou", "onde foi", "país sede", "pais sede")),
    ("bola_de_ouro", ("bola de ouro",)),
    ("artilheiros", ("artilheiro", "goleador", "mais gols", "gols")),
    ("campeoes", ("campeão", "campeao", "campeã", "campea", "venceu", "ganhou", "título", "titulo", "final")),
    ("selecoes", ("seleção", "selecao", "seleções", "selecoes", "time ")),
    ("jogadores", ("jogador", "quem é", "quem foi", "craque")),
]


def classificar_tema(mensagem):
    """Escolhe um tema pela primeira palavra-chave encontrada. Sem palavra: 'outros'."""
    texto = " " + mensagem.lower() + " "
    for tema, palavras in _TEMAS:
        if any(p in texto for p in palavras):
            return tema
    return "outros"


def registrar_uso(mensagem, desfecho):
    """desfecho: 'respondida', 'recusada' ou 'erro'."""
    dia = datetime.now(timezone.utc).date().isoformat()
    with _uso_lock:
        contagem = _uso_dias.setdefault(dia, {"perguntas": 0, "respondidas": 0, "recusadas": 0, "erros": 0})
        contagem["perguntas"] += 1
        chave = {"respondida": "respondidas", "recusada": "recusadas", "erro": "erros"}[desfecho]
        contagem[chave] += 1
        tema = classificar_tema(mensagem)
        _uso_temas[tema] = _uso_temas.get(tema, 0) + 1


@app.get("/api/uso")
def painel_uso():
    """Resumo de uso. Exige o token em PAINEL_TOKEN, enviado no cabeçalho X-Painel-Token."""
    token_esperado = os.getenv("PAINEL_TOKEN", "")
    if not token_esperado:
        return jsonify(erro="Painel desativado."), 404
    token_recebido = request.headers.get("X-Painel-Token", "")
    if not hmac.compare_digest(token_recebido, token_esperado):
        return jsonify(erro="Token inválido."), 401

    with _uso_lock:
        dias = [{"data": d, **c} for d, c in sorted(_uso_dias.items())][-30:]
        temas = sorted(_uso_temas.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(d["perguntas"] for d in dias)
    recusadas = sum(d["recusadas"] for d in dias)
    return jsonify(
        dias=dias,
        total_perguntas=total,
        taxa_recusa=round(recusadas / total, 3) if total else 0,
        temas=[{"tema": t, "perguntas": n} for t, n in temas],
        observacao="Contadores em memória: zeram quando o servidor reinicia.",
    )


@app.get("/health")
def health():
    return jsonify(status="ok", edicoes_na_base=len(FATOS.get("edicoes", [])))


def _edicao_completa(edicao):
    """Junta os dados da edição com artilheiro e Bola de Ouro, quando existirem."""
    jogadores = {j["ano"]: j for j in FATOS.get("jogadores", [])}
    j = jogadores.get(edicao["ano"], {})
    return {
        **edicao,
        "artilheiro": j.get("artilheiro"),
        "gols_artilheiro": j.get("gols"),
        "bola_de_ouro": j.get("bola_de_ouro"),
        "obs_artilheiro": j.get("obs"),
    }


@app.get("/api/edicoes")
def listar_edicoes():
    return jsonify(edicoes=[_edicao_completa(e) for e in FATOS.get("edicoes", [])])


@app.get("/api/edicoes/<int:ano>")
def detalhe_edicao(ano):
    for e in FATOS.get("edicoes", []):
        if e["ano"] == ano:
            return jsonify(_edicao_completa(e))
    return jsonify(erro=f"Edição de {ano} não encontrada na base."), 404


@app.get("/api/selecoes")
def listar_selecoes():
    return jsonify(selecoes=FATOS.get("selecoes", []))


@app.get("/api/selecoes/<path:nome>")
def detalhe_selecao(nome):
    alvo = nome.strip().lower()
    for s in FATOS.get("selecoes", []):
        if s["selecao"].lower() == alvo:
            return jsonify(s)
    return jsonify(erro=f"Seleção '{nome}' não encontrada na base."), 404


@app.errorhandler(429)
def limite_excedido(_erro):
    return jsonify(erro="Muitas perguntas em pouco tempo. Aguarde um minuto e tente novamente."), 429


@app.post("/api/chat")
@limiter.limit(LIMITE_CHAT)
def chat():
    data = request.get_json(silent=True) or {}
    mensagem = (data.get("mensagem") or "").strip()

    if not mensagem:
        return jsonify(erro="Mensagem vazia."), 400
    if len(mensagem) > MAX_CARACTERES:
        return jsonify(erro=f"Mensagem muito longa (máx. {MAX_CARACTERES} caracteres)."), 400

    chave = _chave_cache(mensagem)
    with _cache_lock:
        if chave in _cache:
            _cache.move_to_end(chave)
            return jsonify(resposta=_cache[chave], cache=True)

    contexto = "\n\n# BASE DE FATOS\n" + json.dumps(FATOS, ensure_ascii=False)

    try:
        resposta = get_client().chat.completions.create(
            model=MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + contexto},
                {"role": "user", "content": mensagem},
            ],
        )
    except RuntimeError as erro:
        registrar_uso(mensagem, "erro")
        return jsonify(erro=str(erro)), 500
    except Exception as erro:
        # Registra o tipo e a mensagem do erro nos logs do servidor (sem expor a chave).
        app.logger.error("Falha na chamada à Groq (modelo=%s): %s: %s", MODEL, type(erro).__name__, erro)
        registrar_uso(mensagem, "erro")
        return jsonify(erro="Falha ao consultar o modelo. Tente novamente."), 502

    conteudo = resposta.choices[0].message.content or ""

    # Registra perguntas recusadas nos logs, para orientar a expansão da base.
    if conteudo.strip().startswith(RECUSA):
        app.logger.info("PERGUNTA_RECUSADA: %s", mensagem)
        registrar_uso(mensagem, "recusada")
    else:
        registrar_uso(mensagem, "respondida")

    with _cache_lock:
        _cache[chave] = conteudo
        _cache.move_to_end(chave)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)

    return jsonify(resposta=conteudo)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", port=5000)
