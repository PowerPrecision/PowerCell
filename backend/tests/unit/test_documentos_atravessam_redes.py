"""A guarda de documentos não conhecia REDES (D-26, fechada com a D-25).

ONDE ISTO APARECEU
==================
Não estava em enunciado nenhum. Apareceu a medir a D-24: ao verificar que
a parede do S3 (`build_s3_valid_prefixes`) deriva do PROCESSO e não da
rede — e portanto que uma partilha de processo abre os documentos de
graça —, a pergunta seguinte era quem decide se o processo é visível. A
resposta é `document_visibility.user_can_view_process_documents`, e essa
função tinha **zero** ocorrências de `network` ou `compan`.

As duas linhas que a abriam:

1. **bypass ABSOLUTO** para `_ADMIN_BYPASS_ROLES` = {admin, ceo,
   **diretor**, administrativo, …}, verificado antes de tudo. O diretor
   de uma ilha é diretor da SUA rede — é a regra 2 do `deadline_scope` e
   a mesma do `visit_scope`.
2. `if not is_document_visibility_restricted(process): return True` — um
   processo **já indexado** era visível a qualquer sessão autenticada. A
   restrição foi escrita para a PRÉ-indexação, não como fronteira de
   tenant, e indexado é o caso NORMAL: é a forma do `run_get_my_tasks`
   ao contrário — foi o ramo COMUM não ter guarda nenhuma que o
   escondeu.

E o que estava do outro lado não eram nomes: era a pasta documental do
cliente — cartão de cidadão, IRS, recibos de vencimento, extractos
bancários. Bastava saber um `process_id`.

A FRONTEIRA ENTRA **ANTES** DO BYPASS
=====================================
Um bypass de cargo que corra primeiro é um bypass de rede. É por isso
que o teste do diretor existe: é o papel que o produto trata como «acesso
total», e é precisamente nele que a ordem se nota.

E usa o `processo_no_ambito`, não o `documento_no_ambito`: um processo
PARTILHADO abre-se ao convidado, que é a decisão de produto da D-25 («a
ficha inteira»). Era por isto que esta dívida não podia fechar sozinha —
uma fronteira de rede pura fechava a porta que a partilha precisa de
abrir.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.document_visibility import (
    assert_can_view_process_documents,
    can_manage_process_documents,
    processo_fora_da_rede,
    user_can_view_process_documents,
)
from services.tenant_network import TenantScope
from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

AMBITO_DA_POWER = TenantScope(
    network_ids=(REDE_INCUMBENTE,), company_ids=("cmp-power",),
)
AMBITO_DA_DOMUS = TenantScope(
    network_ids=(REDE_DOMUS,), company_ids=("cmp-domus",),
)

CONSULTOR_DA_DOMUS = {
    "id": "u-domus-consultor",
    "email": "c@domus.pt",
    "role": "consultor",
    "company": "Domus",
}


def _processo(**kw) -> dict:
    """Um processo da Power, JÁ INDEXADO — o estado NORMAL de um processo
    em curso, e o ramo que abria a porta."""
    base = {
        "id": "p-power",
        "client_id": "c-power",
        "client_name": "Cliente da Power",
        "status": "em_analise",
        "is_indexed": True,
        "indexed_at": "2026-09-01T10:00:00Z",
        "s3_folder": "Documentação Clientes/c-power",
        "network_id": REDE_INCUMBENTE,
        "company_id": "cmp-power",
    }
    base.update(kw)
    return base


def _casa(fake_db):
    from services import document_visibility

    return _tenant_db(fake_db, document_visibility)


# ════════════════════════════════════════════════════════════════════
#  O ATAQUE
# ════════════════════════════════════════════════════════════════════
class TestAExploracao:

    def test_um_diretor_de_outra_rede_NAO_ve_os_documentos(self):
        """O bypass absoluto do `diretor` atravessava redes.

        O produto dá ao diretor «acesso total» — à SUA rede. A tolerância
        de cruzamento entre redes é zero.
        """
        assert user_can_view_process_documents(
            BRUNO, _processo(), scope=AMBITO_DA_DOMUS
        ) is False, (
            "a diretora da Domus lê a pasta documental de um cliente da "
            "Power sabendo só o id do processo"
        )

    def test_um_consultor_de_outra_rede_tambem_nao(self):
        """`if not is_document_visibility_restricted(process): return True`."""
        assert user_can_view_process_documents(
            CONSULTOR_DA_DOMUS, _processo(), scope=AMBITO_DA_DOMUS
        ) is False

    def test_a_GESTAO_dos_documentos_tambem_nao_atravessa(self):
        """Renomear, organizar, categorizar: é ESCRITA, e tinha o mesmo
        bypass. Duas funções, a mesma lacuna — corrigir só a leitura
        deixava a metade que muda ficheiros aberta."""
        assert can_manage_process_documents(
            BRUNO, _processo(), scope=AMBITO_DA_DOMUS
        ) is False

    def test_a_ATRIBUICAO_a_um_processo_de_outra_rede_nao_vale(self):
        """Um desfasamento de dados (`assignment_drift`) não é uma
        autorização. É a mesma regra do `_processos_visiveis`: a condição
        de rede entra SEMPRE, mesmo para quem está atribuído."""
        processo = _processo(assigned_consultor_ids=[CONSULTOR_DA_DOMUS["id"]])
        assert user_can_view_process_documents(
            CONSULTOR_DA_DOMUS, processo, scope=AMBITO_DA_DOMUS
        ) is False

    @pytest.mark.asyncio
    async def test_a_guarda_async_responde_403(self, db_tenant):  # noqa: F811
        """A guarda que os 11 pontos de `routes/documents.py` chamam.

        403 e não 404 aqui de propósito: ao contrário dos imóveis e das
        visitas, o `assert_*_by_id` carrega o processo e responde 404 por
        «não existe» ANTES de chegar aqui, logo o código não é um oráculo
        novo. E o 403 é o que o `skipErrorToast` da `ClientDetailPage` já
        sabe tratar.
        """
        with _casa(db_tenant):
            with pytest.raises(HTTPException) as erro:
                await assert_can_view_process_documents(BRUNO, _processo())

        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_fronteira_recusa_ANTES_do_allow_path_do_cliente(
        self, db_tenant,  # noqa: F811
    ):
        """O allow-path por relação com o cliente faz I/O e responderia a
        «este cliente existe?». Um processo de outra rede recusa-se antes
        — a ordem das verificações é a regra do Incidente P0 do Portal.
        """
        from services import document_visibility

        chamadas: list = []

        async def _espia(user, client_id):
            chamadas.append(client_id)
            return True  # diria SIM, se fosse consultado

        with _casa(db_tenant):
            with patch.object(
                document_visibility, "_user_related_to_client", _espia
            ):
                with pytest.raises(HTTPException):
                    await assert_can_view_process_documents(BRUNO, _processo())

        assert chamadas == [], (
            "o allow-path do cliente foi consultado para um processo de "
            f"outra rede: {chamadas}"
        )


# ════════════════════════════════════════════════════════════════════
#  A PARTILHA ABRE A PORTA (D-25) — e é por isto que as duas andam juntas
# ════════════════════════════════════════════════════════════════════
class TestOProcessoPartilhado:

    def test_o_convidado_VE_os_documentos_do_processo_partilhado(self):
        """A decisão de produto é «a ficha inteira do processo». Sem esta
        linha, a correcção da D-26 fechava a porta que a D-25 abre."""
        partilhado = _processo(partner_network_ids=[REDE_DOMUS])
        assert user_can_view_process_documents(
            BRUNO, partilhado, scope=AMBITO_DA_DOMUS
        ) is True

    def test_e_pode_ORGANIZAR_os_documentos_desse_processo(self):
        partilhado = _processo(
            partner_network_ids=[REDE_DOMUS],
            assigned_consultor_ids=[CONSULTOR_DA_DOMUS["id"]],
        )
        assert can_manage_process_documents(
            CONSULTOR_DA_DOMUS, partilhado, scope=AMBITO_DA_DOMUS
        ) is True

    def test_a_partilha_de_UM_processo_nao_abre_os_OUTROS(self):
        """É a diferença entre isto e o atalho do UCR nas duas empresas:
        lá o âmbito é do UTILIZADOR e abre a rede inteira."""
        outro = _processo(id="p-power-2", partner_network_ids=[])
        assert user_can_view_process_documents(
            BRUNO, outro, scope=AMBITO_DA_DOMUS
        ) is False


# ════════════════════════════════════════════════════════════════════
#  A CONTRAPROVA — sem isto, «recusar tudo» passava
# ════════════════════════════════════════════════════════════════════
class TestOQueNAOSeFecha:

    def test_a_power_continua_a_ver_os_documentos_da_POWER(self):
        """Uma pasta documental que desaparece pára o processo — e é pior
        do que a fuga, porque ninguém suspeita de uma guarda."""
        assert user_can_view_process_documents(
            ANA, _processo(), scope=AMBITO_DA_POWER
        ) is True

    def test_a_PRECISION_tambem(self):
        """Mesma rede, empresa diferente: a rede é a fronteira, a empresa
        é uma vista."""
        da_precision = TenantScope(
            network_ids=(REDE_INCUMBENTE,), company_ids=("cmp-precision",),
        )
        assert user_can_view_process_documents(
            {"id": "u-carla", "role": "consultor"},
            _processo(assigned_consultor_ids=["u-carla"]),
            scope=da_precision,
        ) is True

    def test_sem_AMBITO_a_fronteira_nao_se_aplica(self):
        """`scope=None` é «não sei» e mantém as puras utilizáveis por quem
        não o tem. A parede real está nas guardas `async`, que o resolvem
        sempre — e há uma guarda sobre a fonte a afirmá-lo."""
        assert processo_fora_da_rede(_processo(), None) is False
        assert user_can_view_process_documents(BRUNO, _processo()) is True

    @pytest.mark.asyncio
    async def test_as_guardas_async_RESOLVEM_mesmo_o_ambito(self, db_tenant):  # noqa: F811
        """A contraprova da guarda de fonte: sem isto, apagar a resolução
        satisfazia o inventário e desligava a parede."""
        from services import document_visibility

        pedidos: list = []
        original = document_visibility._ambito_do_utilizador

        async def _espia(user):
            pedidos.append((user or {}).get("id"))
            return await original(user)

        with _casa(db_tenant):
            with patch.object(document_visibility, "_ambito_do_utilizador", _espia):
                await assert_can_view_process_documents(ANA, _processo())

        assert pedidos == [ANA["id"]]

    @pytest.mark.asyncio
    async def test_o_ambito_falha_FECHADO(self, db_tenant):  # noqa: F811
        """Sem âmbito resolvido, a fronteira RECUSA. Devolver `None` era a
        saída cómoda e desligava a parede por causa de um soluço."""
        from services import document_visibility

        async def _rebenta(_user):
            raise RuntimeError("Mongo em baixo")

        with _casa(db_tenant):
            with patch(
                "services.tenant_network.resolve_tenant_scope", _rebenta
            ):
                ambito = await document_visibility._ambito_do_utilizador(ANA)

        assert ambito.network_ids == ()
        assert processo_fora_da_rede(_processo(), ambito) is True


# ════════════════════════════════════════════════════════════════════
#  GUARDA SOBRE A FONTE
# ════════════════════════════════════════════════════════════════════
def test_as_guardas_async_passam_o_ambito_as_puras():
    """Uma pura chamada SEM âmbito dentro de uma guarda `async` é a
    parede desligada — e é uma linha que passa em qualquer revisão."""
    from services import document_visibility
    from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

    for nome in (
        "assert_can_view_process_documents",
        "exigir_gestao_de_documentos",
    ):
        corpo = codigo_da_funcao_sem_comentarios(
            getattr(document_visibility, nome)
        )
        assert "_ambito_do_utilizador" in corpo, (
            f"`{nome}` não resolve o âmbito de rede"
        )
        assert "scope=" in corpo, (
            f"`{nome}` resolve o âmbito e não o PASSA à função pura"
        )

