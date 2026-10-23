"""D-42 — o cliente GLOBAL associado a uma rede: abre-se, edita-se e cria-se-lhe processo. Nada mais.

Quando a equipa da Domus cria um cliente com o NIF **e** o Email de um cliente da Power, o cliente
é o mesmo e a Domus passa a constar de `redes_associadas`. Isso dá-lhe a janela do VISITANTE para o
passo seguinte (ler a ficha, corrigi-la, criar-lhe processo). Não lhe dá o resto: eliminar, atribuir,
ligar/desligar processos e reenviar o acesso ao Portal continuam a exigir um processo da MINHA rede
— a segregação estrita do CRM.

Os routers são os REAIS e os `run_*` são sentinelas: o ataque exige que o handler nunca corra.
"""
from __future__ import annotations

import pytest

from tests.unit.test_d31_clientes_e_tarefas_por_id import (  # noqa: F401  (fixtures e utilitários)
    HANDLERS_DE_CLIENTES,
    _como,
    _corpo_do_cliente,
    mundo,
    rede_de_omissao_incumbente,
)
from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE


@pytest.fixture
def associado(mundo, fake_async_db):
    """Um cliente da Power, sem processos, ao qual a Domus foi associada."""
    fake_async_db.clients.docs.append({
        "id": "c-global", "nome": "Silva Global", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
        "contacto": {}, "dados_pessoais": {}, "redes_associadas": [REDE_DOMUS],
    })
    return mundo


@pytest.fixture
def nao_associado(mundo, fake_async_db):
    fake_async_db.clients.docs.append({
        "id": "c-global", "nome": "Silva Global", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
        "contacto": {}, "dados_pessoais": {},
    })
    return mundo


class TestAAssociacaoDaAJanela:
    @pytest.mark.parametrize("metodo,caminho", [
        ("get", "/clients/c-global"),
        ("put", "/clients/c-global"),
        ("post", "/clients/c-global/create-process"),
    ])
    def test_a_rede_associada_le_edita_e_cria_processo(self, associado, metodo, caminho):
        http, atual, chamadas = associado
        _como(atual, "bruno")
        kwargs = {"json": _corpo_do_cliente()} if metodo == "put" else {}
        assert getattr(http, metodo)(caminho, **kwargs).status_code == 200, caminho

    @pytest.mark.parametrize("metodo,caminho", [
        ("delete", "/clients/c-global"),
        ("post", "/clients/c-global/assign"),
        ("post", "/clients/c-global/link-process?process_id=p-domus"),
        ("delete", "/clients/c-global/unlink-process/p-domus"),
        ("post", "/clients/c-global/resend-portal-access"),
        ("get", "/clients/c-global/processes"),
        ("get", "/clients/c-global/active-processes"),
    ])
    def test_a_associacao_nao_da_o_resto(self, associado, metodo, caminho):
        """Eliminar, atribuir, ligar processos e dar acesso ao Portal continuam a ser do dono."""
        http, atual, chamadas = associado
        _como(atual, "bruno")
        r = getattr(http, metodo)(caminho)
        assert r.status_code == 404, caminho
        for nome in HANDLERS_DE_CLIENTES:
            chamadas[nome].assert_not_called()

    @pytest.mark.parametrize("metodo,caminho", [
        ("get", "/clients/c-global"),
        ("put", "/clients/c-global"),
        ("post", "/clients/c-global/create-process"),
    ])
    def test_CONTRAPROVA_sem_a_associacao_a_Domus_nao_abre_nada(self, nao_associado, metodo, caminho):
        http, atual, chamadas = nao_associado
        _como(atual, "bruno")
        kwargs = {"json": _corpo_do_cliente()} if metodo == "put" else {}
        assert getattr(http, metodo)(caminho, **kwargs).status_code == 404
        for nome in HANDLERS_DE_CLIENTES:
            chamadas[nome].assert_not_called()

    def test_o_dono_continua_a_abrir_tudo(self, associado):
        http, atual, _ = associado
        _como(atual, "ana")
        assert http.get("/clients/c-global").status_code == 200
        assert http.delete("/clients/c-global").status_code == 200

    def test_a_associacao_da_Domus_nao_abre_o_cliente_a_outra_rede(self, associado, fake_async_db):
        """A associação é de UMA rede: a Power-Precision não ganha nada com ela (já é a dona)
        e um utilizador sem a Domus continua de fora."""
        from services.by_id_scope import cliente_associado_a_minha_rede
        from services.tenant_network import TenantScope

        doc = fake_async_db.clients.docs[-1]
        assert cliente_associado_a_minha_rede(doc, TenantScope(network_ids=(REDE_DOMUS,)))
        assert not cliente_associado_a_minha_rede(doc, TenantScope(network_ids=("rede:de-outra",)))
        assert not cliente_associado_a_minha_rede(doc, TenantScope(network_ids=()))

    @pytest.mark.parametrize("valor", [None, "", REDE_DOMUS, {"a": REDE_DOMUS}, 0, [None, ""]])
    def test_um_campo_do_tipo_errado_nunca_abre(self, valor):
        """Uma lista é truthy, uma string também: só uma LISTA de redes vale (a lição do `pasta_gravada`)."""
        from services.by_id_scope import cliente_associado_a_minha_rede
        from services.tenant_network import TenantScope

        assert not cliente_associado_a_minha_rede({"redes_associadas": valor}, TenantScope(network_ids=(REDE_DOMUS,)))

    def test_a_projeccao_leva_o_campo(self):
        """Sem o campo na projecção a guarda leria um cliente sem associações e fecharia sempre."""
        from services.by_id_scope import PROJECCAO_DO_CLIENTE

        assert PROJECCAO_DO_CLIENTE["redes_associadas"] == 1


class TestAsRotasQueAceitamAssociados:
    def test_so_a_ficha_e_a_criacao_de_processo(self):
        """A lista de rotas que a associação abre é curta e escrita: uma rota nova nasce FECHADA."""
        import inspect

        from services import by_id_scope as g

        fonte = inspect.getsource(g._aceita_associado)
        assert "_aceita_convidado" in fonte and "_CAMINHO_DE_CRIAR_PROCESSO" in fonte
        assert g._CAMINHO_DE_CRIAR_PROCESSO == "/clients/{client_id}/create-process"
        assert g._METODOS_QUE_ACEITAM_CONVIDADO == frozenset({"GET", "PUT"})
