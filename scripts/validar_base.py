"""Valida data/copa_fatos.json antes do deploy (item 12).

Sai com código 1 se encontrar erro. Uso: uv run python scripts/validar_base.py
"""

import json
import sys
from pathlib import Path

CAMINHO = Path(__file__).parent.parent / "data" / "copa_fatos.json"

# Seleções que mudaram de nome: a base usa os dois nomes para o mesmo país.
MESMO_PAIS = {"Alemanha Ocidental": "Alemanha"}


def normalizar(nome):
    return MESMO_PAIS.get(nome, nome)


def validar(dados):
    erros = []
    edicoes = dados.get("edicoes", [])
    anos = [e.get("ano") for e in edicoes]

    if len(anos) != len(set(anos)):
        erros.append("há anos repetidos em edicoes")
    for e in edicoes:
        ano = e.get("ano")
        for campo in ("ano", "sede", "campeao", "vice", "placar_final", "fonte", "link"):
            if not e.get(campo):
                erros.append(f"edição {ano}: campo '{campo}' vazio ou ausente")
        if e.get("campeao") and e.get("campeao") == e.get("vice"):
            erros.append(f"edição {ano}: campeão e vice são o mesmo país")
        if e.get("link") and not str(e["link"]).startswith("https://"):
            erros.append(f"edição {ano}: link não começa com https://")

    anos_set = set(anos)
    for j in dados.get("jogadores", []):
        if j.get("ano") not in anos_set:
            erros.append(f"jogadores: ano {j.get('ano')} não existe em edicoes")
        if not j.get("fonte"):
            erros.append(f"jogadores {j.get('ano')}: sem fonte")

    selecoes = dados.get("selecoes", [])
    nomes = [s.get("selecao") for s in selecoes]
    if len(nomes) != len(set(nomes)):
        erros.append("há seleções repetidas em selecoes")
    for s in selecoes:
        nome = s.get("selecao")
        if not s.get("fonte"):
            erros.append(f"seleção {nome}: sem fonte")
        for campo in ("titulos", "vices", "terceiros", "quartos"):
            for ano in s.get(campo, []):
                if ano not in anos_set:
                    erros.append(f"seleção {nome}: {campo} inclui {ano}, que não existe em edicoes")

    # Títulos da seleção devem bater com as edições em que ela aparece como campeã.
    campeoes_por_ano = {}
    for e in edicoes:
        campeoes_por_ano.setdefault(normalizar(e.get("campeao", "")), set()).add(e["ano"])
    for s in selecoes:
        nome = normalizar(s.get("selecao", ""))
        titulos_base = set(s.get("titulos", []))
        titulos_edicoes = campeoes_por_ano.get(nome, set())
        if titulos_base != titulos_edicoes:
            erros.append(
                f"seleção {s.get('selecao')}: títulos {sorted(titulos_base)} "
                f"não batem com as edições {sorted(titulos_edicoes)}"
            )
    return erros


def main():
    dados = json.loads(CAMINHO.read_text(encoding="utf-8"))
    erros = validar(dados)
    if erros:
        print(f"Base inválida: {len(erros)} problema(s).")
        for erro in erros:
            print(" -", erro)
        return 1
    print(f"Base válida: {len(dados.get('edicoes', []))} edições, {len(dados.get('selecoes', []))} seleções.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
