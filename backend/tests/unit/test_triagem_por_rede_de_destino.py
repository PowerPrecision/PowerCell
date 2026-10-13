"""
Multi-fornecedor: a triagem (Index) vive na REDE DE DESTINO (Out 2026).

O PEDIDO  (substitui o «Hub único» do Bloco A)
  * Não há UM Hub. A Domus pode pedir o Index à Precision, e outra empresa a
    outra: a Empresa A escolhe a rede de destino ao partilhar;
  * o processo partilhado entra na fila de Index DESSA rede específica;
  * `via_verde`: se estiver ligada na partilha, salta o Index e vai direto
    para a consultoria (ex.: só crédito, sem análise documental);
  * a flag `companies.is_hub` desaparece: uma rede «tem Index» quando tem
    indexadores activos (derivado da equipa, não declarado).

O ACHADO QUE O TESTE DO DONO DA REDE REVELOU  (Bloco A, mantido)
  Os pools de auto-atribuição (indexador, consultor, mediador) liam
  `db.users` inteiro: um processo da Domus era dado a um indexador ou
  consultor da Precision SEM partilha nenhuma. As equipas são da rede
  (`TestAEquipaEDaRede`).
"""
from __future__ import annotations

import ast
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]

PRECISION = {"id": "cmp-precision", "name": "Precision Crédito", "network_id": REDE_INCUMBENTE}
POWER = {"id": "cmp-power", "name": "Power Real Estate", "network_id": REDE_INCUMBENTE}
DOMUS = {"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS}

UCRS = [
    {"user_id": "u-ivo", "company_id": "cmp-precision", "company_name": "Precision Crédito", "role": "indexacao", "is_default": True},
    {"user_id": "u-cris", "company_id": "cmp-precision", "company_name": "Precision Crédito", "role": "consultor", "is_default": True},
    {"user_id": "u-dina", "company_id": "cmp-domus", "company_name": "Domus", "role": "consultor", "is_default": True},
    {"user_id": "u-bruno", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor", "is_default": True},
]
USERS = [
    {"id": "u-ivo", "name": "Ivo", "email": "ivo@p.pt", "role": "indexacao", "is_active": True},
    {"id": "u-cris", "name": "Cris", "email": "cris@p.pt", "role": "consultor", "is_active": True},
    {"id": "u-dina", "name": "Dina", "email": "dina@d.pt", "role": "consultor", "is_active": True},
    {"id": "u-bruno", "name": "Bruno", "email": "bruno@d.pt", "role": "diretor", "is_active": True},
]


def _mundo(fake_db, *, com_index=True, processo=None):
    """Precision+Power (uma rede, COM indexador) e Domus (ilha, SEM indexador)."""
    for empresa in (PRECISION, POWER, DOMUS):
        fake_db.companies.docs.append(dict(empresa))
    fake_db.user_company_roles.docs.extend(dict(u) for u in UCRS)
    fake_db.users.docs.extend(dict(u) for u in USERS)
    if not com_index:
        fake_db.users.docs[:] = [u for u in fake_db.users.docs if u["role"] != "indexacao"]
        fake_db.user_company_roles.docs[:] = [u for u in fake_db.user_company_roles.docs if u["role"] != "indexacao"]
    fake_db.processes.docs.append(processo or {
        "id": "p-domus", "process_number": 7, "client_name": "Cliente D",
        "status": "novo", "network_id": REDE_DOMUS, "company_id": "cmp-domus",
        "skip_index": True, "index_dispensado_por": "rede_sem_index",
        "assigned_consultor_id": "u-dina", "assigned_consultor_ids": ["u-dina"],
    })
    return fake_db


@contextlib.contextmanager
def _ambiente(db):
    import services.network_triage as ht
    import services.process_assignment as pa
    import services.process_sharing as ps

    with tenant_db(db, ht, pa, ps), \
            patch("services.history.log_history", AsyncMock()), \
            patch("services.audit_trail_service.log_audit_event", AsyncMock()), \
            patch("services.notification_service.send_notification_with_preference_check", AsyncMock(return_value=True)), \
            patch("services.realtime_notifications.send_realtime_notification", AsyncMock()), \
            patch.object(pa, "_count_active_processes_for_indexer", AsyncMock(return_value=0)), \
            patch.object(pa, "_count_active_processes_for_consultant", AsyncMock(return_value=0)):
        yield


ENTRADA_DA_PRECISION = {
    "company_id": "cmp-precision", "company_name": "Precision Crédito",
    "network_id": REDE_INCUMBENTE, "added_at": "x", "added_by": "u-dina",
}


def _processo(db, pid="p-domus"):
    return next(p for p in db.processes.docs if p["id"] == pid)


# ════════════════════════════════════════════════════════════════════
# Quem tem Index — DERIVADO da equipa, não declarado
# ════════════════════════════════════════════════════════════════════
class TestQuemTemIndex:
    @pytest.mark.asyncio
    async def test_a_rede_com_indexador_activo_tem_index_e_a_ilha_nao(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db):
            assert await ht.redes_com_index() == {REDE_INCUMBENTE}

    @pytest.mark.asyncio
    async def test_sem_indexadores_nenhuma_rede_tem_index(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db, com_index=False)
        with _ambiente(db):
            assert await ht.redes_com_index() == set()

    @pytest.mark.asyncio
    async def test_um_indexador_inactivo_nao_conta(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        next(u for u in db.users.docs if u["id"] == "u-ivo")["is_active"] = False
        with _ambiente(db):
            assert await ht.redes_com_index() == set()

    @pytest.mark.asyncio
    async def test_contratar_um_indexador_na_domus_da_index_a_domus(self, fake_async_db):
        """A capacidade segue a equipa real: nada a declarar à mão."""
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        db.users.docs.append({"id": "u-ines", "name": "Inês", "role": "indexacao", "is_active": True})
        db.user_company_roles.docs.append(
            {"user_id": "u-ines", "company_id": "cmp-domus", "company_name": "Domus", "role": "indexacao"})
        with _ambiente(db):
            assert await ht.redes_com_index() == {REDE_INCUMBENTE, REDE_DOMUS}

    @pytest.mark.asyncio
    async def test_o_indexador_de_conta_antiga_conta_pela_empresa(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db, com_index=False)
        db.users.docs.append({"id": "u-velho", "role": "indexacao", "company": "Domus", "is_active": True})
        with _ambiente(db):
            assert await ht.redes_com_index() == {REDE_DOMUS}

    @pytest.mark.asyncio
    async def test_uma_falha_a_ler_a_equipa_desliga_a_regra(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db), patch.object(db.users, "find", side_effect=RuntimeError("bd")):
            assert await ht.redes_com_index() == set()

    def test_a_flag_is_hub_ja_nao_existe(self):
        """Removida de vez: modelo, serviço de empresas e triagem."""
        from models.company import CompanyCreate, CompanyResponse, CompanyUpdate

        for modelo in (CompanyCreate, CompanyUpdate, CompanyResponse):
            assert "is_hub" not in modelo.model_fields, modelo.__name__
        for rel in ("services/network_triage.py", "services/companies_crud_api_mutate.py",
                    "services/process_sharing.py", "models/company.py"):
            fonte = (BACKEND / rel).read_text(encoding="utf-8")
            assert "is_hub" not in fonte.replace("`companies.is_hub`", ""), rel


# ════════════════════════════════════════════════════════════════════
# O regime da rede sem Index: nasce dispensado
# ════════════════════════════════════════════════════════════════════
class TestUmaRedeSemIndexNaoPassaPeloIndex:
    @pytest.mark.asyncio
    async def test_um_processo_da_domus_nasce_dispensado_do_index(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        doc = {"id": "n", "network_id": REDE_DOMUS}
        with _ambiente(db):
            assert await ht.aplicar_regime_de_indexacao(doc) is True
        assert doc["skip_index"] is True
        assert doc["index_dispensado_por"] == "rede_sem_index"

    @pytest.mark.asyncio
    async def test_um_processo_de_uma_rede_com_index_passa_pelo_index(self, fake_async_db):
        """Contraprova: tirar o Index a toda a gente passaria no teste acima."""
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        doc = {"id": "n", "network_id": REDE_INCUMBENTE}
        with _ambiente(db):
            assert await ht.aplicar_regime_de_indexacao(doc) is False
        assert "skip_index" not in doc

    @pytest.mark.asyncio
    async def test_sem_nenhum_index_no_sistema_nada_muda_nem_para_a_domus(self, fake_async_db):
        """Sem Index em lado nenhum, TODAS as redes seriam dispensadas —
        inclusive a do grupo incumbente."""
        import services.network_triage as ht

        db = _mundo(fake_async_db, com_index=False)
        doc = {"id": "n", "network_id": REDE_DOMUS}
        with _ambiente(db):
            assert await ht.aplicar_regime_de_indexacao(doc) is False
        assert "skip_index" not in doc

    @pytest.mark.asyncio
    async def test_um_processo_por_carimbar_nao_perde_o_index(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        doc = {"id": "n"}
        with _ambiente(db):
            assert await ht.aplicar_regime_de_indexacao(doc) is False
        assert "skip_index" not in doc

    @pytest.mark.asyncio
    async def test_uma_falha_a_ler_a_equipa_nao_parte_a_criacao(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        doc = {"id": "n", "network_id": REDE_DOMUS}
        with _ambiente(db), patch.object(ht, "redes_com_index", AsyncMock(side_effect=RuntimeError("x"))):
            assert await ht.aplicar_regime_de_indexacao(doc) is False


# ════════════════════════════════════════════════════════════════════
# A decisão (pura)
# ════════════════════════════════════════════════════════════════════
class TestDecidirEntrada:
    def test_partilha_normal_entra_em_triagem(self):
        from services.network_triage import decidir_entrada

        d = decidir_entrada({"id": "p"}, redes_de_destino=["hub"])
        assert d["state"] == "triagem" and d["network_id"] == "hub"

    def test_via_verde_salta_o_index(self):
        from services.network_triage import decidir_entrada

        d = decidir_entrada({"via_verde": True}, redes_de_destino=["hub"])
        assert d["state"] == "via_verde" and d["motivo"] == "via_verde"

    @pytest.mark.parametrize("valor", ["true", 1, "sim", None, False])
    def test_so_o_booleano_true_liga_a_via_verde(self, valor):
        from services.network_triage import decidir_entrada

        d = decidir_entrada({"via_verde": valor}, redes_de_destino=["hub"])
        assert d["state"] == "triagem"

    def test_um_processo_ja_indexado_nao_tem_nada_a_triar(self):
        from services.network_triage import decidir_entrada

        d = decidir_entrada({"is_indexed": True}, redes_de_destino=["hub"])
        assert d["state"] == "via_verde" and d["motivo"] == "ja_indexado"

    def test_o_primeiro_registo_ganha(self):
        from services.network_triage import decidir_entrada

        assert decidir_entrada(
            {"hub_triage": {"state": "triagem"}, "via_verde": True},
            redes_de_destino=["hub"],
        ) is None

    def test_sem_rede_de_destino_nao_ha_nada_a_fazer(self):
        from services.network_triage import decidir_entrada

        assert decidir_entrada({}, redes_de_destino=[]) is None


# ════════════════════════════════════════════════════════════════════
# A entrada na triagem da rede de destino (com a base de dados)
# ════════════════════════════════════════════════════════════════════
class TestEntradaNaTriagemDaRede:
    @pytest.mark.asyncio
    async def test_a_partilha_poe_o_processo_na_fila_do_index_da_rede_de_destino(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db):
            registo = await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_PRECISION], por_ordem_de="u-dina")

        p = _processo(db)
        assert registo["state"] == "triagem"
        assert p["hub_triage"]["state"] == "triagem"
        assert p["hub_triage"]["network_id"] == REDE_INCUMBENTE
        assert p["skip_index"] is False, "a triagem da rede de destino exige o Index"
        # O indexador sai do pool da rede de DESTINO.
        assert p["assigned_indexacao_id"] == "u-ivo"

    @pytest.mark.asyncio
    async def test_via_verde_salta_o_index_e_nao_atribui_indexador(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        _processo(db)["via_verde"] = True
        with _ambiente(db):
            registo = await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_PRECISION])

        p = _processo(db)
        assert registo["state"] == "via_verde"
        assert p["skip_index"] is True, "a Via Verde não repõe o Index"
        assert not p.get("assigned_indexacao_id")

    @pytest.mark.asyncio
    async def test_destino_sem_indexadores_nao_recebe_fila(self, fake_async_db):
        """Uma fila que ninguém lê é um buraco negro: não se cria."""
        import services.network_triage as ht

        db = _mundo(fake_async_db, com_index=False)
        with _ambiente(db):
            registo = await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_PRECISION])

        assert registo is None
        assert "hub_triage" not in _processo(db)
        assert _processo(db)["skip_index"] is True, "o processo continua a andar, sem Index"

    @pytest.mark.asyncio
    async def test_destino_sem_indexador_livre_fica_na_fila_e_nao_falha(self, fake_async_db):
        import services.network_triage as ht
        import services.process_assignment as pa

        db = _mundo(fake_async_db)
        with _ambiente(db), patch.object(
            pa, "assign_to_indexer", AsyncMock(return_value=(False, {}, "todos ocupados")),
        ):
            registo = await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_PRECISION])

        p = _processo(db)
        assert registo["state"] == "triagem"
        assert not p.get("assigned_indexacao_id")

    @pytest.mark.asyncio
    async def test_e_idempotente_e_o_primeiro_registo_ganha(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db):
            primeiro = await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_PRECISION])
            _processo(db)["via_verde"] = True  # ligar depois não reabre nem fecha
            segundo = await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_PRECISION])

        assert primeiro is not None and segundo is None
        assert _processo(db)["hub_triage"]["state"] == "triagem"

    @pytest.mark.asyncio
    async def test_partilhar_com_uma_rede_sem_index_nao_faz_nada(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        outra = {"company_id": "x", "company_name": "X", "network_id": "rede:x"}
        with _ambiente(db):
            assert await ht.entrar_na_triagem_da_rede("p-domus", [outra]) is None
        assert "hub_triage" not in _processo(db)

    @pytest.mark.asyncio
    async def test_deixa_rasto_no_historico_e_no_trilho(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db), patch("services.history.log_history", AsyncMock()) as hist, \
                patch("services.audit_trail_service.log_audit_event", AsyncMock()) as trilho:
            await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_PRECISION], por_ordem_de="u-dina")

        assert hist.await_count >= 1
        assert trilho.await_args.kwargs["action"] == "hub_triage_entered"

    @pytest.mark.asyncio
    async def test_a_versao_dos_escritores_nunca_propaga(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db), patch.object(ht, "entrar_na_triagem_da_rede", AsyncMock(side_effect=RuntimeError("x"))):
            assert await ht.entrar_na_triagem_da_rede_sem_falhar("p-domus", [ENTRADA_DA_PRECISION]) is None


