"""A EXPLORAÇÃO: o que a Domus vê que não é dela (Out 2026).

Escrito ANTES de qualquer correcção, para morder primeiro. A pergunta é
operacional e tem uma data: a Domus vai começar a trabalhar na
plataforma, e a topologia declarada é «Power + Precision partilham; a
Domus é uma ilha de tolerância zero».

O Lote 4 ergueu o isolamento por REDE e os lotes seguintes foram-no
ligando superfície a superfície (processos, clientes, tarefas, Kanban,
pesquisa, calendário, alertas, visitas, webmail, explorador de
ficheiros). Estes testes percorrem o que ficou **fora** desse
inventário, e são três colecções com dados de cliente:

1. `db.properties` — a carteira de angariações. Sem fronteira NENHUMA,
   na listagem e no `find_one` (a forma do `run_delete_deadline`: a
   rota autoriza o VERBO, não o OBJECTO). O documento leva
   `owner.name`, `owner.phone`, `owner.email` e `owner.nif`.
2. `client_match` — o Smart Match. Consulta `db.processes` com
   `{"status": {"$nin": [...]}}` e devolve `client_name`,
   `client_email` e `client_phone`. É a ponte: um imóvel de uma rede
   devolve os clientes de TODAS.
3. `db.process_finances` — `GET /finance/processes`. O `company_id` é
   um filtro OPCIONAL da query string, não uma fronteira: sem ele a
   consulta é `{}`. É o placebo do `build_company_scope_condition`
   outra vez — um parâmetro que o cliente escolhe nunca é uma parede.

Nenhuma destas tinha entrada em `TECHNICAL_DEBT.md`: não foram decisões
adiadas, foram superfícies por inventariar. Hoje são a **D-24**.

PORQUE É QUE ESTES TESTES ESTÃO `xfail(strict=True)`
====================================================
As quatro fugas estão PROVADAS e ainda não corrigidas — a correcção
depende de uma decisão de produto que vem a seguir (o que é que cada
lado vê num processo em PARTILHA entre a Domus e a Precision), e
escrever a fronteira antes dessa resposta é escrever a fronteira errada.

`strict=True` é o que impede isto de ser esquecido: no dia em que a
guarda entrar, o teste passa, o `xfail` estrito transforma esse
**xpass em FALHA** e obriga a remover o marcador. Um `skip` ficava
verde para sempre e um teste vermelho parava o CI — esta é a única das
três formas que envelhece bem.

**Não são testes a documentar o comportamento actual.** Afirmam o que
tem de ser verdade; é o marcador que diz que ainda não é.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "rede:domus"


def _utilizador_da_domus() -> dict:
    return {
        "id": "u-domus",
        "name": "Diretora da Domus",
        "role": "diretor",
        "company": "Domus",
        "active_company_id": "c-domus",
    }


# ====================================================================
# 1. A CARTEIRA DE ANGARIAÇÕES
# ====================================================================

@pytest.mark.xfail(strict=True, reason="D-24: `db.properties` não tem fronteira de rede (listagem)")
@pytest.mark.asyncio
async def test_a_listagem_de_imoveis_nao_atravessa_redes(fake_async_db):
    """Um imóvel da Power não pode aparecer à Domus.

    O `PropertyListItem` leva `client_name`: a listagem sozinha já
    entrega o nome do cliente da outra rede, antes de se abrir um
    imóvel.
    """
    from services import property_list

    await fake_async_db.properties.insert_one({
        "id": "imo-power",
        "internal_reference": "IMO-001",
        "title": "T3 em Cascais",
        "property_type": "apartamento",
        "status": "disponivel",
        "financials": {"asking_price": 420000.0},
        "address": {"district": "Lisboa", "municipality": "Cascais"},
        "features": {"bedrooms": 3},
        "owner": {
            "name": "Proprietário da Power",
            "phone": "912345678",
            "email": "dono@exemplo.pt",
            "nif": "123456789",
        },
        "client_name": "Ana Martins",
        "network_id": REDE_POWER,
        "created_at": "2026-10-01T10:00:00Z",
    })

    with patch.object(property_list, "db", fake_async_db):
        visiveis = await property_list.run_list_properties(_utilizador_da_domus())

    titulos = [getattr(p, "title", None) for p in visiveis]
    assert titulos == [], (
        "a Domus vê a carteira de angariações da Power: "
        f"{titulos} (e o item de listagem leva `client_name`)"
    )


@pytest.mark.xfail(strict=True, reason="D-24: `run_get_property` é um `find_one` por id, sem posse")
@pytest.mark.asyncio
async def test_abrir_um_imovel_de_outra_rede_responde_404(fake_async_db):
    """E o `find_one` por id entrega o `owner` completo: nome, telefone,
    email e **NIF** do proprietário de outra rede.

    404 e nunca 403 — distinguir «não existe» de «não é teu» confirma o
    id a quem adivinha (precedente das notificações e do calendário).
    """
    from fastapi import HTTPException

    from services import property_crud

    # O documento tem de ser VÁLIDO para o modelo `Property`: com um
    # fixture incompleto o teste falha com `ValidationError` e passa a
    # provar que o Pydantic valida — não que a guarda existe.
    await fake_async_db.properties.insert_one({
        "id": "imo-power",
        "title": "T3 em Cascais",
        "property_type": "apartamento",
        "condition": "bom",
        "status": "disponivel",
        "financials": {"asking_price": 420000.0},
        "address": {"district": "Lisboa", "municipality": "Cascais", "locality": "Cascais"},
        "owner": {"name": "Dono da Power", "nif": "123456789", "phone": "912345678"},
        "network_id": REDE_POWER,
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })

    with patch.object(property_crud, "db", fake_async_db):
        try:
            imovel = await property_crud.run_get_property(
                "imo-power", _utilizador_da_domus()
            )
        except HTTPException as erro:
            assert erro.status_code == 404, f"esperava 404, veio {erro.status_code}"
            return

    pytest.fail(
        "a Domus abriu um imóvel da Power e recebeu o proprietário: "
        f"nome={imovel.owner.name!r} nif={imovel.owner.nif!r} "
        f"telefone={imovel.owner.phone!r}"
    )


# ====================================================================
# 2. O SMART MATCH — a ponte entre as duas pontas
# ====================================================================

@pytest.mark.xfail(strict=True, reason="D-24: o Smart Match cruza `properties` x `processes` sem âmbito")
@pytest.mark.asyncio
async def test_o_match_de_um_imovel_nao_devolve_clientes_de_outra_rede(fake_async_db):
    """A pior das três: é um JOIN entre colecções, nenhuma delas filtrada.

    `find_matching_clients_for_property` consulta `db.processes` por
    ESTADO e devolve `client_name`, `client_email` e `client_phone`.
    Alcançável por `GET /match/property/{id}/clients` **e** pelo
    `check_and_notify_matches_for_new_property`, que manda o resultado
    por EMAIL ao agente — uma fuga que sai do sistema.
    """
    from services import client_match

    await fake_async_db.properties.insert_one({
        "id": "imo-domus",
        "title": "T2 em Leiria",
        "financials": {"asking_price": 200000.0},
        "address": {"district": "Leiria", "municipality": "Leiria"},
        "features": {"bedrooms": 2},
        "network_id": REDE_DOMUS,
    })
    await fake_async_db.processes.insert_one({
        "id": "proc-power",
        "client_name": "Ana Martins",
        "client_email": "ana@exemplo.pt",
        "client_phone": "912345678",
        "status": "em_analise",
        "financial_data": {"valor_pretendido": "210000"},
        "real_estate_data": {"distrito": "Leiria", "concelho": "Leiria", "tipologia": "T2"},
        "network_id": REDE_POWER,
    })

    with patch.object(client_match, "db", fake_async_db):
        matches = await client_match.find_matching_clients_for_property("imo-domus")

    nomes = [m.get("process", {}).get("client_name") for m in matches]
    assert nomes == [], (
        "o Smart Match de um imóvel da Domus devolve clientes da Power "
        f"com nome, email e telefone: {nomes}"
    )


# ====================================================================
# 3. OS REGISTOS FINANCEIROS
# ====================================================================

@pytest.mark.xfail(strict=True, reason="D-24: `GET /finance/processes` usa o `company_id` da query como filtro, não como fronteira")
@pytest.mark.asyncio
async def test_a_listagem_financeira_nao_atravessa_redes(fake_async_db):
    """`GET /finance/processes` sem `company_id` consulta `{}`.

    E o `company_id` da query string é um FILTRO escolhido por quem
    pergunta, não uma fronteira: os `FINANCE_READ_ROLES` incluem
    `consultor`, `administrativo` e `indexacao`.
    """
    from services import finance_process_records

    await fake_async_db.process_finances.insert_one({
        "id": "fin-power",
        "process_id": "proc-power",
        "client_id": "cli-power",
        "company_id": "c-power",
        "client_name": "Ana Martins",
        "expected_value": 4200.0,
        "status": "pendente",
        "network_id": REDE_POWER,
    })

    with patch.object(finance_process_records, "db", fake_async_db):
        resposta = await finance_process_records.run_list_process_finances(
            None, None, None, None, _utilizador_da_domus()
        )

    assert resposta["finances"] == [], (
        "a Domus lê os registos financeiros da Power: "
        f"{[f.get('id') for f in resposta['finances']]}"
    )
