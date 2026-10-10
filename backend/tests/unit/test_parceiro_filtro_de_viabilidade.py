"""
Bloco B — o filtro de viabilidade do Parceiro (Out 2026).

O PEDIDO
  3. A lead só passa para o lado da equipa se o parceiro submeter um
     ficheiro categorizado como «Comprovativo de Pagamento». Sem ele, o
     registo fica retido do lado do parceiro (Pendente).
  4. Com o comprovativo, fica a aguardar uma «Validação Financeira»
     (Validar / Rejeitar — só CEO, Diretor e Administrativo). Rejeitada: a
     lead é devolvida, sai da vista do Index e o parceiro é avisado. Não
     validada: NÃO bloqueia nada — só um selo vermelho.
  7. Leads pendentes sem actividade há 60 dias passam a «Expirado».

O QUE ESTES TESTES VIGIAM
  * a retenção é ESTRUTURAL (colecção própria): a equipa não vê o
    rascunho em nenhuma superfície;
  * só a categoria INTEIRA «Comprovativo de Pagamento» liberta — não um
    prefixo comum, não o nome do ficheiro;
  * a validação nunca bloqueia (guarda de fonte: nada no motor a lê).
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import REDE_INCUMBENTE
from tests.unit.test_parceiro_escrita import (  # noqa: F401  (fixtures do mundo do parceiro)
    CHAVE_BOA,
    _confirmar,
    _corpo,
    com_bd,
    mundo,
    rede_de_omissao_incumbente,
    s3,
    tarefas,
    veredicto,
)
from tests.unit.test_parceiro_leitura import PT1, PT2

BACKEND = Path(__file__).resolve().parents[2]
COMPROVATIVO = "Comprovativo_Pagamento"


async def _lead_retida(com_bd, parceiro=PT1, **extra):
    import services.partner_leads as pl

    r = await pl.run_submit_lead(parceiro, pl.PartnerLeadIn(**_corpo(**extra)))
    return r["id"]


def _chave(client_id, nome="comprovativo.pdf"):
    return f"Documentação Clientes/{client_id}/Index/{nome}"


async def _enviar(com_bd, client_id, categoria, *, parceiro=PT1, nome="x.pdf", request_id=None):
    import services.partner_upload_ops as ops

    extra = {"category": categoria} if categoria is not None else {}
    if request_id:
        extra["request_id"] = request_id
    return await ops.run_partner_confirm_upload(
        parceiro, client_id, _confirmar(ops, key=_chave(client_id, nome), nome=nome, **extra),
    )


# ════════════════════════════════════════════════════════════════════
#  A categoria
# ════════════════════════════════════════════════════════════════════
class TestACategoriaDoComprovativo:
    @pytest.mark.parametrize("valor", [
        "Comprovativo_Pagamento", "Comprovativo de Pagamento", "comprovativo_pagamento",
        "  COMPROVATIVO DE PAGAMENTO ", "Comprovativo-Pagamento",
    ])
    def test_reconhece_as_grafias_da_categoria(self, valor):
        from services.partner_drafts import e_comprovativo_de_pagamento

        assert e_comprovativo_de_pagamento(valor) is True

    @pytest.mark.parametrize("valor", [
        "Comprovativo_IBAN", "Comprovativo", "Pagamento", "Comprovativo_Pagamento_Extra",
        "", None, "Outros", "Index", "Recibo_Vencimento",
    ])
    def test_um_prefixo_comum_nao_e_a_categoria(self, valor):
        """«Comprovativo_IBAN» tem a mesma primeira palavra e não liberta nada."""
        from services.partner_drafts import e_comprovativo_de_pagamento

        assert e_comprovativo_de_pagamento(valor) is False


# ════════════════════════════════════════════════════════════════════
#  A retenção
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestARetencao:
    async def test_a_lead_nasce_retida_e_a_equipa_nao_a_ve_em_lado_nenhum(self, com_bd):
        cid = await _lead_retida(com_bd)

        assert [d["id"] for d in com_bd.partner_drafts.docs] == [cid]
        assert not [c for c in com_bd.clients.docs if c.get("id") == cid], "nasceu na colecção da equipa"

    async def test_o_parceiro_ve_a_lead_como_pendente(self, com_bd):
        import services.partner_portal_read as ppr

        cid = await _lead_retida(com_bd)
        itens = (await ppr.run_list_cases(PT1))["items"]
        assert [(i["id"], i["etapa"], i["requer_comprovativo"]) for i in itens] == [(cid, "pendente", True)]
        caso = await ppr.run_get_case(PT1, cid)
        assert caso["etapa"] == "pendente" and caso["editavel"] is True

    async def test_outro_parceiro_nao_ve_o_rascunho_nem_o_abre_por_id(self, com_bd):
        import services.partner_portal_read as ppr

        cid = await _lead_retida(com_bd)
        assert (await ppr.run_list_cases(PT2))["items"] == []
        with pytest.raises(HTTPException) as erro:
            await ppr.run_get_case(PT2, cid)
        assert erro.value.status_code == 404

    async def test_o_painel_conta_os_pendentes(self, com_bd):
        import services.partner_portal_read as ppr

        await _lead_retida(com_bd)
        painel = await ppr.run_get_dashboard(PT1)
        assert painel["pendentes"] == 1
        etapas = {e["etapa"]: e["total"] for e in painel["funil"]}
        assert etapas["pendente"] == 1 and etapas["lead"] == 0

    async def test_a_equipa_nao_e_avisada_enquanto_a_lead_esta_retida(self, com_bd, tarefas):
        cid = await _lead_retida(com_bd)
        assert f"partner-lead-alert:{cid}" not in tarefas

    async def test_um_ficheiro_qualquer_nao_liberta(self, com_bd):
        cid = await _lead_retida(com_bd)
        resposta = await _enviar(com_bd, cid, "Cartao_Cidadao")
        assert resposta["lead_submetida"] is False
        assert [d["id"] for d in com_bd.partner_drafts.docs] == [cid]
        assert not [c for c in com_bd.clients.docs if c.get("id") == cid]

    async def test_sem_categoria_nao_liberta(self, com_bd):
        cid = await _lead_retida(com_bd)
        assert (await _enviar(com_bd, cid, None))["lead_submetida"] is False

    async def test_o_nome_do_ficheiro_nao_decide(self, com_bd):
        """Um ficheiro chamado «comprovativo_pagamento.pdf» enviado como
        «Outros» não liberta nada — decide a categoria, não o nome."""
        cid = await _lead_retida(com_bd)
        resposta = await _enviar(com_bd, cid, "Outros", nome="comprovativo_pagamento.pdf")
        assert resposta["lead_submetida"] is False

    async def test_comprovativo_do_iban_nao_liberta(self, com_bd):
        cid = await _lead_retida(com_bd)
        assert (await _enviar(com_bd, cid, "Comprovativo_IBAN"))["lead_submetida"] is False


# ════════════════════════════════════════════════════════════════════
#  A libertação
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestALibertacao:
    async def test_o_comprovativo_passa_a_lead_a_equipa(self, com_bd):
        cid = await _lead_retida(com_bd)
        resposta = await _enviar(com_bd, cid, COMPROVATIVO)

        assert resposta["lead_submetida"] is True
        assert not com_bd.partner_drafts.docs, "a libertação é um MOVIMENTO, não uma cópia"
        lead = next(c for c in com_bd.clients.docs if c["id"] == cid)
        assert lead["lead_status"] == "new" and lead["network_id"] == REDE_INCUMBENTE
        assert "partner_stage" not in lead and "last_activity_at" not in lead
        assert lead["submitted_by_partner_id"] == "pt-1"

    async def test_a_lead_libertada_nasce_com_a_validacao_financeira_pendente(self, com_bd):
        cid = await _lead_retida(com_bd)
        await _enviar(com_bd, cid, COMPROVATIVO, nome="pagamento.pdf")

        lead = next(c for c in com_bd.clients.docs if c["id"] == cid)
        validacao = lead["validacao_financeira"]
        assert validacao["estado"] == "pendente"
        assert validacao["comprovativo"]["filename"] == "pagamento.pdf"

    async def test_o_id_mantem_se_e_os_ficheiros_continuam_do_mesmo_cliente(self, com_bd):
        cid = await _lead_retida(com_bd)
        await _enviar(com_bd, cid, "Cartao_Cidadao", nome="cc.pdf")
        await _enviar(com_bd, cid, COMPROVATIVO)

        assert {d["client_id"] for d in com_bd.documents.docs if d.get("source") == "partner_portal"} == {cid}

    async def test_a_gestao_e_avisada_uma_vez_na_libertacao(self, com_bd, tarefas):
        cid = await _lead_retida(com_bd)
        await _enviar(com_bd, cid, COMPROVATIVO)
        assert tarefas.count(f"partner-lead-alert:{cid}") == 1

    async def test_o_comprovativo_fica_marcado_no_ficheiro_pelo_servidor(self, com_bd):
        cid = await _lead_retida(com_bd)
        await _enviar(com_bd, cid, COMPROVATIVO)
        marcados = [d for d in com_bd.documents.docs if d.get("comprovativo_de_pagamento")]
        assert len(marcados) == 1 and marcados[0]["declared_category"] == COMPROVATIVO

    async def test_um_comprovativo_num_processo_nao_tem_efeito(self, com_bd):
        """Um processo já passou o filtro de viabilidade."""
        import services.partner_upload_ops as ops
        from tests.unit.test_parceiro_escrita import _mundo

        _mundo(com_bd)
        await ops.run_partner_confirm_upload(
            PT1, "a-novo", _confirmar(ops, category=COMPROVATIVO),
        )
        assert not [d for d in com_bd.documents.docs if d.get("comprovativo_de_pagamento")]

    async def test_libertar_duas_vezes_nao_duplica_o_cliente(self, com_bd):
        from services.partner_drafts import libertar_se_tiver_comprovativo

        cid = await _lead_retida(com_bd)
        await _enviar(com_bd, cid, COMPROVATIVO)
        assert await libertar_se_tiver_comprovativo(cid) is None
        assert len([c for c in com_bd.clients.docs if c["id"] == cid]) == 1

    async def test_uma_falha_ao_libertar_nao_faz_falhar_o_envio(self, com_bd):
        cid = await _lead_retida(com_bd)
        with patch("services.partner_upload_ops.libertar_se_tiver_comprovativo", AsyncMock(side_effect=RuntimeError("x"))):
            resposta = await _enviar(com_bd, cid, COMPROVATIVO)
        assert resposta["success"] is True and resposta["lead_submetida"] is False
        assert [d["id"] for d in com_bd.partner_drafts.docs] == [cid], "o rascunho não se perde"

    async def test_a_lead_libertada_aparece_na_lista_do_parceiro_como_lead(self, com_bd):
        import services.partner_portal_read as ppr

        cid = await _lead_retida(com_bd)
        await _enviar(com_bd, cid, COMPROVATIVO)
        itens = (await ppr.run_list_cases(PT1))["items"]
        assert [(i["id"], i["etapa"]) for i in itens] == [(cid, "lead")]


# ════════════════════════════════════════════════════════════════════
#  A validação financeira
# ════════════════════════════════════════════════════════════════════
CEO = {"id": "u-ceo", "name": "Dono", "role": "ceo", "email": "ceo@p.pt"}


def _com_papel(papel):
    return {"id": f"u-{papel}", "name": papel.title(), "role": papel, "email": f"{papel}@p.pt"}


@pytest.fixture
def quem_decide(com_bd):
    """O papel efectivo é o do utilizador e o âmbito é o da Power."""
    import services.financial_validation as fv
    from tests.unit.helpers_tenant import UCRS

    for papel in ("ceo", "diretor", "administrativo", "consultor", "admin", "master"):
        com_bd.user_company_roles.docs.append(
            {"user_id": f"u-{papel}", "company_id": "cmp-power", "company_name": "Power Real Estate",
             "role": papel, "is_default": True}
        )

    async def papel(request, user):
        return user["role"]

    import services.partner_accounts as acc

    with patch("services.auth.get_effective_role_async", papel), \
            patch.object(fv, "db", com_bd), \
            patch.object(acc, "db", com_bd), \
            patch("services.history.log_history", AsyncMock()), \
            patch("services.email_service.send_email", AsyncMock()):
        yield fv


async def _lead_libertada(com_bd):
    cid = await _lead_retida(com_bd)
    await _enviar(com_bd, cid, COMPROVATIVO)
    return cid


@pytest.mark.asyncio
class TestQuemPodeDecidir:
    @pytest.mark.parametrize("papel", ["ceo", "diretor", "administrativo"])
    async def test_validam_ceo_diretor_e_administrativo(self, com_bd, quem_decide, papel):
        cid = await _lead_libertada(com_bd)
        r = await quem_decide.run_decidir("lead", cid, "validate", None, _com_papel(papel))
        assert r["estado"] == "validado"
        assert next(c for c in com_bd.clients.docs if c["id"] == cid)["validacao_financeira"]["estado"] == "validado"

    @pytest.mark.parametrize("papel", ["consultor", "admin", "master", "indexacao", "intermediario"])
    async def test_os_outros_perfis_nao_decidem(self, com_bd, quem_decide, papel):
        cid = await _lead_libertada(com_bd)
        with pytest.raises(HTTPException) as erro:
            await quem_decide.run_decidir("lead", cid, "validate", None, _com_papel(papel))
        assert erro.value.status_code == 403
        assert next(c for c in com_bd.clients.docs if c["id"] == cid)["validacao_financeira"]["estado"] == "pendente"

    async def test_uma_lead_de_outra_rede_e_404_e_nao_403(self, com_bd, quem_decide):
        cid = await _lead_libertada(com_bd)
        com_bd.user_company_roles.docs.append(
            {"user_id": "u-diretor", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor",
             "is_default": True}
        )
        com_bd.user_company_roles.docs[:] = [
            u for u in com_bd.user_company_roles.docs
            if not (u["user_id"] == "u-diretor" and u["company_id"] == "cmp-power")
        ]
        with pytest.raises(HTTPException) as erro:
            await quem_decide.run_decidir("lead", cid, "validate", None, _com_papel("diretor"))
        assert erro.value.status_code == 404

    async def test_o_tipo_desconhecido_e_404(self, com_bd, quem_decide):
        with pytest.raises(HTTPException) as erro:
            await quem_decide.run_decidir("cliente", "x", "validate", None, _com_papel("ceo"))
        assert erro.value.status_code == 404


@pytest.mark.asyncio
class TestRejeitar:
    async def test_a_rejeicao_devolve_a_lead_ao_parceiro_com_o_motivo(self, com_bd, quem_decide):
        import services.partner_portal_read as ppr

        cid = await _lead_libertada(com_bd)
        r = await quem_decide.run_decidir("lead", cid, "reject", "Comprovativo ilegível", _com_papel("ceo"))

        assert r == {"success": True, "estado": "rejeitado", "devolvida": True}
        assert not [c for c in com_bd.clients.docs if c["id"] == cid], "sai de TODAS as listas da equipa"
        rascunho = next(d for d in com_bd.partner_drafts.docs if d["id"] == cid)
        assert rascunho["partner_stage"] == "devolvida"
        assert rascunho["devolucao"]["motivo"] == "Comprovativo ilegível"
        caso = await ppr.run_get_case(PT1, cid)
        assert caso["etapa"] == "devolvida" and caso["motivo_da_devolucao"] == "Comprovativo ilegível"

    async def test_o_motivo_e_obrigatorio(self, com_bd, quem_decide):
        cid = await _lead_libertada(com_bd)
        for motivo in (None, "", "  ", "ab"):
            with pytest.raises(HTTPException) as erro:
                await quem_decide.run_decidir("lead", cid, "reject", motivo, _com_papel("ceo"))
            assert erro.value.status_code == 400
        assert [c["id"] for c in com_bd.clients.docs if c["id"] == cid] == [cid]

    async def test_o_parceiro_e_avisado_por_email(self, com_bd, quem_decide, tarefas):
        cid = await _lead_libertada(com_bd)
        await quem_decide.run_decidir("lead", cid, "reject", "Pagamento não confirmado", _com_papel("ceo"))
        assert f"partner-reject:{cid}" in tarefas

    async def test_o_email_leva_o_motivo(self, com_bd, quem_decide):
        enviar = AsyncMock()
        with patch("services.email_service.send_email", enviar):
            await quem_decide._enviar_email_de_rejeicao(
                {"email": "rui@p.pt", "name": "Rui"}, {"nome": "Joana"}, "Pagamento não confirmado",
            )
        assert "Pagamento não confirmado" in enviar.await_args.kwargs["body"]
        assert enviar.await_args.kwargs["to_emails"] == ["rui@p.pt"]

    async def test_depois_de_devolvida_so_um_comprovativo_novo_liberta(self, com_bd, quem_decide):
        cid = await _lead_libertada(com_bd)
        await quem_decide.run_decidir("lead", cid, "reject", "Ilegível", _com_papel("ceo"))

        from services.partner_drafts import libertar_se_tiver_comprovativo

        assert await libertar_se_tiver_comprovativo(cid) is None, "o comprovativo antigo é o que foi rejeitado"
        assert [d["id"] for d in com_bd.partner_drafts.docs] == [cid]

        # Um envio novo (depois da devolução) volta a libertar, com histórico.
        novo = await _enviar(com_bd, cid, COMPROVATIVO, nome="novo.pdf")
        assert novo["lead_submetida"] is True
        lead = next(c for c in com_bd.clients.docs if c["id"] == cid)
        assert lead["validacao_financeira"]["estado"] == "pendente"
        assert lead["devolucoes_anteriores"][0]["motivo"] == "Ilegível"

    async def test_rejeitar_duas_vezes_e_409(self, com_bd, quem_decide):
        cid = await _lead_libertada(com_bd)
        await quem_decide.run_decidir("lead", cid, "validate", None, _com_papel("ceo"))
        with pytest.raises(HTTPException) as erro:
            await quem_decide.run_decidir("lead", cid, "validate", None, _com_papel("ceo"))
        assert erro.value.status_code == 409


@pytest.mark.asyncio
class TestOProcessoNaoValidado:
    def _processo(self, com_bd, estado="pendente"):
        com_bd.processes.docs.append({
            "id": "p-parceiro", "client_id": "c-1", "client_name": "Joana", "status": "fase_documental",
            "network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "assigned_parceiro_id": "pt-1",
            "validacao_financeira": {"estado": estado},
        })
        com_bd.clients.docs.append({
            "id": "c-1", "nome": "Joana", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
            "submitted_by_partner_id": "pt-1", "process_ids": ["p-parceiro"],
            "validacao_financeira": {"estado": estado},
        })

    async def test_o_processo_herda_a_validacao_do_cliente(self):
        from services.partner_attribution import aplicar_parceiro_do_cliente

        processo = {"id": "p"}
        aplicar_parceiro_do_cliente(processo, {"submitted_by_partner_id": "pt-1",
                                               "validacao_financeira": {"estado": "pendente"}})
        assert processo["validacao_financeira"] == {"estado": "pendente"}

    async def test_a_heranca_nao_inventa_validacao_a_quem_nao_vem_de_parceiro(self):
        from services.partner_attribution import aplicar_parceiro_do_cliente

        processo = {"id": "p"}
        aplicar_parceiro_do_cliente(processo, {"nome": "Cliente normal"})
        assert "validacao_financeira" not in processo

    async def test_validar_acende_o_estado_no_processo_e_no_cliente(self, com_bd, quem_decide):
        self._processo(com_bd)
        await quem_decide.run_decidir("process", "p-parceiro", "validate", None, _com_papel("diretor"))
        assert com_bd.processes.docs[-1]["validacao_financeira"]["estado"] == "validado"
        assert com_bd.clients.docs[-1]["validacao_financeira"]["estado"] == "validado"

    async def test_rejeitar_um_processo_fecha_o_na_fase_terminal_e_sai_do_index(self, com_bd, quem_decide):
        self._processo(com_bd)
        com_bd.processes.docs[-1].update({"assigned_indexacao_id": "u-ivo", "indexacao_name": "Ivo"})
        # O motor manda: as fases terminais são as que têm `is_active: false`.
        for fase in com_bd.workflow_statuses.docs:
            fase["is_active"] = fase["name"] not in ("concluidos", "desistencias")
        terminal = "desistencias"  # a macro-fase «perdido» ganha à primeira terminal
        import services.workflow_phases as wp

        with patch.object(wp, "db", com_bd):
            wp.invalidar_cache_de_fases()
            await quem_decide.run_decidir("process", "p-parceiro", "reject", "Sem viabilidade", _com_papel("ceo"))
            wp.invalidar_cache_de_fases()

        proc = com_bd.processes.docs[-1]
        assert proc["validacao_financeira"]["estado"] == "rejeitado"
        assert proc["validacao_financeira"]["motivo"] == "Sem viabilidade"
        assert proc["status"] == terminal and not proc.get("assigned_indexacao_id")

    async def test_um_processo_sem_validacao_nao_se_decide(self, com_bd, quem_decide):
        com_bd.processes.docs.append({"id": "p-normal", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"})
        with pytest.raises(HTTPException) as erro:
            await quem_decide.run_decidir("process", "p-normal", "validate", None, _com_papel("ceo"))
        assert erro.value.status_code == 400

    def test_esta_por_validar(self):
        from services.financial_validation import esta_por_validar

        assert esta_por_validar({"validacao_financeira": {"estado": "pendente"}}) is True
        assert esta_por_validar({"validacao_financeira": {"estado": "rejeitado"}}) is True
        assert esta_por_validar({"validacao_financeira": {"estado": "validado"}}) is False
        assert esta_por_validar({}) is False, "um processo normal não tem selo"
        assert esta_por_validar({"validacao_financeira": "pendente"}) is False, "tipo errado: sem selo"


class TestNuncaBloqueia:
    """A decisão de produto: um processo não validado trabalha-se até ao fim."""

    def test_nenhum_modulo_do_motor_le_a_validacao_financeira(self):
        """Falha por OMISSÃO para um módulo novo que a leia: ou é um selo
        (apresentação) ou é um travão, e um travão exige uma decisão."""
        permitidos = {
            # O estado e a regra:
            "financial_validation.py", "partner_drafts.py", "partner_attribution.py",
            # Apresentação / projecção de dados (listas da equipa e o DTO):
            "partner_visibility.py", "client_registered.py", "process_service.py",
        }
        leem = []
        for caminho in sorted((BACKEND / "services").glob("*.py")):
            if caminho.name in permitidos:
                continue
            fonte = caminho.read_text(encoding="utf-8")
            if "validacao_financeira" in fonte:
                leem.append(caminho.name)
        assert not leem, f"módulos que referem a validação financeira (travão?): {leem}"

    def test_as_guardas_de_fase_e_de_edicao_nao_a_conhecem(self):
        for nome in ("process_closed_guard.py", "process_kanban_move.py", "process_update.py",
                     "process_assignment.py", "document_visibility.py", "process_indexing.py"):
            assert "validacao_financeira" not in (BACKEND / "services" / nome).read_text(encoding="utf-8"), nome

    def test_o_leitor_do_inventario_le_mesmo_os_modulos(self):
        fonte = (BACKEND / "services" / "financial_validation.py").read_text(encoding="utf-8")
        assert "validacao_financeira" in fonte or "CAMPO_VALIDACAO" in fonte
        assert ast.parse(fonte)


# ════════════════════════════════════════════════════════════════════
#  A expiração (60 dias)
# ════════════════════════════════════════════════════════════════════
def _ha(dias):
    return (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()


@pytest.mark.asyncio
class TestExpiracaoAos60Dias:
    async def test_um_rascunho_parado_ha_61_dias_expira(self, com_bd):
        from services.partner_drafts import expirar_leads_inactivas

        cid = await _lead_retida(com_bd)
        for d in com_bd.partner_drafts.docs:
            d["updated_at"] = d["last_activity_at"] = _ha(61)
        r = await expirar_leads_inactivas()
        assert r["rascunhos"] == 1
        assert com_bd.partner_drafts.docs[0]["partner_stage"] == "expirado" and com_bd.partner_drafts.docs[0]["id"] == cid

    async def test_um_rascunho_com_59_dias_nao_expira(self, com_bd):
        from services.partner_drafts import expirar_leads_inactivas

        await _lead_retida(com_bd)
        for d in com_bd.partner_drafts.docs:
            d["updated_at"] = d["last_activity_at"] = _ha(59)
        assert (await expirar_leads_inactivas())["rascunhos"] == 0
        assert com_bd.partner_drafts.docs[0]["partner_stage"] == "pendente"

    async def test_um_envio_recente_adia_a_expiracao(self, com_bd):
        """Edições e envios contam como actividade: a lead parada em
        `updated_at` mas com um envio de ontem NÃO expira."""
        from services.partner_drafts import expirar_leads_inactivas

        await _lead_retida(com_bd)
        com_bd.partner_drafts.docs[0]["updated_at"] = _ha(90)
        com_bd.partner_drafts.docs[0]["last_activity_at"] = _ha(1)
        assert (await expirar_leads_inactivas())["rascunhos"] == 0

    async def test_enviar_um_ficheiro_regista_actividade(self, com_bd):
        cid = await _lead_retida(com_bd)
        com_bd.partner_drafts.docs[0]["last_activity_at"] = _ha(40)
        await _enviar(com_bd, cid, "Cartao_Cidadao")
        assert com_bd.partner_drafts.docs[0]["last_activity_at"] > _ha(1)

    async def test_uma_lead_na_triagem_parada_expira_e_sai_da_triagem(self, com_bd):
        from services.partner_drafts import expirar_leads_inactivas

        cid = await _lead_retida(com_bd)
        await _enviar(com_bd, cid, COMPROVATIVO)
        lead = next(c for c in com_bd.clients.docs if c["id"] == cid)
        lead["updated_at"] = lead["last_activity_at"] = _ha(61)

        r = await expirar_leads_inactivas()
        assert r["na_triagem"] == 1 and lead["lead_status"] == "expired"

    @pytest.mark.parametrize("campo,valor", [
        ("process_ids", ["p-1"]), ("lead_status", "converted"), ("is_deleted", True),
        ("submitted_by_partner_id", None),
    ])
    async def test_o_que_tem_processo_ou_nao_e_de_parceiro_nunca_se_toca(self, com_bd, campo, valor):
        from services.partner_drafts import expirar_leads_inactivas

        com_bd.clients.docs.append({
            "id": "c-x", "nome": "X", "lead_status": "new", "process_ids": [],
            "submitted_by_partner_id": "pt-1", "updated_at": _ha(200), campo: valor,
        })
        await expirar_leads_inactivas()
        assert com_bd.clients.docs[-1]["lead_status"] in ("new", "converted"), "não foi tocada"

    async def test_e_idempotente(self, com_bd):
        from services.partner_drafts import expirar_leads_inactivas

        await _lead_retida(com_bd)
        com_bd.partner_drafts.docs[0]["updated_at"] = com_bd.partner_drafts.docs[0]["last_activity_at"] = _ha(61)
        primeira = await expirar_leads_inactivas()
        segunda = await expirar_leads_inactivas()
        assert primeira["rascunhos"] == 1 and segunda["rascunhos"] == 0

    async def test_o_parceiro_ve_a_lead_expirada_mas_nao_pode_trabalha_la(self, com_bd):
        import services.partner_portal_read as ppr
        import services.partner_upload_ops as ops
        from services.partner_drafts import expirar_leads_inactivas

        cid = await _lead_retida(com_bd)
        com_bd.partner_drafts.docs[0]["updated_at"] = com_bd.partner_drafts.docs[0]["last_activity_at"] = _ha(61)
        await expirar_leads_inactivas()

        caso = await ppr.run_get_case(PT1, cid)
        assert caso["etapa"] == "expirado" and caso["editavel"] is False
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_upload_url(PT1, cid, ops.PartnerUploadUrlIn(filename="x.pdf"))
        assert erro.value.status_code == 409

    async def test_o_job_agendado_chama_a_expiracao(self):
        fonte = (BACKEND / "services" / "scheduled_tasks.py").read_text(encoding="utf-8")
        assert "expire_stale_partner_leads()" in fonte, "o job não corre: a expiração seria código morto"
        assert "expirar_leads_inactivas" in fonte