# ════════════════════════════════════════════════════════════════════
# A ligação: a partilha EXPLÍCITA dispara a triagem (a Via Rápida morreu)
# ════════════════════════════════════════════════════════════════════
class TestAPartilhaDisparaATriagem:
    @pytest.mark.asyncio
    async def test_partilhar_com_uma_rede_com_index_entra_na_triagem(self, fake_async_db):
        """Fim a fim: «Partilhar com Empresa…» abre a partilha e a partilha
        põe o processo na fila central da rede de destino."""
        import services.process_sharing as ps

        db = _mundo(fake_async_db)
        with _ambiente(db):
            resultado = await ps.partilhar_com_rede(
                "p-domus", REDE_INCUMBENTE, por_ordem_de="u-bruno",
            )

        assert resultado["partilhado"] is True
        assert _processo(db)["hub_triage"]["state"] == "triagem"
        assert _processo(db)["hub_triage"]["explicit"] is True

    @pytest.mark.asyncio
    async def test_com_via_verde_a_partilha_fica_a_cargo_da_consultoria(self, fake_async_db):
        import services.process_sharing as ps

        db = _mundo(fake_async_db)
        with _ambiente(db):
            await ps.partilhar_com_rede(
                "p-domus", REDE_INCUMBENTE, via_verde=True, por_ordem_de="u-bruno",
            )

        assert _processo(db)["hub_triage"]["state"] == "via_verde"
        assert _processo(db)["skip_index"] is True

    @pytest.mark.asyncio
    async def test_atribuir_alguem_da_precision_NAO_entra_na_triagem(self, fake_async_db):
        """A antiga Via Rápida: um processo da Domus com um consultor da
        Precision atribuído. Já não há partilha por atribuição, logo nada
        entra na fila de ninguém."""
        db = _mundo(fake_async_db)
        p = _processo(db)
        p["assigned_consultor_ids"] = ["u-cris"]
        p["assigned_consultor_id"] = "u-cris"

        assert "hub_triage" not in _processo(db)
        assert not _processo(db).get("partner_network_ids")

    def test_a_ligacao_existe_no_codigo(self):
        """Contraprova da ligação: sem ela a triagem é código morto."""
        fonte = (BACKEND / "services" / "process_sharing.py").read_text(encoding="utf-8")
        assert "entrar_na_triagem_da_rede_sem_falhar(" in fonte


