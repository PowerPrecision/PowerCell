"""
PORTAL DO PARCEIRO — LEITURA: painel, lista, detalhe (V1)

O que se prova, por ordem de gravidade:

  1. a visibilidade é uma RELAÇÃO (atribuído a mim E na minha rede): o
     processo de outro parceiro da mesma rede, o meu processo carimbado com
     outra rede, o legado por carimbar de uma rede que não é a minha e o
     eliminado ficam todos de fora — e um id alheio é «não existe» (404
     igual), nunca «não é teu»;
  2. o parceiro nunca recebe o documento: DTO por lista positiva e NENHUM
     dado financeiro (decisão de produto da V1), com contraprova de que o
     detector de tokens financeiros morde;
  3. o funil usa a macro-fase do motor, e o que o motor não reconhece cai
     em «Em curso» em vez de desaparecer ou de ser inventado;
  4. ficheiros: o que EU enviei e o que o CLIENTE enviou — nunca o que a
     equipa juntou à mesma pasta — e nunca uma chave S3 na saída.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

PT1 = {"id": "pt-1", "name": "Rui", "email": "rui@p.pt", "status": "active",
       "redes": [{"network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "status": "active"}]}
PT2 = {"id": "pt-2", "name": "Sara", "email": "sara@p.pt", "status": "active",
       "redes": [{"network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "status": "active"}]}
PT3 = {"id": "pt-3", "name": "Tomé", "email": "tome@p.pt", "status": "active",
       "redes": [{"network_id": REDE_DOMUS, "company_id": "cmp-domus", "status": "active"}]}

FASES = [
    {"name": "fase_documental", "label": "Documental", "order": 1, "macro_fase": "novo"},
    {"name": "fase_bancaria", "label": "Bancária", "order": 2, "macro_fase": "analise"},
    {"name": "ch_aprovado", "label": "Aprovado", "order": 3, "macro_fase": "aprovado"},
    {"name": "concluidos", "label": "Concluídos", "order": 4, "macro_fase": "concluido"},
    {"name": "desistencias", "label": "Desistências", "order": 5, "macro_fase": "perdido"},
    {"name": "fase_sem_macro", "label": "Sem macro", "order": 6},
]

#: Lixo financeiro e interno que NUNCA pode chegar ao parceiro.
_SUJEIRA = {
    "credit_data": {"valor_pretendido": 250000, "rendimento_mensal": 3200, "prestacao": 900},
    "real_estate_data": {"preco": 310000, "morada": "Rua Secreta 1"},
    "client_nif": "123456789", "client_email": "cliente@x.pt", "client_phone": "912345678",
    "notes": "NOTA INTERNA: cliente difícil", "observations": "obs internas",
    "observation_notes": [{"text": "interna"}],
    "comissao": 1500, "financial_origin": {"tipo": "angariacao"},
}


def _proc(pid, partner, rede=REDE_INCUMBENTE, status="fase_documental", **extra):
    doc = {
        "id": pid, "process_number": f"PROC-{pid}", "client_name": f"Cliente {pid}",
        "process_type": "credito_habitacao", "status": status,
        "assigned_parceiro_id": partner, "consultor_names": ["Carla Consultora"],
        "created_at": "2026-10-01T10:00:00+00:00", "updated_at": "2026-10-02T10:00:00+00:00",
        "client_id": f"cli-{pid}", "s3_folder": f"Documentação Clientes/cli-{pid}",
        **_SUJEIRA, **extra,
    }
    if rede:
        doc["network_id"] = rede
        doc["company_id"] = "cmp-power" if rede == REDE_INCUMBENTE else "cmp-domus"
    return doc


def _lead(cid, partner, rede=REDE_INCUMBENTE, **extra):
    doc = {
        "id": cid, "nome": f"Lead {cid}", "submitted_by_partner_id": partner,
        "network_id": rede, "company_id": "cmp-power" if rede == REDE_INCUMBENTE else "cmp-domus",
        "process_ids": [], "lead_status": "new", "pending_process_type": "credito_habitacao",
        "created_at": "2026-10-03T10:00:00+00:00", "updated_at": "2026-10-03T10:00:00+00:00",
        "contacto": {"email": "segredo@x.pt", "telefone": "999"}, "dados_pessoais": {"nif": "987654321"},
        **extra,
    }
    return doc


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.workflow_statuses.docs.extend(dict(f) for f in FASES)
    fake_async_db.partners.docs.extend([dict(PT1), dict(PT2), dict(PT3)])
    return fake_async_db


@pytest.fixture
def com_bd(mundo):
    import services.partner_portal_read as ppr

    with tenant_db(mundo, ppr):
        yield mundo


def _dono(mundo):
    """Cenário principal: o PT1 tem 5 processos e 2 leads; os outros têm o seu."""
    mundo.processes.docs.clear()
    mundo.clients.docs.clear()
    mundo.processes.docs.extend([
        _proc("a-novo", "pt-1", status="fase_documental"),
        _proc("b-analise", "pt-1", status="fase_bancaria", updated_at="2026-10-05T10:00:00+00:00"),
        _proc("c-aprovado", "pt-1", status="ch_aprovado"),
        _proc("d-escriturado", "pt-1", status="concluidos"),
        _proc("e-perdido", "pt-1", status="desistencias"),
        # ── os que NÃO são do PT1 ─────────────────────────────────────
        _proc("x-de-outro-parceiro", "pt-2"),
        _proc("x-rede-errada", "pt-1", rede=REDE_DOMUS),
        _proc("x-eliminado", "pt-1", is_deleted=True),
        _proc("x-sem-parceiro", None),
        _proc("t-da-domus", "pt-3", rede=REDE_DOMUS),
    ])
    mundo.clients.docs.extend([
        _lead("lead-1", "pt-1"),
        _lead("lead-2", "pt-1", updated_at="2026-10-09T10:00:00+00:00"),
        # ── os que NÃO são leads do PT1 ───────────────────────────────
        _lead("x-lead-de-outro", "pt-2"),
        _lead("x-lead-com-processo", "pt-1", process_ids=["a-novo"]),
        _lead("x-lead-convertida", "pt-1", lead_status="converted"),
        _lead("x-lead-eliminada", "pt-1", is_deleted=True),
        _lead("x-lead-rede-errada", "pt-1", rede=REDE_DOMUS),
    ])


# ════════════════════════════════════════════════════════════════════
#  AS CONDIÇÕES
# ════════════════════════════════════════════════════════════════════
class TestAsCondicoes:
    def test_a_visibilidade_exige_a_atribuicao_E_a_rede(self):
        from services.partner_visibility import condicao_de_processos
        from tests.unit.helpers_tenant import casa

        cond = condicao_de_processos(PT1)
        assert casa(_proc("ok", "pt-1"), cond)
        assert not casa(_proc("outro", "pt-2"), cond), "atribuído a outro parceiro"
        assert not casa(_proc("rede", "pt-1", rede=REDE_DOMUS), cond), "atribuído a mim mas noutra rede"
        assert not casa(_proc("del", "pt-1", is_deleted=True), cond)

    def test_o_legado_por_carimbar_so_conta_para_quem_pertence_a_rede_de_omissao(self, rede_de_omissao_incumbente):
        from services.partner_visibility import condicao_de_processos
        from tests.unit.helpers_tenant import casa

        legado_do_pt1 = _proc("leg", "pt-1", rede=None)
        legado_do_pt3 = _proc("leg3", "pt-3", rede=None)
        assert casa(legado_do_pt1, condicao_de_processos(PT1))
        assert not casa(legado_do_pt3, condicao_de_processos(PT3)), "a Domus não herda a pilha antiga"

    def test_sem_nenhuma_rede_activa_a_condicao_nao_apanha_nada(self):
        from services.partner_visibility import condicao_de_leads, condicao_de_processos
        from tests.unit.helpers_tenant import casa

        suspenso = {**PT1, "redes": [{**PT1["redes"][0], "status": "suspended"}]}
        assert not casa(_proc("a", "pt-1"), condicao_de_processos(suspenso))
        assert not casa(_lead("l", "pt-1"), condicao_de_leads(suspenso))

    def test_nao_usa_o_ramo_das_redes_convidadas(self):
        """Um parceiro não herda uma partilha entre casas (D-25)."""
        from services.partner_visibility import condicao_de_processos
        from services.tenant_network import CAMPO_REDES_PARCEIRAS

        assert CAMPO_REDES_PARCEIRAS not in repr(condicao_de_processos(PT1))

    def test_uma_lead_so_e_lead_enquanto_nao_tem_processo(self):
        from services.partner_visibility import condicao_de_leads
        from tests.unit.helpers_tenant import casa

        cond = condicao_de_leads(PT1)
        assert casa(_lead("a", "pt-1"), cond)
        assert casa(_lead("b", "pt-1", process_ids=None), cond)
        sem_campo = _lead("c", "pt-1")
        sem_campo.pop("process_ids")
        assert casa(sem_campo, cond)
        assert not casa(_lead("d", "pt-1", process_ids=["p-1"]), cond)
        assert not casa(_lead("e", "pt-1", lead_status="converted"), cond)


# ════════════════════════════════════════════════════════════════════
#  O FUNIL
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestFunil:
    async def test_o_painel_conta_por_macro_fase_e_junta_as_leads(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        painel = await ppr.run_get_dashboard(PT1)
        totais = {e["etapa"]: e["total"] for e in painel["funil"]}
        # «Pendentes» mostra-se sempre (é a acção em mãos do parceiro); as
        # devolvidas e os expirados só quando existem.
        assert totais == {"pendente": 0, "lead": 2, "novo": 1, "analise": 1, "aprovado": 1, "concluido": 1, "perdido": 1}
        assert painel["total_de_casos"] == 7
        assert painel["escriturados"] == 1 and painel["leads"] == 2
        assert painel["taxa_de_conversao"] == round(100 * 1 / 7, 1)

    async def test_o_funil_mostra_as_etiquetas_do_parceiro(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        etiquetas = {e["etapa"]: e["label"] for e in (await ppr.run_get_dashboard(PT1))["funil"]}
        assert etiquetas["lead"] == "Leads"
        assert etiquetas["aprovado"] == "Em aprovação"
        assert etiquetas["concluido"] == "Escriturados"

    async def test_uma_fase_sem_macro_cai_em_curso_e_nao_desaparece(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        com_bd.processes.docs.append(_proc("f-sem-macro", "pt-1", status="fase_sem_macro"))
        com_bd.processes.docs.append(_proc("g-desconhecido", "pt-1", status="fase-que-nao-existe"))
        com_bd.processes.docs.append(_proc("h-sem-estado", "pt-1", status=None))
        totais = {e["etapa"]: e["total"] for e in (await ppr.run_get_dashboard(PT1))["funil"]}
        assert totais["em_curso"] == 3
        assert (await ppr.run_get_dashboard(PT1))["total_de_casos"] == 10

    async def test_em_curso_so_aparece_quando_existe(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        assert "em_curso" not in {e["etapa"] for e in (await ppr.run_get_dashboard(PT1))["funil"]}

    async def test_sem_casos_a_taxa_e_desconhecida_e_nao_zero(self, com_bd):
        import services.partner_portal_read as ppr

        painel = await ppr.run_get_dashboard(PT1)
        assert painel["taxa_de_conversao"] is None and painel["total_de_casos"] == 0

    async def test_o_alias_do_estado_resolve_pela_macro_fase_do_motor(self, com_bd):
        """`escriturado` é o nome que a UI antiga grava; o motor traduz-o."""
        import services.partner_portal_read as ppr

        com_bd.processes.docs.append(_proc("z", "pt-1", status="concluido"))
        totais = {e["etapa"]: e["total"] for e in (await ppr.run_get_dashboard(PT1))["funil"]}
        assert totais["concluido"] == 1

    def test_todas_as_macro_fases_do_motor_tem_etapa(self):
        """Uma macro-fase nova no enum sem etapa aqui cairia em «Em curso»
        em silêncio — este teste obriga a decidir."""
        from models.workflow import MacroFase
        from services.partner_visibility import ETAPA_POR_MACRO_FASE

        assert {m.value for m in MacroFase} == set(ETAPA_POR_MACRO_FASE)


# ════════════════════════════════════════════════════════════════════
#  A LISTA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestLista:
    async def test_so_aparecem_os_casos_do_parceiro(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        ids = {c["id"] for c in (await ppr.run_list_cases(PT1))["items"]}
        assert ids == {"a-novo", "b-analise", "c-aprovado", "d-escriturado", "e-perdido", "lead-1", "lead-2"}

    async def test_cada_parceiro_ve_so_o_seu(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        assert {c["id"] for c in (await ppr.run_list_cases(PT2))["items"]} == {"x-de-outro-parceiro", "x-lead-de-outro"}
        assert {c["id"] for c in (await ppr.run_list_cases(PT3))["items"]} == {"t-da-domus"}

    async def test_o_mais_recente_vem_primeiro(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        items = (await ppr.run_list_cases(PT1))["items"]
        assert items[0]["id"] == "lead-2"  # 10-09
        datas = [i["updated_at"] for i in items]
        assert datas == sorted(datas, reverse=True)

    async def test_filtra_por_etapa_e_pesquisa_por_nome_ou_numero(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        so_leads = await ppr.run_list_cases(PT1, etapa="lead")
        assert {c["id"] for c in so_leads["items"]} == {"lead-1", "lead-2"}
        por_numero = await ppr.run_list_cases(PT1, pesquisa="proc-c-aprov")
        assert [c["id"] for c in por_numero["items"]] == ["c-aprovado"]
        por_nome = await ppr.run_list_cases(PT1, pesquisa="LEAD-2")
        assert [c["id"] for c in por_nome["items"]] == ["lead-2"]

    async def test_uma_etapa_inventada_e_400(self, com_bd):
        import services.partner_portal_read as ppr

        with pytest.raises(HTTPException) as erro:
            await ppr.run_list_cases(PT1, etapa="$ne")
        assert erro.value.status_code == 400

    async def test_pagina_e_o_tamanho_tem_tecto(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        pag = await ppr.run_list_cases(PT1, page=2, size=3)
        assert pag["total"] == 7 and pag["pages"] == 3 and len(pag["items"]) == 3
        enorme = await ppr.run_list_cases(PT1, size=100000)
        assert enorme["size"] == ppr.TAMANHO_DE_PAGINA_MAXIMO

    async def test_conta_os_pedidos_pendentes_por_caso_incluindo_os_ancorados_so_ao_cliente(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        com_bd.documents.docs.extend([
            {"id": "d1", "process_id": "a-novo", "status": "REQUESTED", "source": "admin_request", "category": "IRS"},
            {"id": "d2", "process_id": "a-novo", "status": "PENDING", "source": "admin_request", "category": "CC"},
            {"id": "d3", "process_id": "a-novo", "status": "RECEIVED", "source": "admin_request", "category": "X"},
            # ancorado só ao cliente do processo (registo público / Sala de Triagem)
            {"id": "d4", "client_id": "cli-b-analise", "status": "REQUESTED", "source": "mandatory_checklist"},
            # pedido de uma lead
            {"id": "d5", "client_id": "lead-1", "status": "REQUESTED", "source": "mandatory_checklist"},
            # de outro processo (não pode contar)
            {"id": "d6", "process_id": "x-de-outro-parceiro", "status": "REQUESTED", "source": "admin_request"},
        ])
        itens = {c["id"]: c for c in (await ppr.run_list_cases(PT1))["items"]}
        assert itens["a-novo"]["pedidos_pendentes"] == 2
        assert itens["b-analise"]["pedidos_pendentes"] == 1
        assert itens["lead-1"]["pedidos_pendentes"] == 1
        assert itens["lead-2"]["pedidos_pendentes"] == 0
        assert (await ppr.run_get_dashboard(PT1))["pedidos_pendentes"] == 4


# ════════════════════════════════════════════════════════════════════
#  O ISOLAMENTO POR ID
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestIsolamentoPorId:
    @pytest.mark.parametrize(
        "alheio",
        ["x-de-outro-parceiro", "x-rede-errada", "x-eliminado", "x-sem-parceiro", "t-da-domus",
         "x-lead-de-outro", "x-lead-com-processo", "x-lead-convertida", "x-lead-eliminada", "x-lead-rede-errada"],
    )
    async def test_um_caso_alheio_e_404_igual_ao_de_um_inexistente(self, com_bd, alheio):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        with pytest.raises(HTTPException) as erro_alheio:
            await ppr.run_get_case(PT1, alheio)
        with pytest.raises(HTTPException) as erro_nada:
            await ppr.run_get_case(PT1, "nao-existe")
        assert erro_alheio.value.status_code == erro_nada.value.status_code == 404
        assert erro_alheio.value.detail == erro_nada.value.detail

    async def test_um_id_vazio_ou_estranho_nao_abre_nada(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        for lixo in ("", "   ", None):
            with pytest.raises(HTTPException) as erro:
                await ppr.resolver_caso(PT1, lixo)
            assert erro.value.status_code == 404

    async def test_o_proprio_caso_resolve(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        assert (await ppr.resolver_caso(PT1, "a-novo")).tipo == "process"
        assert (await ppr.resolver_caso(PT1, "lead-1")).tipo == "lead"

    async def test_suspender_a_ligacao_fecha_tudo(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        suspenso = {**PT1, "redes": [{**PT1["redes"][0], "status": "suspended"}]}
        assert (await ppr.run_list_cases(suspenso))["total"] == 0
        with pytest.raises(HTTPException):
            await ppr.run_get_case(suspenso, "a-novo")


# ════════════════════════════════════════════════════════════════════
#  SEM DADOS FINANCEIROS NEM INTERNOS
# ════════════════════════════════════════════════════════════════════
_TOKENS_FINANCEIROS = (
    "valor", "preco", "price", "salar", "income", "rendiment", "comiss", "commission", "financ",
    "credit", "loan", "emprest", "montante", "amount", "iban", "euribor", "spread", "taeg",
    "dsti", "ltv", "prestacao", "nif", "real_estate", "morada", "notes", "observ",
)


def chaves_suspeitas(obj, caminho="") -> list[str]:
    """Percorre a saída e devolve os caminhos cujo NOME é financeiro/interno."""
    achados: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            nome = str(k).lower()
            # `notes` é a nota do PEDIDO de documentos — a que o cliente também lê.
            ignorar = caminho.endswith("pedidos[]") and nome == "notes"
            if not ignorar and any(t in nome for t in _TOKENS_FINANCEIROS):
                achados.append(f"{caminho}.{k}".lstrip("."))
            achados += chaves_suspeitas(v, f"{caminho}.{k}")
    elif isinstance(obj, list):
        for item in obj:
            achados += chaves_suspeitas(item, f"{caminho}[]")
    return achados


@pytest.mark.asyncio
class TestSemDadosFinanceiros:
    def test_o_detector_morde(self):
        """Contraprova: um DTO sujo é apanhado — senão o teste abaixo passava
        a provar nada."""
        assert chaves_suspeitas({"credit_data": {"valor_pretendido": 1}})
        assert chaves_suspeitas({"a": [{"comissao": 1}]})
        assert chaves_suspeitas({"client_nif": "1"})
        assert chaves_suspeitas({"etapa": "novo", "id": "x"}) == []

    async def test_a_lista_o_painel_e_o_detalhe_nao_levam_dados_financeiros_nem_internos(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        saidas = {
            "lista": await ppr.run_list_cases(PT1),
            "painel": await ppr.run_get_dashboard(PT1),
            "detalhe_processo": await ppr.run_get_case(PT1, "a-novo"),
            "detalhe_lead": await ppr.run_get_case(PT1, "lead-1"),
        }
        for nome, saida in saidas.items():
            assert chaves_suspeitas(saida) == [], nome

    async def test_os_valores_sujos_do_documento_nao_aparecem_em_lado_nenhum(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        blob = repr([
            await ppr.run_list_cases(PT1),
            await ppr.run_get_case(PT1, "a-novo"),
            await ppr.run_get_case(PT1, "lead-1"),
        ])
        for segredo in ("250000", "3200", "310000", "Rua Secreta", "123456789", "cliente@x.pt", "912345678",
                        "NOTA INTERNA", "segredo@x.pt", "987654321", "1500", "angariacao"):
            assert segredo not in blob, segredo

    async def test_a_saida_do_processo_e_exactamente_a_lista_positiva(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        item = next(c for c in (await ppr.run_list_cases(PT1))["items"] if c["id"] == "a-novo")
        assert set(item) == {
            "kind", "id", "process_number", "client_name", "process_type", "etapa", "etapa_label",
            "consultor_name", "pedidos_pendentes", "created_at", "updated_at",
        }
        assert item["consultor_name"] == "Carla Consultora"

    async def test_um_campo_novo_no_documento_do_processo_nao_chega_ao_parceiro(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        com_bd.processes.docs[0]["campo_novo_perigoso"] = "SEGREDO-NOVO"
        assert "SEGREDO-NOVO" not in repr(await ppr.run_get_case(PT1, "a-novo"))


# ════════════════════════════════════════════════════════════════════
#  PEDIDOS E FICHEIROS
# ════════════════════════════════════════════════════════════════════
def _documentos(mundo):
    mundo.documents.docs.extend([
        # Pedido da equipa, ainda por satisfazer — com a nota que o cliente também lê.
        {"id": "req-1", "process_id": "a-novo", "status": "REQUESTED", "source": "admin_request",
         "category": "Cartão de Cidadão", "custom_label": "CC frente e verso", "notes": "Frente e verso, por favor",
         "expected_count": 2, "created_at": "2026-10-04T10:00:00+00:00", "requested_by": "u-secreto",
         "requested_by_name": "Consultora Interna"},
        # Pedido satisfeito por TRÊS autores: cliente, parceiro e equipa.
        {"id": "req-2", "process_id": "a-novo", "status": "RECEIVED", "source": "admin_request",
         "category": "IRS", "created_at": "2026-10-05T10:00:00+00:00",
         "attached_files": [
             {"file_id": "f-cli", "filename": "irs-cliente.pdf", "file_size": 10, "s3_path": "Documentação Clientes/cli-a-novo/Index/irs-cliente.pdf",
              "uploaded_at": "2026-10-05T11:00:00+00:00", "uploaded_by": "portal_client"},
             {"file_id": "f-eu", "filename": "irs-parceiro.pdf", "file_size": 11, "s3_path": "Documentação Clientes/cli-a-novo/Index/irs-parceiro.pdf",
              "uploaded_at": "2026-10-05T12:00:00+00:00", "uploaded_by": "partner:pt-1"},
             {"file_id": "f-outro-parceiro", "filename": "irs-outro.pdf", "file_size": 12, "s3_path": "Documentação Clientes/cli-a-novo/Index/irs-outro.pdf",
              "uploaded_at": "2026-10-05T12:30:00+00:00", "uploaded_by": "partner:pt-2"},
             {"file_id": "f-staff", "filename": "irs-equipa.pdf", "file_size": 13, "s3_path": "Documentação Clientes/cli-a-novo/Financeiros/irs-equipa.pdf",
              "uploaded_at": "2026-10-05T13:00:00+00:00", "uploaded_by": "u-consultora"},
         ]},
        # Envios soltos.
        {"id": "solto-eu", "process_id": "a-novo", "status": "RECEIVED", "source": "partner_portal",
         "filename": "extra.pdf", "s3_path": "Documentação Clientes/cli-a-novo/Index/extra.pdf",
         "uploaded_by": "partner:pt-1", "uploaded_at": "2026-10-06T10:00:00+00:00", "category": "Index"},
        {"id": "solto-cliente", "process_id": "a-novo", "status": "RECEIVED", "source": "client_portal",
         "filename": "foto.jpg", "s3_path": "Documentação Clientes/cli-a-novo/Index/foto.jpg",
         "uploaded_by": "portal_client", "uploaded_at": "2026-10-06T11:00:00+00:00", "category": "Index"},
        {"id": "solto-equipa", "process_id": "a-novo", "status": "RECEIVED", "source": "client_portal",
         "filename": "interno.pdf", "s3_path": "Documentação Clientes/cli-a-novo/Financeiros/interno.pdf",
         "uploaded_by": "u-consultora", "uploaded_at": "2026-10-06T12:00:00+00:00", "category": "Financeiros"},
    ])


@pytest.mark.asyncio
class TestPedidosEFicheiros:
    async def test_o_pedido_leva_a_nota_do_cliente_e_o_estado(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        _documentos(com_bd)
        detalhe = await ppr.run_get_case(PT1, "a-novo")
        pedidos = {p["id"]: p for p in detalhe["pedidos"]}
        assert pedidos["req-1"]["label"] == "CC frente e verso"
        assert pedidos["req-1"]["notes"] == "Frente e verso, por favor"
        assert pedidos["req-1"]["estado"] == "pendente" and pedidos["req-2"]["estado"] == "recebido"
        assert detalhe["pedidos_pendentes"] == 1

    async def test_quem_pediu_nao_sai(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        _documentos(com_bd)
        blob = repr(await ppr.run_get_case(PT1, "a-novo"))
        assert "u-secreto" not in blob and "Consultora Interna" not in blob

    async def test_so_vejo_o_que_eu_e_o_cliente_enviamos(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        _documentos(com_bd)
        detalhe = await ppr.run_get_case(PT1, "a-novo")
        nos_pedidos = {f["id"]: f["by"] for p in detalhe["pedidos"] for f in p["ficheiros"]}
        assert nos_pedidos == {"f-cli": "cliente", "f-eu": "eu"}
        soltos = {f["id"]: f["by"] for f in detalhe["ficheiros"]}
        assert soltos == {"solto-eu": "eu", "solto-cliente": "cliente"}

    async def test_o_que_a_equipa_juntou_e_o_que_outro_parceiro_enviou_ficam_de_fora(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        _documentos(com_bd)
        blob = repr(await ppr.run_get_case(PT1, "a-novo"))
        for escondido in ("irs-equipa", "irs-outro", "interno.pdf", "f-staff", "f-outro-parceiro", "solto-equipa"):
            assert escondido not in blob, escondido

    async def test_nunca_sai_uma_chave_s3(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        _documentos(com_bd)
        blob = repr(await ppr.run_get_case(PT1, "a-novo"))
        assert "s3_path" not in blob and "Documentação Clientes" not in blob and "file_key" not in blob

    async def test_a_resolucao_interna_traz_a_chave_mas_so_dos_visiveis(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        _documentos(com_bd)
        caso = await ppr.resolver_caso(PT1, "a-novo")
        ids = {f["id"] for f in await ppr.ficheiros_internos(PT1, caso)}
        assert ids == {"f-cli", "f-eu", "solto-eu", "solto-cliente"}
        for f in await ppr.ficheiros_internos(PT1, caso):
            assert f["s3_path"]

    async def test_outro_parceiro_da_mesma_rede_nao_ve_os_meus_ficheiros(self, com_bd):
        """O PT2 não tem acesso ao caso do PT1 — nem sequer chega aos ficheiros."""
        import services.partner_portal_read as ppr

        _dono(com_bd)
        _documentos(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ppr.run_get_case(PT2, "a-novo")
        assert erro.value.status_code == 404

    async def test_o_pedido_de_uma_lead_ancorado_so_ao_cliente_aparece_no_detalhe(self, com_bd):
        import services.partner_portal_read as ppr

        _dono(com_bd)
        com_bd.documents.docs.extend([
            {"id": "lr-1", "client_id": "lead-1", "status": "REQUESTED", "source": "mandatory_checklist", "category": "CC"},
            # de outra lead: nunca
            {"id": "lr-x", "client_id": "x-lead-de-outro", "status": "REQUESTED", "source": "mandatory_checklist", "category": "CC"},
            # do mesmo cliente mas JÁ ancorado a um processo: não é desta lead
            {"id": "lr-p", "client_id": "lead-1", "process_id": "a-novo", "status": "REQUESTED", "source": "admin_request"},
        ])
        detalhe = await ppr.run_get_case(PT1, "lead-1")
        assert [p["id"] for p in detalhe["pedidos"]] == ["lr-1"]
        assert detalhe["kind"] == "lead"
