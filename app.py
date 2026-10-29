import json
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from groq import Groq

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
CORS(app, origins=[os.getenv("FRONTEND_ORIGIN", "*")])

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


@app.get("/health")
def health():
    return jsonify(status="ok", edicoes_na_base=len(FATOS.get("edicoes", [])))


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    mensagem = (data.get("mensagem") or "").strip()

    if not mensagem:
        return jsonify(erro="Mensagem vazia."), 400
    if len(mensagem) > MAX_CARACTERES:
        return jsonify(erro=f"Mensagem muito longa (máx. {MAX_CARACTERES} caracteres)."), 400

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
        return jsonify(erro=str(erro)), 500
    except Exception as erro:
        # Registra o tipo e a mensagem do erro nos logs do servidor (sem expor a chave).
        app.logger.error("Falha na chamada à Groq (modelo=%s): %s: %s", MODEL, type(erro).__name__, erro)
        return jsonify(erro="Falha ao consultar o modelo. Tente novamente."), 502

    conteudo = resposta.choices[0].message.content or ""

    # Registra perguntas recusadas nos logs, para orientar a expansão da base.
    if conteudo.strip().startswith(RECUSA):
        app.logger.info("PERGUNTA_RECUSADA: %s", mensagem)

    return jsonify(resposta=conteudo)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