# ════════════════════════════════════════════════════════════════════
# As equipas são da rede
# ════════════════════════════════════════════════════════════════════
class TestAEquipaEDaRede:
    @pytest.mark.asyncio
    async def test_a_domus_nao_recebe_um_indexador_da_precision(self, fake_async_db):
        """O achado: o pool era o mundo. E a Domus não tem Index — o
        processo NÃO é atribuído, e o estado não muda."""
        import services.process_assignment as pa

        db = _mundo(fake_async_db)
        with _ambiente(db):
            ok, dados, _ = await pa.assign_to_indexer("p-domus")

        assert ok is True and dados["assigned"] is False
        assert dados["reason"] == "network_without_index"
        assert not _processo(db).get("assigned_indexacao_id")
        assert _processo(db)["status"] == "novo"

    @pytest.mark.asyncio
    async def test_o_indexador_da_triagem_sai_do_pool_da_rede_de_destino_e_nao_do_mundo(self, fake_async_db):
        """Com uma indexadora da Domus à frente na lista, escolher à ordem
        do Mongo daria a ela — o teste só morde se o pool for filtrado."""
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        db.users.docs.insert(0, {"id": "u-ines", "name": "Inês", "email": "i@d.pt", "role": "indexacao", "is_active": True})
        db.user_company_roles.docs.append(
            {"user_id": "u-ines", "company_id": "cmp-domus", "company_name": "Domus", "role": "indexacao", "is_default": True}
        )
        with _ambiente(db):
            # (explícita: a Domus tem agora Index próprio, e uma partilha por
            # atribuição não desviava o trabalho — regra 4 do módulo.)
            await ht.entrar_na_triagem_da_rede(
                "p-domus", [ENTRADA_DA_PRECISION])

        assert _processo(db)["assigned_indexacao_id"] == "u-ivo"

    @pytest.mark.asyncio
    async def test_sem_index_na_precision_o_pool_de_indexadores_continua_a_ser_o_da_propria_rede(self, fake_async_db):
        import services.process_assignment as pa

        db = _mundo(fake_async_db, com_index=False)
        _processo(db).pop("skip_index")
        db.users.docs.insert(0, {"id": "u-ines", "name": "Inês", "email": "i@d.pt", "role": "indexacao", "is_active": True})
        db.user_company_roles.docs.append(
            {"user_id": "u-ines", "company_id": "cmp-domus", "company_name": "Domus", "role": "indexacao", "is_default": True}
        )
        with _ambiente(db):
            ok, dados, _ = await pa.assign_to_indexer("p-domus")

        assert ok and dados["assigned_indexacao_id"] == "u-ines", "o pool não pode ser o mundo"

    @pytest.mark.asyncio
    async def test_o_pool_de_consultores_da_domus_e_so_da_domus(self, fake_async_db):
        import services.process_assignment as pa

        db = _mundo(fake_async_db)
        p = _processo(db)
        for campo in ("assigned_consultor_id", "assigned_consultor_ids"):
            p.pop(campo)
        with _ambiente(db):
            escolhido = await pa._find_least_busy_user("consultor", None, REDE_DOMUS)

        assert escolhido["id"] == "u-dina"

    @pytest.mark.asyncio
    async def test_sem_consultor_na_rede_nao_se_vai_buscar_a_outra(self, fake_async_db):
        import services.process_assignment as pa

        db = _mundo(fake_async_db)
        db.users.docs[:] = [u for u in db.users.docs if u["id"] != "u-dina"]
        with _ambiente(db):
            assert await pa._find_least_busy_user("consultor", None, REDE_DOMUS) is None

    @pytest.mark.asyncio
    async def test_contraprova_sem_rede_o_pool_continua_a_ser_o_de_sempre(self, fake_async_db):
        """Um processo por carimbar não tem equipa conhecida: sem restrição."""
        import services.process_assignment as pa

        db = _mundo(fake_async_db)
        with _ambiente(db):
            escolhido = await pa._find_least_busy_user("consultor", None, None)
        assert escolhido["id"] in {"u-cris", "u-dina"}

    @pytest.mark.asyncio
    async def test_depois_da_triagem_a_equipa_e_a_do_destino(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        assert ht.rede_da_equipa(_processo(db)) == REDE_DOMUS
        _processo(db)["hub_triage"] = {"state": "triagem", "network_id": REDE_INCUMBENTE}
        assert ht.rede_da_equipa(_processo(db)) == REDE_INCUMBENTE

    @pytest.mark.asyncio
    async def test_membros_da_rede_por_ucr_e_por_conta_antiga(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        db.users.docs.append({"id": "u-velho", "name": "V", "role": "consultor", "company": "Domus", "is_active": True})
        with _ambiente(db):
            assert await ht.user_ids_da_rede(REDE_DOMUS) == {"u-dina", "u-bruno", "u-velho"}
            assert await ht.user_ids_da_rede("") is None
            assert await ht.user_ids_da_rede("rede:inexistente") == set()


# ════════════════════════════════════════════════════════════════════
# Multi-fornecedor: a Domus escolhe QUEM faz o Index
# ════════════════════════════════════════════════════════════════════
OMEGA = {"id": "cmp-omega", "name": "Omega Crédito", "network_id": "rede:omega"}
ENTRADA_DA_OMEGA = {
    "company_id": "cmp-omega", "company_name": "Omega Crédito",
    "network_id": "rede:omega", "added_at": "x", "added_by": "u-bruno",
}


def _com_a_omega(db):
    """Um SEGUNDO fornecedor de Index, independente da Precision."""
    db.companies.docs.append(dict(OMEGA))
    db.users.docs.append({"id": "u-olga", "name": "Olga", "email": "o@o.pt", "role": "indexacao", "is_active": True})
    db.user_company_roles.docs.append(
        {"user_id": "u-olga", "company_id": "cmp-omega", "company_name": "Omega Crédito",
         "role": "indexacao", "is_default": True})
    return db


class TestMultiFornecedor:
    @pytest.mark.asyncio
    async def test_cada_destino_tem_o_seu_index(self, fake_async_db):
        import services.network_triage as ht

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            assert await ht.redes_com_index() == {REDE_INCUMBENTE, "rede:omega"}

    @pytest.mark.asyncio
    async def test_partilhar_com_a_omega_usa_o_indexador_da_omega(self, fake_async_db):
        """O ataque ao «Hub único»: com dois fornecedores, o destino é o ESCOLHIDO."""
        import services.network_triage as ht

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            registo = await ht.entrar_na_triagem_da_rede(
                "p-domus", [ENTRADA_DA_OMEGA])

        p = _processo(db)
        assert registo["network_id"] == "rede:omega"
        assert p["hub_triage"]["network_id"] == "rede:omega"
        assert p["assigned_indexacao_id"] == "u-olga", "nunca o Ivo, que é da Precision"

    @pytest.mark.asyncio
    async def test_partilhar_com_a_precision_continua_a_usar_o_ivo(self, fake_async_db):
        import services.network_triage as ht

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_PRECISION])
        assert _processo(db)["assigned_indexacao_id"] == "u-ivo"

    @pytest.mark.asyncio
    async def test_a_equipa_do_processo_passa_a_ser_a_do_destino_escolhido(self, fake_async_db):
        import services.network_triage as ht

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_OMEGA])
        assert ht.rede_da_equipa(_processo(db)) == "rede:omega"

    @pytest.mark.asyncio
    async def test_o_primeiro_destino_ganha_um_segundo_nao_reabre_a_triagem(self, fake_async_db):
        import services.network_triage as ht

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            await ht.entrar_na_triagem_da_rede("p-domus", [ENTRADA_DA_OMEGA])
            segundo = await ht.entrar_na_triagem_da_rede(
                "p-domus", [ENTRADA_DA_PRECISION])
        assert segundo is None
        assert _processo(db)["hub_triage"]["network_id"] == "rede:omega"


