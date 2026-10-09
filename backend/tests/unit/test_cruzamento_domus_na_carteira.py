"""A EXPLORAÇÃO, e o seu fecho: o que a Domus via que não era dela (D-24).

A pergunta era operacional e tinha uma data: a Domus ia começar a
trabalhar na plataforma, e a topologia declarada é «Power + Precision
partilham; a Domus é uma ilha de tolerância zero».

O Lote 4 ergueu o isolamento por REDE e os lotes seguintes foram-no
ligando superfície a superfície (processos, clientes, tarefas, Kanban,
pesquisa, calendário, alertas, visitas, webmail, explorador de
ficheiros). Estes testes percorrem o que ficou **fora** desse
inventário — e o inventário à mão tinha QUATRO funções, enquanto a
medição deu **duas colecções inteiras**:

1. `db.properties` — a carteira de angariações. Doze módulos, ZERO
   ocorrências de `compan` ou `network`. O documento leva `owner.name`,
   `owner.phone`, `owner.email` e `owner.nif`, e `client_name` viaja já
   no item de LISTAGEM. Sem fronteira na listagem, nas estatísticas, no
   `find_one`, na edição, no estado, nos documentos, nas fotos, no
   interessado, na visita — e o `delete` era `delete_one({"id": ...})`.
2. `client_match` — o Smart Match. É um JOIN e nenhuma das pontas
   estava filtrada. Alcançável por `GET /match/property/{id}/clients`
   **e** pelo `check_and_notify_matches_for_new_property`, que manda o
   resultado por EMAIL: uma fuga que SAI do sistema.
3. `db.process_finances` — `GET /finance/processes`. O `company_id` era
   um filtro OPCIONAL da query string e sem ele a consulta era `{}`. Um
   parâmetro escolhido por quem pergunta nunca é uma parede: é o placebo
   do `build_company_scope_condition` outra vez.

E a QUARTA forma do defeito, que não estava no enunciado: o **DESTINO**.
`run_add_interested_client` e `run_register_visit` recebem um
`client_id` que é um **process_id**, leem `db.processes` e gravam o
`client_name` que lá encontram dentro do imóvel. Quem soubesse um id de
processo da Power copiava o nome do cliente para a sua carteira — e
ficava lá escrito.

`TestAExploracao` é o ataque, e foi escrito antes da correcção (vivia em
`xfail(strict=True)`; os quatro passaram a XPASS no momento em que a
guarda entrou, que é exactamente o que o marcador estrito existe para
forçar). `TestOQueNAOSeFecha` é a contraprova: sem ela, «não devolver
nada a ninguém» passava, e é pior do que a fuga.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    CARLA,
    ORFAO,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    rede_de_omissao_incumbente,  # noqa: F401  (fixture)
    semear as _semear,
    tenant_db as _tenant_db,
)

# ────────────────────────────────────────────────────────────────────
#  O CENÁRIO
# ────────────────────────────────────────────────────────────────────
# Reutiliza as empresas, UCRs e processos do `helpers_tenant`: duas
# redes, três empresas, a Carla a trabalhar nas duas. Uma segunda versão
# do mesmo cenário divergiria, e metade destes testes passaria a provar
# outra coisa.


def _imovel(**kw) -> dict:
    """Um imóvel VÁLIDO para o modelo `Property`.

    Com um fixture incompleto o teste falha com `ValidationError` e
    passa a provar que o Pydantic valida — não que a guarda existe. Foi
    o que aconteceu na primeira versão deste ficheiro.
    """
    base = {
        "id": "imo-power",
        "internal_reference": "IMO-001",
        "title": "T3 em Cascais",
        "property_type": "apartamento",
        "condition": "bom",
        "status": "disponivel",
        "financials": {"asking_price": 420000.0},
        "address": {
            "district": "Lisboa",
            "municipality": "Cascais",
            "locality": "Cascais",
        },
        "features": {"bedrooms": 3, "useful_area": 120.0},
        "owner": {
            "name": "Dono da Power",
            "phone": "912345678",
            "email": "dono@exemplo.pt",
            "nif": "123456789",
        },
        "client_name": "Cliente da Power",
        "process_id": "p-power",
        "network_id": REDE_INCUMBENTE,
        "company_id": "cmp-power",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    }
    base.update(kw)
    return base


def _imovel_da_domus(**kw) -> dict:
    return _imovel(
        id="imo-domus",
        internal_reference="IMO-900",
        title="T2 em Leiria",
        client_name="Cliente da Domus",
        process_id="p-domus",
        network_id=REDE_DOMUS,
        company_id="cmp-domus",
        owner={"name": "Dono da Domus", "phone": "911111111", "nif": "999999999"},
        **kw,
    )


def _registo_financeiro(**kw) -> dict:
    base = {
        "id": "fin-power",
        "process_id": "p-power",
        "client_id": "c-power",
        "company_id": "cmp-power",
        "client_name": "Cliente da Power",
        "expected_value": 420000.0,
        "expected_commission": 4200.0,
        "total_with_tax": 5166.0,
        "status": "pending",
    }
    base.update(kw)
    return base


@pytest.fixture
def carteira(db_tenant):  # noqa: F811
    """O cenário multi-tenant + uma angariação de cada rede."""
    db_tenant.properties.docs.append(_imovel())
    db_tenant.properties.docs.append(_imovel_da_domus())
    db_tenant.process_finances.docs.append(_registo_financeiro())
    db_tenant.process_finances.docs.append(
        _registo_financeiro(
            id="fin-domus", process_id="p-domus", client_id="c-domus",
            company_id="cmp-domus", client_name="Cliente da Domus",
        )
    )
    return db_tenant


def _modulos_dos_imoveis():
    from services import (
        alerts,
        client_match,
        finance_process_records,
        match_api_smart,
        portal_recommendations,
        property_crud,
        property_documents,
        property_engagement,
        property_helpers,
        property_list,
    )

    return (
        property_list, property_crud, property_engagement, property_documents,
        # `property_helpers.get_next_reference` importa `db` no topo e é
        # chamado na CRIAÇÃO: sem ele a cadeia fala com o proxy real e o
        # teste rebenta com "Event loop is closed" — um vermelho a
        # apontar para o isolamento quando o problema é o `db`.
        property_helpers,
        client_match, match_api_smart, portal_recommendations,
        finance_process_records, alerts,
    )


def _casa_de_imoveis(fake_db):
    """A cadeia COMPLETA de `db` — a de tenant e a dos nove módulos.

    Patchar só um dos dois lados deixa metade da cadeia a falar com o
    proxy real: o resultado passa ou falha conforme a ORDEM de recolha
    do pytest, e a fuga fica provada por degradação em vez de por regra
    (ver AGENTS.md, «from database import db ao nível do módulo»).
    """
    return _tenant_db(fake_db, *_modulos_dos_imoveis())


# ════════════════════════════════════════════════════════════════════
#  O ATAQUE
# ════════════════════════════════════════════════════════════════════
class TestAExploracao:
    """Cada um destes devolvia dados de outra rede antes da D-24."""

    # ── 1. A CARTEIRA ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_a_listagem_de_imoveis_nao_atravessa_redes(self, carteira):
        """O `PropertyListItem` leva `client_name`: a listagem sozinha
        entregava o nome do cliente da outra rede, antes de se abrir um
        imóvel."""
        from services import property_list

        with _casa_de_imoveis(carteira):
            visiveis = await property_list.run_list_properties(BRUNO)

        assert [p.title for p in visiveis] == ["T2 em Leiria"], (
            "a Domus vê a carteira da Power: "
            f"{[(p.title, p.client_name) for p in visiveis]}"
        )

    @pytest.mark.asyncio
    async def test_as_estatisticas_da_carteira_nao_somam_outras_redes(self, carteira):
        """`count_documents({})` + `$group` sem `$match`: a Domus lia o
        VALOR da carteira do grupo, sem precisar de abrir um imóvel.

        A soma (`$sum` sobre `financials.asking_price`) **não** se
        afirma aqui: o duplo de Mongo não agrega caminhos com ponto e
        devolveria 0 com a correcção presente OU ausente — uma asserção
        que passa sem provar nada é pior do que não existir. O que se
        mede é a CONTAGEM (que o duplo faz) e, no teste seguinte, a
        ORDEM das etapas, que é a propriedade que eu escrevi.
        """
        from services import property_list

        with _casa_de_imoveis(carteira):
            stats = await property_list.run_get_property_stats(BRUNO)

        assert stats["total"] == 1, (
            f"a Domus conta {stats['total']} imóveis; só um é dela"
        )
        assert stats["by_status"]["disponivel"]["count"] == 1

    @pytest.mark.asyncio
    async def test_o_MATCH_entra_antes_do_group(self, carteira):
        """Agregar primeiro e filtrar depois somaria o valor das outras
        redes para o descartar a seguir — e o `total` sairia errado de
        qualquer maneira. A etapa 0 é o `$match`."""
        from services import property_list

        etapas: list = []
        original = carteira.properties.aggregate

        def _espia(pipeline, *a, **kw):
            etapas.append(pipeline)
            return original(pipeline, *a, **kw)

        with _casa_de_imoveis(carteira):
            with patch.object(carteira.properties, "aggregate", _espia):
                await property_list.run_get_property_stats(BRUNO)

        assert etapas, "o pipeline não foi executado"
        primeira = etapas[0][0]
        assert "$match" in primeira, (
            f"a primeira etapa não é um `$match`: {primeira}"
        )
        assert REDE_DOMUS in str(primeira), (
            f"o `$match` não leva a rede do utilizador: {primeira}"
        )

    @pytest.mark.asyncio
    async def test_abrir_um_imovel_de_outra_rede_responde_404(self, carteira):
        """O `find_one` por id entregava o `owner` completo: nome,
        telefone, email e **NIF** do proprietário.

        404 e nunca 403 — distinguir «não existe» de «não é teu»
        confirma o id a quem adivinha (precedente das notificações, do
        calendário e das visitas)."""
        from services import property_crud

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                imovel = await property_crud.run_get_property("imo-power", BRUNO)
                pytest.fail(
                    "a Domus abriu um imóvel da Power e recebeu o "
                    f"proprietário: nome={imovel.owner.name!r} "
                    f"nif={imovel.owner.nif!r} telefone={imovel.owner.phone!r}"
                )

        assert erro.value.status_code == 404
        assert erro.value.detail == "Imóvel não encontrado"

    @pytest.mark.asyncio
    async def test_editar_um_imovel_de_outra_rede_responde_404(self, carteira):
        from models.property import PropertyUpdate
        from services import property_crud

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await property_crud.run_update_property(
                    "imo-power", PropertyUpdate(title="Mudei o título"), BRUNO,
                )

        assert erro.value.status_code == 404
        # E nada mudou.
        assert carteira.properties.docs[0]["title"] == "T3 em Cascais"

    @pytest.mark.asyncio
    async def test_APAGAR_um_imovel_de_outra_rede_responde_404(self, carteira):
        """Era `delete_one({"id": property_id})` e mais nada — o
        `run_delete_deadline` do Lote 7 com outro nome."""
        from services import property_crud

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await property_crud.run_delete_property("imo-power", BRUNO)

        assert erro.value.status_code == 404
        assert {d["id"] for d in carteira.properties.docs} == {
            "imo-power", "imo-domus",
        }, "o imóvel da Power foi apagado por alguém de outra rede"

    @pytest.mark.asyncio
    async def test_mudar_o_estado_de_um_imovel_de_outra_rede_responde_404(self, carteira):
        from models.property import PropertyStatus
        from services import property_crud

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await property_crud.run_update_property_status(
                    "imo-power", PropertyStatus.VENDIDO, BRUNO,
                )

        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_os_documentos_de_um_imovel_de_outra_rede_respondem_404(self, carteira):
        """Caderneta predial, certidão de registo, CPCV."""
        from services import property_documents

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await property_documents.run_get_property_documents(
                    "imo-power", BRUNO,
                )

        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_projeccao_RESTRITA_nao_cega_a_guarda(self, carteira):
        """`run_get_interested_clients` lia o imóvel com
        `{"interested_clients": 1}`.

        **Uma projecção que deixa o carimbo de fora cega a guarda**: o
        documento chega sem rede, conta como legado e a guarda ABRE em
        vez de fechar. É a família da lição do `get_file_content` —
        inspeccionar uma coisa e decidir sobre outra.
        """
        from services import property_engagement

        carteira.properties.docs[0]["interested_clients"] = ["p-power"]

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await property_engagement.run_get_interested_clients(
                    "imo-power", BRUNO,
                )

        assert erro.value.status_code == 404

    # ── 2. O DESTINO ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_nao_se_registam_visitas_com_um_processo_de_outra_rede(self, carteira):
        """A pergunta do DESTINO: o `client_name` do processo ia ser
        GRAVADO no histórico do imóvel da Domus."""
        from services import property_engagement

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await property_engagement.run_register_visit(
                    "imo-domus", BRUNO, client_id="p-power",
                )

        assert erro.value.status_code == 404
        historico = carteira.properties.docs[1].get("history") or []
        assert not any("Cliente da Power" in str(h) for h in historico), (
            "o nome do cliente da Power ficou gravado no imóvel da Domus"
        )

    @pytest.mark.asyncio
    async def test_nao_se_adiciona_um_interessado_de_outra_rede(self, carteira):
        from services import property_engagement

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await property_engagement.run_add_interested_client(
                    "imo-domus", "p-power", BRUNO,
                )

        assert erro.value.status_code == 404
        assert "p-power" not in (
            carteira.properties.docs[1].get("interested_clients") or []
        )

    # ── 3. O SMART MATCH ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_o_match_de_um_imovel_nao_devolve_clientes_de_outra_rede(self, carteira):
        """A pior das três: um JOIN sem âmbito em nenhuma das pontas.

        Devolve `client_name`, `client_email` e `client_phone`, e é este
        resultado que o `notify_property_match` manda por EMAIL.
        """
        from services import client_match

        carteira.processes.docs.append({
            "id": "p-power-activo",
            "client_name": "Ana da Power",
            "client_email": "ana@power.pt",
            "client_phone": "912345678",
            "status": "em_analise",
            "financial_data": {"valor_pretendido": "210000"},
            "real_estate_data": {
                "distrito": "Leiria", "concelho": "Leiria", "tipologia": "T2",
            },
            "network_id": REDE_INCUMBENTE,
            "company_id": "cmp-power",
        })

        with _casa_de_imoveis(carteira):
            matches = await client_match.find_matching_clients_for_property(
                "imo-domus"
            )

        nomes = [m.get("process", {}).get("client_name") for m in matches]
        assert nomes == [], (
            "o Smart Match de um imóvel da Domus devolve clientes da "
            f"Power com nome, email e telefone: {nomes}"
        )

    @pytest.mark.asyncio
    async def test_o_match_de_um_processo_nao_devolve_imoveis_de_outra_rede(self, carteira):
        """O sentido inverso: a carteira da Power recomendada a um
        processo da Domus."""
        from services import client_match

        carteira.processes.docs.append({
            "id": "p-domus-comprador",
            "client_name": "Cliente da Domus",
            "status": "em_analise",
            "financial_data": {"valor_pretendido": "500000"},
            "real_estate_data": {
                "distrito": "Lisboa", "concelho": "Cascais", "tipologia": "T3",
            },
            "network_id": REDE_DOMUS,
            "company_id": "cmp-domus",
        })

        with _casa_de_imoveis(carteira):
            matches = await client_match.find_matching_properties_for_client(
                "p-domus-comprador"
            )

        encontrados = [m.get("property", {}).get("id") for m in matches]
        assert "imo-power" not in encontrados, (
            f"um processo da Domus recebeu imóveis da Power: {encontrados}"
        )
        # E a contraprova no mesmo teste: o match continua a funcionar
        # DENTRO da rede. Sem esta linha, "não devolver nada" passava.
        assert "imo-domus" in encontrados, (
            f"o match deixou de encontrar o imóvel da própria rede: {encontrados}"
        )

    @pytest.mark.asyncio
    async def test_o_smart_match_do_endpoint_tambem_nao_atravessa(self, carteira):
        """`match_api_smart` tem a sua PRÓPRIA query — é a lição do
        `build_kanban_query`: um ponto único para a condição não chega,
        é preciso inventariar as superfícies."""
        from services import match_api_smart

        carteira.processes.docs.append({
            "id": "p-domus-comprador",
            "client_name": "Cliente da Domus",
            "process_type": "compra",
            "status": "em_analise",
            "real_estate_data": {
                "distrito": "Lisboa", "concelho": "Cascais",
                "tipologia": "T3", "valor_imovel": "500000",
            },
            "network_id": REDE_DOMUS,
            "company_id": "cmp-domus",
        })

        with _casa_de_imoveis(carteira):
            resposta = await match_api_smart.run_smart_match_for_process(
                "p-domus-comprador", BRUNO,
            )

        encontrados = {
            m.get("property", {}).get("id") or m.get("id")
            for m in (resposta.get("matches") or [])
        }
        assert "imo-power" not in encontrados, (
            f"o Smart Match trouxe um imóvel da Power: {encontrados}"
        )

    @pytest.mark.asyncio
    async def test_as_recomendacoes_do_portal_nao_atravessam_redes(self, carteira):
        """Os `property_ids` vêm do CORPO do pedido: sem âmbito,
        recomendava-se ao cliente um imóvel de outra rede — com preço e
        morada — e ficava gravado na ficha dele."""
        from services import portal_recommendations

        with _casa_de_imoveis(carteira):
            resposta = await portal_recommendations.run_create_recommendations(
                {"process_id": "p-domus", "property_ids": ["imo-power"]}, BRUNO,
            )

        recomendados = str(resposta)
        assert "imo-power" not in recomendados, (
            f"o imóvel da Power foi recomendado a um cliente da Domus: {resposta}"
        )

    # ── 4. OS REGISTOS FINANCEIROS ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_a_listagem_financeira_nao_atravessa_redes(self, carteira):
        """Sem `company_id` a consulta era `{}`. E o `company_id` da
        query string é um FILTRO escolhido por quem pergunta: os
        `FINANCE_READ_ROLES` incluem `consultor`, `administrativo` e
        `indexacao`."""
        from services import finance_process_records

        with _casa_de_imoveis(carteira):
            resposta = await finance_process_records.run_list_process_finances(
                None, None, None, None, BRUNO,
            )

        assert [f["id"] for f in resposta["finances"]] == ["fin-domus"], (
            "a Domus lê os registos financeiros da Power: "
            f"{[(f['id'], f.get('client_name')) for f in resposta['finances']]}"
        )

    @pytest.mark.asyncio
    async def test_pedir_a_empresa_da_OUTRA_rede_no_filtro_nao_a_abre(self, carteira):
        """O filtro não pode vencer a fronteira."""
        from services import finance_process_records

        with _casa_de_imoveis(carteira):
            resposta = await finance_process_records.run_list_process_finances(
                "cmp-power", None, None, None, BRUNO,
            )

        assert resposta["finances"] == [], (
            "pedir explicitamente a empresa da outra rede devolveu dados"
        )

    @pytest.mark.asyncio
    async def test_o_resumo_financeiro_de_outra_empresa_responde_404(self, carteira):
        """Aqui o `company_id` é OBRIGATÓRIO — logo valida-se, não se
        confia. 404 e não 403: um 403 transformava o endpoint num
        directório das empresas do sistema."""
        from services import finance_process_records

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await finance_process_records.run_get_process_finance_summary(
                    "cmp-power", BRUNO,
                )

        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_abrir_um_registo_financeiro_de_outra_rede_responde_404(self, carteira):
        from services import finance_process_records

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await finance_process_records.run_get_process_finance_by_id(
                    "fin-power", BRUNO,
                )

        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_APAGAR_um_registo_financeiro_de_outra_rede_responde_404(self, carteira):
        from services import finance_process_records

        with _casa_de_imoveis(carteira):
            with pytest.raises(HTTPException) as erro:
                await finance_process_records.run_delete_process_finance(
                    "fin-power", BRUNO,
                )

        assert erro.value.status_code == 404
        assert {f["id"] for f in carteira.process_finances.docs} == {
            "fin-power", "fin-domus",
        }

    @pytest.mark.asyncio
    async def test_um_registo_SEM_empresa_e_recusado(self, carteira):
        """Mais estrito do que a tolerância do legado nas outras
        colecções, de propósito: o `company_id` é obrigatório na criação
        desde sempre, logo um registo sem ele são dados corrompidos e
        não história — e adivinhar a quem pertence é escolher a quem
        vazar."""
        from services.finance_scope import pode_ver_registo

        assert pode_ver_registo(
            {"id": "fin-orfao", "client_name": "Alguém"},
            papel="diretor",
            empresas=("cmp-domus",),
        ) is False


# ════════════════════════════════════════════════════════════════════
#  A CONTRAPROVA — sem isto, "não devolver nada" passava
# ════════════════════════════════════════════════════════════════════
class TestOQueNAOSeFecha:
    """Fechar demasiado esconde trabalho real, e **um imóvel que
    desaparece não produz erro nenhum**."""

    @pytest.mark.asyncio
    async def test_a_power_continua_a_ver_a_carteira_da_POWER(self, carteira):
        from services import property_list

        with _casa_de_imoveis(carteira):
            visiveis = await property_list.run_list_properties(ANA)

        assert [p.title for p in visiveis] == ["T3 em Cascais"]

    @pytest.mark.asyncio
    async def test_a_PRECISION_ve_a_carteira_da_POWER(self, carteira):
        """As duas empresas do grupo partilham dados: é a rede, e não a
        empresa, que é a fronteira. A Carla é consultora na Precision."""
        from services import property_list

        with _casa_de_imoveis(carteira):
            visiveis = await property_list.run_list_properties(CARLA)

        titulos = {p.title for p in visiveis}
        assert "T3 em Cascais" in titulos, (
            f"a Precision deixou de ver a carteira da Power: {titulos}"
        )

    @pytest.mark.asyncio
    async def test_a_PRECISION_ve_os_registos_financeiros_da_POWER(self, carteira):
        """A metade que se parte em SILÊNCIO se a fronteira financeira
        for a empresa em vez da rede. `process_finances` nunca teve
        `network_id`: a condição deriva de rede → EMPRESAS, e é isso que
        a faz funcionar sem migração."""
        from services import finance_process_records

        with _casa_de_imoveis(carteira):
            resposta = await finance_process_records.run_list_process_finances(
                None, None, None, None, CARLA,
            )

        ids = {f["id"] for f in resposta["finances"]}
        assert "fin-power" in ids, (
            f"a Precision perdeu de vista os registos da Power: {ids}"
        )
        assert "fin-domus" in ids, "a Carla também trabalha na Domus"

    @pytest.mark.asyncio
    async def test_o_ADMIN_atravessa_redes_de_proposito(self, carteira):
        """ADMIN/CEO reconciliam a pilha inteira. O **diretor não** — tem
        passe livre DENTRO da sua rede, que é o que o produto promete."""
        from services import property_list

        with _casa_de_imoveis(carteira):
            visiveis = await property_list.run_list_properties(ORFAO)

        assert {p.title for p in visiveis} == {"T3 em Cascais", "T2 em Leiria"}

    @pytest.mark.asyncio
    async def test_a_pilha_POR_CARIMBAR_e_do_grupo_incumbente(
        self, carteira, rede_de_omissao_incumbente,  # noqa: F811
    ):
        """A carteira existente está TODA por carimbar — nunca houve
        escritor que a carimbasse. Tolerá-la a todos (como as visitas
        fazem) entregava-a à primeira ilha que entrasse no sistema; é
        `TENANT_DEFAULT_NETWORK_ID` que declara de quem ela é.
        """
        from services import property_list

        carteira.properties.docs.append(
            _imovel(id="imo-legado", title="Legado sem carimbo",
                    network_id=None, company_id=None, process_id=None)
        )

        with _casa_de_imoveis(carteira):
            da_power = await property_list.run_list_properties(ANA)
            da_domus = await property_list.run_list_properties(BRUNO)

        assert "Legado sem carimbo" in {p.title for p in da_power}, (
            "a pilha por carimbar desapareceu ao grupo incumbente"
        )
        assert "Legado sem carimbo" not in {p.title for p in da_domus}, (
            "a Domus vê a carteira legada do grupo"
        )

    @pytest.mark.asyncio
    async def test_a_power_continua_a_registar_visitas_nos_SEUS_processos(self, carteira):
        """A pergunta do destino não pode fechar o caminho normal."""
        from services import property_engagement

        with _casa_de_imoveis(carteira):
            resposta = await property_engagement.run_register_visit(
                "imo-power", ANA, client_id="p-power",
            )

        assert resposta["success"] is True
        historico = carteira.properties.docs[0].get("history") or []
        assert any("Cliente da Power" in str(h) for h in historico)


# ════════════════════════════════════════════════════════════════════
#  O CARIMBO NA ESCRITA
# ════════════════════════════════════════════════════════════════════
class TestOCarimboNaEscrita:
    """Corrigir só a leitura tornava a correcção invisível para o
    trabalho NOVO — a lição do `assigned_to`."""

    @pytest.mark.asyncio
    async def test_um_imovel_novo_nasce_com_a_rede_de_quem_o_cria(self, carteira):
        from models.property import (
            OwnerInfo, PropertyAddress, PropertyCreate, PropertyFinancials,
            PropertyType,
        )
        from services import property_crud

        pedido = PropertyCreate(
            title="Angariação nova da Domus",
            property_type=PropertyType.APARTAMENTO,
            address=PropertyAddress(
                district="Leiria", municipality="Leiria", locality="Leiria",
            ),
            financials=PropertyFinancials(asking_price=180000.0),
            owner=OwnerInfo(name="Dono novo", phone="911222333"),
        )

        with _casa_de_imoveis(carteira):
            with patch.object(
                property_crud, "check_and_notify_matches_for_new_property",
                new=_nao_faz_nada,
            ):
                criado = await property_crud.run_create_property(
                    pedido, {**BRUNO, "active_company_id": "cmp-domus"},
                )

        assert criado["network_id"] == REDE_DOMUS
        assert criado["company_id"] == "cmp-domus"
        assert "_id" not in criado, (
            "o `insert_one` do Motor muta o dicionário com um ObjectId — "
            "devolvê-lo rebenta a serialização JSON"
        )

    @pytest.mark.asyncio
    async def test_sem_empresa_activa_fica_POR_CARIMBAR_e_nao_adivinha(self, carteira):
        """**Meio carimbo é pior do que nenhum**: a pilha por carimbar
        tem migração, uma rede errada é permanente."""
        from models.property import (
            OwnerInfo, PropertyAddress, PropertyCreate, PropertyFinancials,
            PropertyType,
        )
        from services import property_crud

        pedido = PropertyCreate(
            title="Sem empresa activa",
            property_type=PropertyType.APARTAMENTO,
            address=PropertyAddress(
                district="Porto", municipality="Porto", locality="Porto",
            ),
            financials=PropertyFinancials(asking_price=200000.0),
            owner=OwnerInfo(name="Dono sem empresa"),
        )

        with _casa_de_imoveis(carteira):
            with patch.object(
                property_crud, "check_and_notify_matches_for_new_property",
                new=_nao_faz_nada,
            ):
                criado = await property_crud.run_create_property(
                    pedido, {"id": "u-sem-empresa", "email": "x@y.pt",
                             "role": "consultor"},
                )

        assert not criado.get("network_id")


async def _nao_faz_nada(*_args, **_kwargs):
    """O `check_and_notify_matches_for_new_property` real corre num
    `create_task` e mede outra coisa — tem testes próprios."""
    return None


# ════════════════════════════════════════════════════════════════════
#  CONCORDÂNCIA: o predicado e a condição Mongo respondem o MESMO
# ════════════════════════════════════════════════════════════════════
class TestOPredicadoConcordaComACondicao:
    """`build_network_scope_condition` responde em Mongo (listagens) e
    `documento_no_ambito` em Python (posse de um objecto).

    Duas respostas à mesma pergunta divergem na primeira mudança, e a
    que divergir não dá erro: deixa ver, ou esconde trabalho real. Foi um
    teste desta forma que apanhou, no `sub35`, uma data no futuro a
    entrar na lista filtrada sem etiqueta no ecrã.
    """

    AMOSTRA = [
        {"nome": "da rede", "network_id": REDE_INCUMBENTE},
        {"nome": "da outra rede", "network_id": REDE_DOMUS},
        {"nome": "só com empresa (id)", "company_id": "cmp-power"},
        {"nome": "só com empresa (nome)", "company_name": "Power Real Estate"},
        {"nome": "empresa legada no campo `company`", "company": "Power Real Estate"},
        {"nome": "empresa de outra rede", "company_id": "cmp-domus"},
        {"nome": "sem marca nenhuma"},
        {"nome": "marca vazia", "network_id": "", "company_id": None},
        {"nome": "sentinel `default`", "company_id": "default", "network_id": ""},
        {"nome": "empresa sem rede ainda", "company_id": "cmp-domus",
         "network_id": None},
    ]

    @pytest.mark.parametrize("inclui_omissao", [False, True])
    @pytest.mark.parametrize(
        "redes,empresas",
        [
            ((REDE_INCUMBENTE,), ("cmp-power", "Power Real Estate")),
            ((REDE_DOMUS,), ("cmp-domus", "Domus")),
            ((), ()),
            ((REDE_INCUMBENTE, REDE_DOMUS), ()),
        ],
    )
    def test_respondem_o_mesmo_sobre_a_amostra_inteira(
        self, redes, empresas, inclui_omissao,
    ):
        from tests.unit.helpers_tenant import casa
        from services.tenant_network import (
            TenantScope,
            build_network_scope_condition,
            documento_no_ambito,
        )

        scope = TenantScope(
            network_ids=redes,
            company_ids=tuple(e for e in empresas if e.startswith("cmp-")),
            company_names=tuple(e for e in empresas if not e.startswith("cmp-")),
            inclui_rede_de_omissao=inclui_omissao,
        )
        condicao = build_network_scope_condition(scope)

        for doc in self.AMOSTRA:
            em_mongo = casa(doc, condicao)
            em_python = documento_no_ambito(doc, scope)
            assert em_mongo == em_python, (
                f"discordam sobre {doc['nome']!r} "
                f"(redes={redes}, omissão={inclui_omissao}): "
                f"Mongo={em_mongo} Python={em_python}"
            )

    def test_POR_CARIMBAR_exige_a_ausencia_de_TODAS_as_marcas(self):
        """Olhar só para o `network_id` deixaria a fuga entrar pela
        cláusula que existe para a evitar: um imóvel da Domus criado
        entre o carimbo na escrita e a migração tem empresa e ainda não
        tem rede."""
        from services.tenant_network import documento_sem_marca_de_tenant

        assert documento_sem_marca_de_tenant({}) is True
        assert documento_sem_marca_de_tenant(
            {"network_id": "", "company_id": None, "company_name": ""}
        ) is True
        assert documento_sem_marca_de_tenant(
            {"company_id": "cmp-domus"}
        ) is False
        assert documento_sem_marca_de_tenant(
            {"company": "Domus"}
        ) is False


# ════════════════════════════════════════════════════════════════════
#  A PONTA DE UM CRUZAMENTO
# ════════════════════════════════════════════════════════════════════
class TestAmbitoDeUmaPontaDoCruzamento:
    """O Smart Match não tem utilizador: corre em background depois de
    uma angariação nascer. A fronteira sai do DOCUMENTO."""

    def test_a_ancora_carimbada_restringe_a_SUA_rede(self):
        from services.tenant_network import ambito_de_um_documento

        scope = ambito_de_um_documento({"network_id": REDE_DOMUS})
        assert scope.network_ids == (REDE_DOMUS,)
        assert scope.inclui_rede_de_omissao is False

    def test_a_ancora_por_carimbar_pertence_a_rede_de_OMISSAO(
        self, rede_de_omissao_incumbente,  # noqa: F811
    ):
        """É precisamente para isto que a variável existe."""
        from services.tenant_network import ambito_de_um_documento

        scope = ambito_de_um_documento({})
        assert scope.network_ids == (REDE_INCUMBENTE,)
        assert scope.inclui_rede_de_omissao is True

    def test_a_ancora_do_grupo_incumbente_tambem_alcanca_o_legado(
        self, rede_de_omissao_incumbente,  # noqa: F811
    ):
        """Senão um imóvel novo da Power deixava de cruzar com os
        processos antigos da Power — a correcção a esconder trabalho."""
        from services.tenant_network import ambito_de_um_documento

        scope = ambito_de_um_documento({"network_id": REDE_INCUMBENTE})
        assert scope.inclui_rede_de_omissao is True

    def test_sem_variavel_definida_mantem_o_comportamento_ANTERIOR(self, monkeypatch):
        """Dev e CI: nunca em silêncio — o aviso do `tenant_network` é
        dado. Fechar aqui esvaziaria o Smart Match de desenvolvimento."""
        from services.tenant_network import ambito_de_um_documento

        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        scope = ambito_de_um_documento({})
        assert scope.inclui_rede_de_omissao is True
        assert scope.network_ids == ()
