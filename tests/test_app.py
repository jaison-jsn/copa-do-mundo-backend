"""Testes locais das rotas. Não chamam a API da Groq."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as app_module  # noqa: E402


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(app_module, "_client", None)
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        yield c


def test_health_retorna_ok_e_edicoes(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"
    assert r.get_json()["edicoes_na_base"] == 23


def test_mensagem_vazia_retorna_400(cliente):
    r = cliente.post("/api/chat", json={"mensagem": "   "})
    assert r.status_code == 400


def test_mensagem_acima_do_limite_retorna_400(cliente):
    r = cliente.post("/api/chat", json={"mensagem": "a" * 501})
    assert r.status_code == 400


def test_mensagem_no_limite_passa_da_validacao(cliente):
    # Sem chave configurada, a mensagem passa da validação e falha só ao chamar a Groq.
    r = cliente.post("/api/chat", json={"mensagem": "a" * 500})
    assert r.status_code == 500
    assert "GROQ_API_KEY" in r.get_json()["erro"]


def test_sem_chave_retorna_500_com_mensagem_clara(cliente):
    r = cliente.post("/api/chat", json={"mensagem": "Quem foi campeão em 1994?"})
    assert r.status_code == 500
    assert "GROQ_API_KEY" in r.get_json()["erro"]


def test_base_de_fatos_tem_jogadores_para_cada_edicao():
    jogadores = app_module.FATOS["jogadores"]
    anos_edicoes = {e["ano"] for e in app_module.FATOS["edicoes"]}
    anos_jogadores = {j["ano"] for j in jogadores}
    assert anos_edicoes == anos_jogadores


def test_romario_consta_como_bola_de_ouro_de_1994():
    entrada = next(j for j in app_module.FATOS["jogadores"] if j["ano"] == 1994)
    assert entrada["bola_de_ouro"] == "Romário (Brasil)"


def test_prompt_inclui_regra_de_jogadores():
    assert "JOGADORES, TÉCNICOS E SELEÇÕES" in app_module.SYSTEM_PROMPT


def test_arquivo_de_avaliacao_tem_perguntas_validas():
    import json

    caminho = Path(__file__).parent / "perguntas_avaliacao.json"
    perguntas = json.loads(caminho.read_text(encoding="utf-8"))["perguntas"]
    assert len(perguntas) >= 30
    for item in perguntas:
        assert ("deve_conter" in item) != ("deve_recusar" in item), item["pergunta"]


def test_prompt_exige_linha_de_fonte():
    assert 'linha começando por "Fonte:"' in app_module.SYSTEM_PROMPT


def test_todos_os_registros_tem_fonte():
    for e in app_module.FATOS["edicoes"]:
        assert e.get("fonte"), f"edição {e['ano']} sem fonte"
    for s in app_module.FATOS["selecoes"]:
        assert s.get("fonte"), f"seleção {s['selecao']} sem fonte"