class TestOServicoNaoConfiaNaRota:
    """Defesa em profundidade: o serviço é chamado por mais do que uma rota."""

    @pytest.mark.asyncio
    async def test_o_servico_recusa_um_papel_sem_direito_mesmo_sem_a_rota(self, fake_async_db):
        from fastapi import HTTPException

        import services.process_sharing_api as api

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db), tenant_db(db, api):
            with pytest.raises(HTTPException) as erro:
                await api.run_share_process("p-domus", "rede:omega", None, DINA)
        assert erro.value.status_code == 403
        assert not _processo(db).get("partner_network_ids")

    @pytest.mark.asyncio
    async def test_a_triagem_nunca_poe_um_processo_na_fila_da_propria_rede_do_dono(self, fake_async_db):
        import services.network_triage as ht

        db = _mundo(fake_async_db)
        db.processes.docs.append({
            "id": "p-prec", "status": "novo", "network_id": REDE_INCUMBENTE, "skip_index": False,
        })
        with _ambiente(db):
            assert await ht.entrar_na_triagem_da_rede(
                "p-prec", [ENTRADA_DA_PRECISION]) is None
        assert "hub_triage" not in _processo(db, "p-prec")


class TestSoHaPartilhaExplicita:
    """A Via Rápida foi extinta: a partilha é sempre uma instrução («enviar
    para a rede X»), nunca uma dedução tirada de quem foi atribuído."""

    @pytest.mark.asyncio
    async def test_uma_partilha_e_sempre_uma_instrucao(self, fake_async_db):
        import services.network_triage as ht

        db = _com_a_omega(_mundo(fake_async_db))
        db.processes.docs.append({
            "id": "p-prec", "status": "novo", "network_id": REDE_INCUMBENTE,
            "company_id": "cmp-precision", "skip_index": False,
        })
        with _ambiente(db):
            registo = await ht.entrar_na_triagem_da_rede(
                "p-prec", [ENTRADA_DA_OMEGA])
        assert registo["state"] == "triagem" and registo["explicit"] is True
        assert _processo(db, "p-prec")["assigned_indexacao_id"] == "u-olga"


