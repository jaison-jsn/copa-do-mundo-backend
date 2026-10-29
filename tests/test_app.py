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
    monkeypatch.setattr(app_module, "_cache", app_module.OrderedDict())
    app_module.limiter.enabled = False
    app_module.limiter.reset()
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        yield c
    app_module.limiter.enabled = False
    app_module.limiter.reset()


class _ClienteFalso:
    """Imita o cliente da Groq: conta as chamadas e devolve um texto fixo."""

    def __init__(self, texto):
        self.texto = texto
        self.chamadas = 0
        self.chat = self
        self.completions = self

    def create(self, **_kwargs):
        self.chamadas += 1
        mensagem = type("M", (), {"content": self.texto})()
        escolha = type("E", (), {"message": mensagem})()
        return type("R", (), {"choices": [escolha]})()


def _usar_cliente_falso(monkeypatch, texto):
    falso = _ClienteFalso(texto)
    monkeypatch.setattr(app_module, "get_client", lambda: falso)
    return falso


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


def test_lista_de_edicoes_traz_artilheiro_e_bola_de_ouro(cliente):
    r = cliente.get("/api/edicoes")
    assert r.status_code == 200
    edicoes = r.get_json()["edicoes"]
    assert len(edicoes) == 23
    ed1994 = next(e for e in edicoes if e["ano"] == 1994)
    assert ed1994["campeao"] == "Brasil"
    assert ed1994["bola_de_ouro"] == "Romário (Brasil)"


def test_detalhe_de_edicao_existente_e_inexistente(cliente):
    assert cliente.get("/api/edicoes/2002").get_json()["campeao"] == "Brasil"
    assert cliente.get("/api/edicoes/1999").status_code == 404


def test_lista_e_detalhe_de_selecoes(cliente):
    lista = cliente.get("/api/selecoes").get_json()["selecoes"]
    assert any(s["selecao"] == "Brasil" for s in lista)
    r = cliente.get("/api/selecoes/Brasil")
    assert r.status_code == 200
    assert r.get_json()["titulos"] == [1958, 1962, 1970, 1994, 2002]
    assert cliente.get("/api/selecoes/Atlantis").status_code == 404


def test_detalhe_de_selecao_com_barra_no_nome(cliente):
    r = cliente.get("/api/selecoes/União Soviética / Rússia")
    assert r.status_code == 200


def test_prompt_exige_linha_de_link():
    texto = Path("prompts/system_prompt.txt").read_text(encoding="utf-8")
    assert 'linha começando por "Link:"' in texto


def test_edicoes_tem_link_oficial():
    for e in app_module.FATOS["edicoes"]:
        assert e.get("link", "").startswith("https://"), f"edição {e['ano']} sem link"


def test_classificar_tema():
    assert app_module.classificar_tema("Quem foi campeão em 1994?") == "campeoes"
    assert app_module.classificar_tema("Onde foi a Copa de 2010?") == "sedes"
    assert app_module.classificar_tema("Quem é o maior artilheiro?") == "artilheiros"
    assert app_module.classificar_tema("Qual a cor do uniforme?") == "outros"


def test_painel_uso_protegido(cliente, monkeypatch):
    monkeypatch.delenv("PAINEL_TOKEN", raising=False)
    assert cliente.get("/api/uso").status_code == 404
    monkeypatch.setenv("PAINEL_TOKEN", "segredo-de-teste")
    assert cliente.get("/api/uso").status_code == 401
    assert cliente.get("/api/uso", headers={"X-Painel-Token": "errado"}).status_code == 401
    resp = cliente.get("/api/uso", headers={"X-Painel-Token": "segredo-de-teste"})
    assert resp.status_code == 200
    dados = resp.get_json()
    assert "taxa_recusa" in dados and "temas" in dados and "dias" in dados


def test_cache_evita_nova_chamada(cliente, monkeypatch):
    falso = _usar_cliente_falso(monkeypatch, "Resposta de teste.")
    primeira = cliente.post("/api/chat", json={"mensagem": "Quem foi campeão em 1994?"})
    segunda = cliente.post("/api/chat", json={"mensagem": "  quem foi   CAMPEÃO em 1994? "})
    assert primeira.get_json()["resposta"] == "Resposta de teste."
    assert segunda.get_json()["cache"] is True
    assert falso.chamadas == 1


def test_recusa_conta_no_painel(cliente, monkeypatch):
    monkeypatch.setenv("PAINEL_TOKEN", "segredo-de-teste")
    _usar_cliente_falso(monkeypatch, app_module.RECUSA)
    cliente.post("/api/chat", json={"mensagem": "Qual a receita de bolo?"})
    dados = cliente.get("/api/uso", headers={"X-Painel-Token": "segredo-de-teste"}).get_json()
    assert dados["taxa_recusa"] > 0


def test_limite_por_ip_responde_429(cliente, monkeypatch):
    _usar_cliente_falso(monkeypatch, "ok")
    app_module.limiter.enabled = True
    codigos = [
        cliente.post("/api/chat", json={"mensagem": f"pergunta número {i}"}).status_code
        for i in range(21)
    ]
    assert codigos[:20] == [200] * 20
    assert codigos[20] == 429
