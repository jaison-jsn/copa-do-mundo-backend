"""Roda o conjunto de perguntas de avaliação contra o backend e mostra o resultado.

Uso:
    uv run python tests/avaliar.py                       # usa o backend local
    uv run python tests/avaliar.py https://copa-do-mundo-backend.onrender.com
"""

import json
import sys
import unicodedata
from pathlib import Path

import requests

RECUSA = "Não possuo informações sobre este tema"
CAMINHO = Path(__file__).parent / "perguntas_avaliacao.json"


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparar palavras sem falsos negativos."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def avaliar_item(item: dict, resposta: str) -> tuple[bool, str]:
    if item.get("deve_recusar"):
        if RECUSA in resposta:
            return True, "recusou corretamente"
        return False, "deveria recusar e respondeu"

    if RECUSA in resposta:
        return False, "recusou um tema dentro do escopo"

    faltando = [p for p in item.get("deve_conter", []) if normalizar(p) not in normalizar(resposta)]
    if faltando:
        return False, f"faltou: {', '.join(faltando)}"
    return True, "contém os termos esperados"


def main() -> int:
    base_url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")
    itens = json.loads(CAMINHO.read_text(encoding="utf-8"))["perguntas"]

    aprovadas = 0
    for item in itens:
        try:
            r = requests.post(f"{base_url}/api/chat", json={"mensagem": item["pergunta"]}, timeout=90)
            dados = r.json()
            resposta = dados.get("resposta", "")
            if not resposta:
                ok, motivo = False, f"erro HTTP {r.status_code}: {dados.get('erro', 'sem detalhe')}"
            else:
                ok, motivo = avaliar_item(item, resposta)
        except requests.RequestException as erro:
            ok, motivo = False, f"falha de conexão: {erro}"

        aprovadas += ok
        marca = "OK  " if ok else "FALHA"
        print(f"[{marca}] {item['pergunta']} -> {motivo}")

    total = len(itens)
    print(f"\nResultado: {aprovadas}/{total} aprovadas ({aprovadas / total:.0%}).")
    return 0 if aprovadas == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