# ════════════════════════════════════════════════════════════════════
# A acção «Partilhar com…» (serviço)
# ════════════════════════════════════════════════════════════════════
class TestPartilharComUmaRede:
    @pytest.mark.asyncio
    async def test_envia_para_a_rede_escolhida_e_entra_na_fila_dela(self, fake_async_db):
        import services.process_sharing as ps

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            r = await ps.partilhar_com_rede("p-domus", "rede:omega", por_ordem_de="u-bruno")

        p = _processo(db)
        assert r["partilhado"] is True and r["destino_tem_index"] is True
        assert p["partner_network_ids"] == ["rede:omega"]
        assert p["partner_companies"][0]["company_name"] == "Omega Crédito"
        assert p["hub_triage"]["network_id"] == "rede:omega"
        assert p["assigned_indexacao_id"] == "u-olga"
        assert p["network_id"] == REDE_DOMUS, "partilhar nunca muda de quem é"

    @pytest.mark.asyncio
    async def test_via_verde_na_partilha_salta_o_index_e_fica_gravada(self, fake_async_db):
        import services.process_sharing as ps

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            r = await ps.partilhar_com_rede("p-domus", "rede:omega", via_verde=True)

        p = _processo(db)
        assert p["via_verde"] is True, "a flag grava-se ANTES da triagem"
        assert r["triagem"]["state"] == "via_verde"
        assert p["skip_index"] is True and not p.get("assigned_indexacao_id")

    @pytest.mark.asyncio
    async def test_a_via_verde_do_processo_e_respeitada_quando_o_pedido_nao_a_diz(self, fake_async_db):
        import services.process_sharing as ps

        db = _com_a_omega(_mundo(fake_async_db))
        _processo(db)["via_verde"] = True
        with _ambiente(db):
            r = await ps.partilhar_com_rede("p-domus", "rede:omega")
        assert r["triagem"]["state"] == "via_verde"

    @pytest.mark.asyncio
    async def test_via_verde_false_no_pedido_desliga_a_flag(self, fake_async_db):
        import services.process_sharing as ps

        db = _com_a_omega(_mundo(fake_async_db))
        _processo(db)["via_verde"] = True
        with _ambiente(db):
            r = await ps.partilhar_com_rede("p-domus", "rede:omega", via_verde=False)
        assert _processo(db)["via_verde"] is False
        assert r["triagem"]["state"] == "triagem"

    @pytest.mark.asyncio
    async def test_destino_sem_index_partilha_mas_nao_cria_fila(self, fake_async_db):
        """Só crédito, sem Index: o destino vê o processo, não há fila."""
        import services.process_sharing as ps

        db = _mundo(fake_async_db)
        db.companies.docs.append({"id": "cmp-zeta", "name": "Zeta", "network_id": "rede:zeta"})
        with _ambiente(db):
            r = await ps.partilhar_com_rede("p-domus", "rede:zeta")

        assert r["partilhado"] is True and r["destino_tem_index"] is False
        assert r["triagem"] is None
        assert "hub_triage" not in _processo(db)
        assert _processo(db)["partner_network_ids"] == ["rede:zeta"]

    @pytest.mark.asyncio
    async def test_repetir_e_idempotente(self, fake_async_db):
        import services.process_sharing as ps

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            await ps.partilhar_com_rede("p-domus", "rede:omega")
            r = await ps.partilhar_com_rede("p-domus", "rede:omega")
        assert r["ja_partilhado"] is True and r["partilhado"] is False
        assert len(_processo(db)["partner_companies"]) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("destino,motivo", [
        ("", "Escolha"), ("   ", "Escolha"),
        (REDE_DOMUS, "já pertence"), ("rede:inexistente", "desconhecida"),
    ])
    async def test_destinos_que_nao_servem(self, fake_async_db, destino, motivo):
        import services.process_sharing as ps

        db = _com_a_omega(_mundo(fake_async_db))
        with _ambiente(db):
            with pytest.raises(ps.DestinoInvalido, match=motivo):
                await ps.partilhar_com_rede("p-domus", destino)
        assert not _processo(db).get("partner_network_ids")

    @pytest.mark.asyncio
    async def test_deixa_rasto_no_trilho_e_no_historico(self, fake_async_db):
        import services.process_sharing as ps

        db = _com_a_omega(_mundo(fake_async_db))
        textos = []

        async def historico(texto):
            textos.append(texto)

        with _ambiente(db), patch("services.audit_trail_service.log_audit_event", AsyncMock()) as trilho:
            await ps.partilhar_com_rede("p-domus", "rede:omega", por_ordem_de="u-bruno",
                                        registar_historico=historico)
        acoes = [c.kwargs.get("action") for c in trilho.await_args_list]
        assert "process_shared" in acoes
        assert any("Omega" in t for t in textos)


