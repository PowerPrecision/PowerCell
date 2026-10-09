"""A guarda de documentos não conhece REDES (D-26, Out 2026).

ONDE ISTO APARECEU
==================
Não estava no enunciado do Bloco 1. Apareceu a medir a D-24: ao verificar
que a parede do S3 (`build_s3_valid_prefixes`) deriva do PROCESSO e não da
rede — e portanto que uma partilha de processo abre os documentos de
graça —, a pergunta seguinte era quem decide se o processo é visível. A
resposta é `document_visibility.user_can_view_process_documents`, e essa
função tem **zero** ocorrências de `network` ou `compan`.

As duas linhas que a abrem:

1. **bypass ABSOLUTO** para `_ADMIN_BYPASS_ROLES` = {admin, ceo,
   **diretor**, administrativo, …}, verificado antes de tudo. O diretor
   de uma ilha é diretor da SUA rede — é a regra 2 do `deadline_scope` e
   a mesma do `visit_scope`. Aqui atravessa.
2. `if not is_document_visibility_restricted(process): return True` — um
   processo **já indexado** é visível a qualquer sessão autenticada. A
   restrição existia para a PRÉ-indexação, não como fronteira de tenant.

E o que está do outro lado não são nomes: é a pasta documental do
cliente — cartão de cidadão, IRS, recibos de vencimento, extractos
bancários. É a fuga de maior consequência de RGPD das que foram medidas
neste eixo, e é alcançável sabendo só um `process_id`.

PORQUE É QUE ESTES TESTES FICAM EM `xfail(strict=True)`
=======================================================
A guarda certa depende da resposta que a **D-25** vier a dar: num
processo em PARTILHA, o lado convidado **tem de ver os documentos** (foi
a decisão de produto: «a ficha inteira do processo»). Escrever aqui uma
fronteira de rede pura fechava a porta que a D-25 precisa de abrir, e
abri-la outra vez depois seria alargar uma parede para caber a
correcção — que é como o Incidente P0 do Portal começou.

Logo: a fuga fica **medida e assinada**, e fecha-se no mesmo lote que dá
ao processo o campo das redes convidadas. `strict=True` é o que impede
isto de ser esquecido: no dia em que a guarda entrar, estes testes
passam, o xpass estrito transforma-se em FALHA e obriga a remover o
marcador. Um `skip` ficava verde para sempre; um teste vermelho parava o
CI.

**Não documentam o comportamento actual.** Afirmam o que tem de ser
verdade; é o marcador que diz que ainda não é.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

#: Um processo da Power, JÁ INDEXADO — que é o estado normal de um
#: processo em curso, e o ramo que abre a porta.
PROCESSO_DA_POWER = {
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


def _casa(fake_db):
    from services import document_visibility

    return _tenant_db(fake_db, document_visibility)


@pytest.mark.xfail(
    strict=True,
    reason="D-26: `user_can_view_process_documents` não conhece redes — "
           "fecha com a D-25, que decide o que o lado convidado vê",
)
def test_um_diretor_de_outra_rede_NAO_ve_os_documentos_do_processo():
    """O bypass absoluto do `diretor` atravessa redes.

    O produto dá ao diretor «acesso total» — à SUA rede. A tolerância de
    cruzamento entre redes é zero.
    """
    from services.document_visibility import user_can_view_process_documents

    assert user_can_view_process_documents(BRUNO, PROCESSO_DA_POWER) is False, (
        "a diretora da Domus lê a pasta documental de um cliente da Power "
        "(cartão de cidadão, IRS, extractos) sabendo só o id do processo"
    )


@pytest.mark.xfail(
    strict=True,
    reason="D-26: um processo indexado é visível a qualquer sessão autenticada",
)
def test_um_consultor_de_outra_rede_tambem_nao():
    """`if not is_document_visibility_restricted(process): return True`.

    A restrição foi escrita para a PRÉ-indexação (o indexador trata os
    documentos antes de haver equipa), não como fronteira de tenant — e
    um processo indexado é o caso NORMAL, não o raro. É a forma do
    `run_get_my_tasks` ao contrário: o ramo restrito é o excepcional, e
    foi por o normal não ter guarda nenhuma que isto passou.
    """
    from services.document_visibility import user_can_view_process_documents

    consultor_da_domus = {
        "id": "u-domus-consultor",
        "email": "c@domus.pt",
        "role": "consultor",
        "company": "Domus",
    }
    assert user_can_view_process_documents(
        consultor_da_domus, PROCESSO_DA_POWER
    ) is False


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="D-26: a guarda async herda a mesma ausência de fronteira",
)
async def test_a_guarda_async_recusa_um_processo_de_outra_rede(db_tenant):  # noqa: F811
    """A guarda que os 11 pontos de `routes/documents.py` chamam.

    403 e não 404 aqui de propósito: ao contrário dos imóveis e das
    visitas, este endpoint já respondeu 404 por «não existe» ANTES de
    chegar à guarda (o `assert_*_by_id` carrega o processo primeiro),
    logo o código não é um oráculo novo.
    """
    from services.document_visibility import assert_can_view_process_documents

    with _casa(db_tenant):
        with pytest.raises(HTTPException) as erro:
            await assert_can_view_process_documents(BRUNO, PROCESSO_DA_POWER)

    assert erro.value.status_code == 403


# ════════════════════════════════════════════════════════════════════
#  A CONTRAPROVA — já verdadeira hoje, e tem de continuar a ser
# ════════════════════════════════════════════════════════════════════
def test_a_power_continua_a_ver_os_documentos_da_POWER():
    """Sem esta linha, «recusar tudo» passava — e é pior do que a fuga:
    uma pasta documental que desaparece pára o processo."""
    from services.document_visibility import user_can_view_process_documents

    assert user_can_view_process_documents(ANA, PROCESSO_DA_POWER) is True


def test_a_rede_da_DOMUS_e_mesmo_outra():
    """Contraprova do cenário: se as duas redes fossem a mesma, os
    testes acima «passariam» sem provar nada."""
    assert REDE_DOMUS != REDE_INCUMBENTE