# ════════════════════════════════════════════════════════════════════
# A rota: quem pode, de quem é o processo, o que o ecrã recebe
# ════════════════════════════════════════════════════════════════════
BRUNO = {"id": "u-bruno", "role": "diretor", "effective_role": "diretor", "name": "Bruno"}
DINA = {"id": "u-dina", "role": "consultor", "effective_role": "consultor", "name": "Dina"}
CRIS = {"id": "u-cris", "role": "diretor", "effective_role": "diretor", "name": "Cris"}  # Precision


@pytest.fixture
def cliente_http(fake_async_db, rede_de_omissao_incumbente):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routes.processes as processos
    import services.auth as auth_mod
    import services.process_closed_guard as guarda
    import services.process_scope_guard as psg
    import services.process_sharing_api as api
    import services.network_triage as ht
    import services.process_assignment as pa
    import services.process_sharing as ps
    from services.auth import get_current_user

    db = _com_a_omega(_mundo(fake_async_db))
    db.user_company_roles.docs.append(
        {"user_id": "u-cris", "company_id": "cmp-precision", "company_name": "Precision Crédito",
         "role": "diretor", "is_default": True})
    atual = {"user": BRUNO}
    app = FastAPI()
    app.include_router(processos.router)
    app.dependency_overrides[get_current_user] = lambda: atual["user"]
    with _ambiente(db), tenant_db(db, auth_mod, guarda, psg, api, ht, pa, ps):
        c = TestClient(app, raise_server_exceptions=False)
        c.definir_utilizador = lambda u: atual.update(user=u)
        yield c, db


class TestARotaDePartilha:
    def test_a_direccao_da_casa_dona_envia_para_a_omega(self, cliente_http):
        c, db = cliente_http
        r = c.post("/processes/p-domus/partners", json={"network_id": "rede:omega"})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["partilhado"] is True and corpo["triagem"] == "triagem"
        assert _processo(db)["hub_triage"]["network_id"] == "rede:omega"

    def test_o_corpo_leva_a_via_verde(self, cliente_http):
        c, db = cliente_http
        r = c.post("/processes/p-domus/partners", json={"network_id": "rede:omega", "via_verde": True})
        assert r.status_code == 200, r.text
        assert r.json()["triagem"] == "via_verde"
        assert _processo(db)["via_verde"] is True

    def test_o_consultor_nao_partilha(self, cliente_http):
        c, db = cliente_http
        c.definir_utilizador(DINA)
        assert c.post("/processes/p-domus/partners", json={"network_id": "rede:omega"}).status_code == 403
        assert not _processo(db).get("partner_network_ids")

    def test_o_administrativo_partilha(self, cliente_http):
        c, db = cliente_http
        c.definir_utilizador({"id": "u-adm", "role": "administrativo", "effective_role": "administrativo"})
        db.user_company_roles.docs.append(
            {"user_id": "u-adm", "company_id": "cmp-domus", "company_name": "Domus",
             "role": "administrativo", "is_default": True})
        assert c.post("/processes/p-domus/partners", json={"network_id": "rede:omega"}).status_code == 200

    def test_quem_nao_ve_o_processo_recebe_o_404_de_sempre(self, cliente_http):
        c, db = cliente_http
        db.processes.docs.append({
            "id": "p-omega", "status": "novo", "network_id": "rede:omega", "company_id": "cmp-omega"})
        r = c.post("/processes/p-omega/partners", json={"network_id": REDE_INCUMBENTE})
        assert r.status_code == 404

    def test_a_convidada_passa_adiante_em_cadeia_e_o_elo_fica_marcado(self, cliente_http):
        """Partilha em cadeia (Out 2026): quem VÊ o processo pode passá-lo à frente.

        Antes só a casa dona partilhava (403 à convidada); a direcção pediu a cadeia
        Parceiro → Y → Z sem fricção. O elo guarda DE QUEM veio e a que distância está.
        """
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        r = c.post("/processes/p-domus/partners", json={"network_id": "rede:omega"})
        assert r.status_code == 200, r.text
        elo = next(e for e in _processo(db)["partner_companies"] if e["network_id"] == "rede:omega")
        assert elo["shared_from_network"] == REDE_INCUMBENTE
        assert elo["depth"] == 2
        # A casa dona (Domus) mantém-se a dona: a cadeia só acrescenta quem VÊ.
        assert _processo(db)["network_id"] == REDE_DOMUS

    def test_destino_invalido_e_400(self, cliente_http):
        c, _db = cliente_http
        assert c.post("/processes/p-domus/partners", json={"network_id": "rede:nao-existe"}).status_code == 400
        assert c.post("/processes/p-domus/partners", json={"network_id": REDE_DOMUS}).status_code == 400

    def test_um_processo_fechado_nao_se_partilha(self, cliente_http):
        c, db = cliente_http
        _processo(db)["status"] = "concluido"
        r = c.post("/processes/p-domus/partners", json={"network_id": "rede:omega"})
        assert r.status_code == 403 and "fechado" in r.text
        assert not _processo(db).get("partner_network_ids")

    def test_os_destinos_que_o_ecra_recebe(self, cliente_http):
        c, db = cliente_http
        db.companies.docs.append({"id": "cmp-zeta", "name": "Zeta", "network_id": "rede:zeta"})
        r = c.get("/processes/p-domus/share-targets")
        assert r.status_code == 200, r.text
        por_rede = {d["network_id"]: d for d in r.json()["destinos"]}
        assert REDE_DOMUS not in por_rede, "a rede do dono não é destino"
        assert por_rede[REDE_INCUMBENTE]["tem_index"] is True
        assert por_rede[REDE_INCUMBENTE]["empresas"] == ["Power Real Estate", "Precision Crédito"]
        assert por_rede["rede:omega"]["tem_index"] is True
        assert por_rede["rede:zeta"]["tem_index"] is False
        assert all(d["ja_partilhado"] is False for d in por_rede.values())

    def test_o_destino_ja_partilhado_vem_marcado(self, cliente_http):
        c, _db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": "rede:omega"})
        por_rede = {d["network_id"]: d for d in c.get("/processes/p-domus/share-targets").json()["destinos"]}
        assert por_rede["rede:omega"]["ja_partilhado"] is True

    def test_o_consultor_nao_ve_os_destinos(self, cliente_http):
        c, _db = cliente_http
        c.definir_utilizador(DINA)
        assert c.get("/processes/p-domus/share-targets").status_code == 403


# ════════════════════════════════════════════════════════════════════
# O inventário que falha por omissão
# ════════════════════════════════════════════════════════════════════
#: Escritores que NÃO aplicam o regime, com o motivo. Uma entrada nova
#: exige ler o código e escrever porquê.
EXCEPCOES = {
    ("services/admin_dev_ops.py", "run_seed_realistic_data"):
        "semente de desenvolvimento (só Master, recusa produção): não há rede a respeitar",
    ("services/admin_proc_migration_api.py", "run_rollback_migration"):
        "repõe processos arquivados tal e qual estavam — o regime já foi decidido na criação",
}


def _escritores_de_processos():
    achados = []
    for caminho in sorted((BACKEND / "services").glob("*.py")):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for fn in ast.walk(arvore):
            if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for sub in ast.walk(fn):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr in ("insert_one", "insert_many")
                    and isinstance(sub.func.value, ast.Attribute)
                    and sub.func.value.attr == "processes"
                ):
                    achados.append((f"services/{caminho.name}", fn.name))
                    break
    return achados


class TestOsEscritoresAplicamORegime:
    def test_o_leitor_encontra_os_escritores_conhecidos(self):
        achados = set(_escritores_de_processos())
        conhecidos = {
            ("services/client_assign.py", "run_assign_client_to_user"),
            ("services/onboarding_mandatory_config.py", "_criar_processo_do_onboarding"),
            ("services/client_process_ops.py", "run_create_process_for_client"),
            ("services/process_create.py", "persist_and_finalize_staff_create"),
            ("services/process_create.py", "persist_and_finalize_client_self_create"),
        }
        assert conhecidos <= achados, f"o leitor não viu: {conhecidos - achados} (cegueira)"

    def test_todo_o_escritor_aplica_o_regime_antes_de_gravar(self):
        em_falta = []
        for rel, nome in _escritores_de_processos():
            if (rel, nome) in EXCEPCOES:
                continue
            fonte = (BACKEND / rel).read_text(encoding="utf-8")
            fn = next(
                f for f in ast.walk(ast.parse(fonte))
                if isinstance(f, (ast.AsyncFunctionDef, ast.FunctionDef)) and f.name == nome
            )
            corpo = ast.get_source_segment(fonte, fn) or ""
            if "aplicar_regime_de_indexacao(" not in corpo:
                em_falta.append((rel, nome))
                continue
            assert corpo.index("aplicar_regime_de_indexacao(") < corpo.index("processes.insert_one("), (
                f"{rel}:{nome} aplica o regime DEPOIS de gravar"
            )
        assert not em_falta, f"escritores de processos sem o regime da satélite: {em_falta}"

    def test_as_excepcoes_escritas_ainda_existem(self):
        achados = set(_escritores_de_processos())
        for chave, motivo in EXCEPCOES.items():
            assert motivo and chave in achados, chave

    def test_o_escritor_da_ficha_do_cliente_carimba_a_rede(self):
        """Este escritor nunca carimbava: o processo da Domus caía na pilha
        por carimbar e desaparecia da Domus."""
        fonte = (BACKEND / "services" / "client_process_ops.py").read_text(encoding="utf-8")
        assert "resolve_tenant_stamp(user)" in fonte


# ════════════════════════════════════════════════════════════════════
# Encaminhamento B2B: o remetente escolhe a REDE, nunca a pessoa
# ════════════════════════════════════════════════════════════════════
def _processo_por_atribuir(db):
    p = _processo(db)
    for chave in ("assigned_consultor_id", "assigned_consultor_ids", "consultor_name", "consultor_names"):
        p.pop(chave, None)
    return p


def _com_intermediario_na_precision(db):
    db.users.docs.append({"id": "u-ines", "name": "Inês", "email": "i@p.pt", "role": "intermediario", "is_active": True})
    db.user_company_roles.docs.append(
        {"user_id": "u-ines", "company_id": "cmp-precision", "company_name": "Precision Crédito",
         "role": "intermediario", "is_default": True})
    return db


class TestORemetenteNuncaEscolheOUtilizador:
    @pytest.mark.asyncio
    async def test_via_verde_explicita_distribui_pela_equipa_do_DESTINO(self, fake_async_db):
        """A Domus envia em Via Verde: quem trata é gente da Precision, escolhida pelas
        regras de auto-atribuição do destino — nunca da Domus e nunca por quem remeteu."""
        import services.process_sharing as ps

        db = _com_intermediario_na_precision(_mundo(fake_async_db))
        _processo_por_atribuir(db)
        with _ambiente(db):
            r = await ps.partilhar_com_rede("p-domus", REDE_INCUMBENTE, via_verde=True, por_ordem_de="u-bruno")

        p = _processo(db)
        assert r["triagem"]["state"] == "via_verde"
        assert p["assigned_consultor_ids"] == ["u-cris"], "consultor do destino (a Dina é da Domus)"
        assert p["assigned_mediador_ids"] == ["u-ines"]
        assert p["network_id"] == REDE_DOMUS, "partilhar nunca muda de quem é"

    @pytest.mark.asyncio
    async def test_via_verde_nao_tira_a_quem_ja_la_estava(self, fake_async_db):
        """Quem já tratava o processo em casa continua: a distribuição só preenche o vazio."""
        import services.process_sharing as ps

        db = _com_intermediario_na_precision(_mundo(fake_async_db))
        with _ambiente(db):
            await ps.partilhar_com_rede("p-domus", REDE_INCUMBENTE, via_verde=True)
        p = _processo(db)
        assert p["assigned_consultor_ids"] == ["u-dina"]
        assert p["assigned_mediador_ids"] == ["u-ines"]

    @pytest.mark.asyncio
    async def test_destino_sem_gente_disponivel_nao_falha_e_fica_no_pool(self, fake_async_db):
        import services.process_sharing as ps

        db = _mundo(fake_async_db)
        _processo_por_atribuir(db)
        db.users.docs[:] = [u for u in db.users.docs if u["id"] not in {"u-cris"}]
        with _ambiente(db):
            r = await ps.partilhar_com_rede("p-domus", REDE_INCUMBENTE, via_verde=True)
        assert r["partilhado"] is True
        assert not _processo(db).get("assigned_consultor_ids")

    @pytest.mark.asyncio
    async def test_a_triagem_normal_continua_a_dar_so_o_indexador_do_destino(self, fake_async_db):
        import services.process_sharing as ps

        db = _com_intermediario_na_precision(_mundo(fake_async_db))
        _processo_por_atribuir(db)
        with _ambiente(db):
            await ps.partilhar_com_rede("p-domus", REDE_INCUMBENTE)
        p = _processo(db)
        assert p["assigned_indexacao_id"] == "u-ivo"
        assert not p.get("assigned_consultor_ids") and not p.get("assigned_mediador_ids"), \
            "o consultor só vem depois do Index"

    @pytest.mark.asyncio
    async def test_a_distribuicao_e_uma_ordem_do_servico_nao_do_pedido(self, fake_async_db):
        """Guarda de fonte: o `partilhar_com_rede` não tem parâmetro de utilizador a atribuir."""
        import inspect
        import services.process_sharing as ps

        parametros = set(inspect.signature(ps.partilhar_com_rede).parameters)
        assert not ({"user_id", "assigned_to", "consultor_id", "indexador_id", "utilizador"} & parametros), parametros
        assert "network_id" in parametros or "rede_destino" in parametros or len(parametros) >= 2

    def test_o_corpo_do_pedido_recusa_um_utilizador(self, cliente_http):
        c, db = cliente_http
        r = c.post("/processes/p-domus/partners", json={"network_id": "rede:omega", "user_id": "u-olga"})
        assert r.status_code == 422
        assert not _processo(db).get("partner_network_ids"), "nada foi partilhado"
        ok = c.post("/processes/p-domus/partners", json={"network_id": "rede:omega"})
        assert ok.status_code == 200


class TestAFilaAntigaEDoDestino:
    @pytest.mark.asyncio
    async def test_um_indexador_so_puxa_da_fila_da_sua_rede(self, fake_async_db):
        import services.process_assignment as pa

        db = _com_a_omega(_mundo(fake_async_db))
        db.processes.docs.append({
            "id": "p-fila-omega", "status": "fila_espera", "network_id": REDE_DOMUS,
            "created_at": "2026-01-01", "hub_triage": {"state": "triagem", "network_id": "rede:omega"},
        })
        db.processes.docs.append({
            "id": "p-fila-precision", "status": "fila_espera", "network_id": REDE_DOMUS,
            "created_at": "2026-01-02", "hub_triage": {"state": "triagem", "network_id": REDE_INCUMBENTE},
        })
        with _ambiente(db), patch("services.notification_service.send_notification_with_preference_check", AsyncMock()):
            n = await pa.process_queue_for_freed_indexer("u-ivo")  # indexador da Precision
        assert n == 1
        por_id = {p["id"]: p for p in db.processes.docs}
        assert por_id["p-fila-precision"]["assigned_indexacao_id"] == "u-ivo"
        assert por_id["p-fila-omega"]["status"] == "fila_espera", "a fila da Omega não é da Precision"
        assert not por_id["p-fila-omega"].get("assigned_indexacao_id")
