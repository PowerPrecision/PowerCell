"""
Bloco A, ponto 2 — Hub & Spoke: a triagem (Index) vive no Hub (Out 2026).

O PEDIDO
  * A Precision é o Hub (tem a equipa de Index). Na Domus (satélite) o
    processo avança internamente, sem passar pelo Index.
  * Se a Domus partilhar/atribuir um processo à Precision, esse processo
    entra IMEDIATAMENTE na fila de triagem (Index) da Precision.
  * `via_verde`: se estiver ligada, o processo partilhado salta o Index e
    vai direto para a consultoria.

O ACHADO QUE O TESTE DO DONO DA REDE REVELOU
  Os pools de auto-atribuição (indexador, consultor, mediador) liam
  `db.users` inteiro: um processo da Domus era dado a um indexador ou
  consultor da Precision SEM partilha nenhuma, e a Domus (que não tem
  Index) nunca teria um indexador seu. As equipas passam a ser da rede
  (`TestAEquipaEDaRede`).
"""
from __future__ import annotations

import ast
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE, tenant_db

BACKEND = Path(__file__).resolve().parents[2]

HUB = {"id": "cmp-precision", "name": "Precision Crédito", "network_id": REDE_INCUMBENTE, "is_hub": True}
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


def _mundo(fake_db, *, com_hub=True, processo=None):
    hub = dict(HUB)
    if not com_hub:
        hub.pop("is_hub")
    for empresa in (hub, POWER, DOMUS):
        fake_db.companies.docs.append(dict(empresa))
    fake_db.user_company_roles.docs.extend(dict(u) for u in UCRS)
    fake_db.users.docs.extend(dict(u) for u in USERS)
    fake_db.processes.docs.append(processo or {
        "id": "p-domus", "process_number": 7, "client_name": "Cliente D",
        "status": "novo", "network_id": REDE_DOMUS, "company_id": "cmp-domus",
        "skip_index": True, "index_dispensado_por": "rede_satelite",
        "assigned_consultor_id": "u-dina", "assigned_consultor_ids": ["u-dina"],
    })
    return fake_db


@contextlib.contextmanager
def _ambiente(db):
    import services.hub_triage as ht
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


ENTRADA_DO_HUB = {
    "company_id": "cmp-precision", "company_name": "Precision Crédito",
    "network_id": REDE_INCUMBENTE, "added_at": "x", "added_by": "u-dina",
}


def _processo(db, pid="p-domus"):
    return next(p for p in db.processes.docs if p["id"] == pid)


# ════════════════════════════════════════════════════════════════════
# Quem é o Hub
# ════════════════════════════════════════════════════════════════════
class TestQuemEOHub:
    @pytest.mark.asyncio
    async def test_o_hub_e_a_rede_das_empresas_marcadas(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db):
            assert await ht.hub_network_ids() == {REDE_INCUMBENTE}

    @pytest.mark.asyncio
    async def test_sem_empresa_marcada_nao_ha_hub(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db, com_hub=False)
        with _ambiente(db):
            assert await ht.hub_network_ids() == set()

    @pytest.mark.asyncio
    async def test_so_o_booleano_true_conta(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        db.companies.docs[0]["is_hub"] = "true"
        with _ambiente(db):
            assert await ht.hub_network_ids() == set()


# ════════════════════════════════════════════════════════════════════
# O regime da satélite: nasce sem Index
# ════════════════════════════════════════════════════════════════════
class TestASateliteNaoTemIndex:
    @pytest.mark.asyncio
    async def test_um_processo_da_domus_nasce_dispensado_do_index(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        doc = {"id": "n", "network_id": REDE_DOMUS}
        with _ambiente(db):
            assert await ht.aplicar_regime_de_indexacao(doc) is True
        assert doc["skip_index"] is True
        assert doc["index_dispensado_por"] == "rede_satelite"

    @pytest.mark.asyncio
    async def test_um_processo_do_hub_passa_pelo_index(self, fake_async_db):
        """Contraprova: tirar o Index a toda a gente passaria no teste acima."""
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        doc = {"id": "n", "network_id": REDE_INCUMBENTE}
        with _ambiente(db):
            assert await ht.aplicar_regime_de_indexacao(doc) is False
        assert "skip_index" not in doc

    @pytest.mark.asyncio
    async def test_sem_hub_configurado_nada_muda_nem_para_a_domus(self, fake_async_db):
        """Sem Hub, TODAS as redes seriam satélites — inclusive a Precision."""
        import services.hub_triage as ht

        db = _mundo(fake_async_db, com_hub=False)
        doc = {"id": "n", "network_id": REDE_DOMUS}
        with _ambiente(db):
            assert await ht.aplicar_regime_de_indexacao(doc) is False
        assert "skip_index" not in doc

    @pytest.mark.asyncio
    async def test_um_processo_por_carimbar_nao_perde_o_index(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        doc = {"id": "n"}
        with _ambiente(db):
            assert await ht.aplicar_regime_de_indexacao(doc) is False
        assert "skip_index" not in doc

    @pytest.mark.asyncio
    async def test_uma_falha_a_ler_o_hub_nao_parte_a_criacao(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        doc = {"id": "n", "network_id": REDE_DOMUS}
        with _ambiente(db), patch.object(ht, "hub_network_ids", AsyncMock(side_effect=RuntimeError("x"))):
            assert await ht.aplicar_regime_de_indexacao(doc) is False


# ════════════════════════════════════════════════════════════════════
# A decisão (pura)
# ════════════════════════════════════════════════════════════════════
class TestDecidirEntrada:
    def test_partilha_normal_entra_em_triagem(self):
        from services.hub_triage import decidir_entrada

        d = decidir_entrada({"id": "p"}, redes_do_hub_convidadas=["hub"])
        assert d["state"] == "triagem" and d["network_id"] == "hub"

    def test_via_verde_salta_o_index(self):
        from services.hub_triage import decidir_entrada

        d = decidir_entrada({"via_verde": True}, redes_do_hub_convidadas=["hub"])
        assert d["state"] == "via_verde" and d["motivo"] == "via_verde"

    @pytest.mark.parametrize("valor", ["true", 1, "sim", None, False])
    def test_so_o_booleano_true_liga_a_via_verde(self, valor):
        from services.hub_triage import decidir_entrada

        d = decidir_entrada({"via_verde": valor}, redes_do_hub_convidadas=["hub"])
        assert d["state"] == "triagem"

    def test_um_processo_ja_indexado_nao_tem_nada_a_triar(self):
        from services.hub_triage import decidir_entrada

        d = decidir_entrada({"is_indexed": True}, redes_do_hub_convidadas=["hub"])
        assert d["state"] == "via_verde" and d["motivo"] == "ja_indexado"

    def test_o_primeiro_registo_ganha(self):
        from services.hub_triage import decidir_entrada

        assert decidir_entrada(
            {"hub_triage": {"state": "triagem"}, "via_verde": True},
            redes_do_hub_convidadas=["hub"],
        ) is None

    def test_sem_rede_do_hub_nao_ha_nada_a_fazer(self):
        from services.hub_triage import decidir_entrada

        assert decidir_entrada({}, redes_do_hub_convidadas=[]) is None


# ════════════════════════════════════════════════════════════════════
# A entrada na triagem do Hub (com a base de dados)
# ════════════════════════════════════════════════════════════════════
class TestEntradaNaTriagemDoHub:
    @pytest.mark.asyncio
    async def test_a_partilha_poe_o_processo_na_fila_do_index_do_hub(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db):
            registo = await ht.entrar_na_triagem_do_hub("p-domus", [ENTRADA_DO_HUB], por_ordem_de="u-dina")

        p = _processo(db)
        assert registo["state"] == "triagem"
        assert p["hub_triage"]["state"] == "triagem"
        assert p["hub_triage"]["network_id"] == REDE_INCUMBENTE
        assert p["skip_index"] is False, "a triagem do Hub exige o Index"
        # O indexador sai do pool do HUB.
        assert p["assigned_indexacao_id"] == "u-ivo"

    @pytest.mark.asyncio
    async def test_via_verde_salta_o_index_e_nao_atribui_indexador(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        _processo(db)["via_verde"] = True
        with _ambiente(db):
            registo = await ht.entrar_na_triagem_do_hub("p-domus", [ENTRADA_DO_HUB])

        p = _processo(db)
        assert registo["state"] == "via_verde"
        assert p["skip_index"] is True, "a Via Verde não repõe o Index"
        assert not p.get("assigned_indexacao_id")

    @pytest.mark.asyncio
    async def test_sem_indexador_no_hub_fica_na_fila_e_nao_falha(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        db.users.docs[:] = [u for u in db.users.docs if u["id"] != "u-ivo"]
        with _ambiente(db):
            registo = await ht.entrar_na_triagem_do_hub("p-domus", [ENTRADA_DO_HUB])

        p = _processo(db)
        assert registo["state"] == "triagem"
        assert not p.get("assigned_indexacao_id")

    @pytest.mark.asyncio
    async def test_e_idempotente_e_o_primeiro_registo_ganha(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db):
            primeiro = await ht.entrar_na_triagem_do_hub("p-domus", [ENTRADA_DO_HUB])
            _processo(db)["via_verde"] = True  # ligar depois não reabre nem fecha
            segundo = await ht.entrar_na_triagem_do_hub("p-domus", [ENTRADA_DO_HUB])

        assert primeiro is not None and segundo is None
        assert _processo(db)["hub_triage"]["state"] == "triagem"

    @pytest.mark.asyncio
    async def test_partilhar_com_uma_rede_que_nao_e_hub_nao_faz_nada(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        outra = {"company_id": "x", "company_name": "X", "network_id": "rede:x"}
        with _ambiente(db):
            assert await ht.entrar_na_triagem_do_hub("p-domus", [outra]) is None
        assert "hub_triage" not in _processo(db)

    @pytest.mark.asyncio
    async def test_deixa_rasto_no_historico_e_no_trilho(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db), patch("services.history.log_history", AsyncMock()) as hist, \
                patch("services.audit_trail_service.log_audit_event", AsyncMock()) as trilho:
            await ht.entrar_na_triagem_do_hub("p-domus", [ENTRADA_DO_HUB], por_ordem_de="u-dina")

        assert hist.await_count >= 1
        assert trilho.await_args.kwargs["action"] == "hub_triage_entered"

    @pytest.mark.asyncio
    async def test_a_versao_dos_escritores_nunca_propaga(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        with _ambiente(db), patch.object(ht, "entrar_na_triagem_do_hub", AsyncMock(side_effect=RuntimeError("x"))):
            assert await ht.entrar_na_triagem_do_hub_sem_falhar("p-domus", [ENTRADA_DO_HUB]) is None


# ════════════════════════════════════════════════════════════════════
# A ligação: partilhar (por atribuição) dispara a triagem
# ════════════════════════════════════════════════════════════════════
class TestAPartilhaDisparaATriagem:
    @pytest.mark.asyncio
    async def test_atribuir_alguem_do_hub_a_um_processo_da_domus_entra_na_triagem(self, fake_async_db):
        """Fim a fim: a Via Rápida abre a partilha e a partilha abre a triagem."""
        import services.process_sharing as ps

        db = _mundo(fake_async_db)
        p = _processo(db)
        p["assigned_consultor_ids"] = ["u-cris"]  # alguém da Precision
        p["assigned_consultor_id"] = "u-cris"
        with _ambiente(db):
            novas = await ps.sincronizar_parceiros("p-domus", por_ordem_de="u-bruno")

        assert [n["network_id"] for n in novas] == [REDE_INCUMBENTE]
        assert _processo(db)["hub_triage"]["state"] == "triagem"

    @pytest.mark.asyncio
    async def test_com_via_verde_a_partilha_fica_a_cargo_da_consultoria(self, fake_async_db):
        import services.process_sharing as ps

        db = _mundo(fake_async_db)
        p = _processo(db)
        p.update({"assigned_consultor_ids": ["u-cris"], "assigned_consultor_id": "u-cris", "via_verde": True})
        with _ambiente(db):
            await ps.sincronizar_parceiros("p-domus", por_ordem_de="u-bruno")

        assert _processo(db)["hub_triage"]["state"] == "via_verde"
        assert _processo(db)["skip_index"] is True

    @pytest.mark.asyncio
    async def test_uma_atribuicao_dentro_da_domus_nao_toca_na_triagem(self, fake_async_db):
        import services.process_sharing as ps

        db = _mundo(fake_async_db)
        with _ambiente(db):
            novas = await ps.sincronizar_parceiros("p-domus", por_ordem_de="u-bruno")

        assert novas == []
        assert "hub_triage" not in _processo(db)

    def test_a_ligacao_existe_no_codigo(self):
        """Contraprova da ligação: sem ela a triagem é código morto."""
        fonte = (BACKEND / "services" / "process_sharing.py").read_text(encoding="utf-8")
        assert "entrar_na_triagem_do_hub_sem_falhar(" in fonte


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
    async def test_o_indexador_da_triagem_sai_do_pool_do_hub_e_nao_do_mundo(self, fake_async_db):
        """Com uma indexadora da Domus à frente na lista, escolher à ordem
        do Mongo daria a ela — o teste só morde se o pool for filtrado."""
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        db.users.docs.insert(0, {"id": "u-ines", "name": "Inês", "email": "i@d.pt", "role": "indexacao", "is_active": True})
        db.user_company_roles.docs.append(
            {"user_id": "u-ines", "company_id": "cmp-domus", "company_name": "Domus", "role": "indexacao", "is_default": True}
        )
        with _ambiente(db):
            await ht.entrar_na_triagem_do_hub("p-domus", [ENTRADA_DO_HUB])

        assert _processo(db)["assigned_indexacao_id"] == "u-ivo"

    @pytest.mark.asyncio
    async def test_sem_hub_o_pool_de_indexadores_continua_a_ser_o_da_propria_rede(self, fake_async_db):
        import services.process_assignment as pa

        db = _mundo(fake_async_db, com_hub=False)
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
    async def test_depois_da_triagem_a_equipa_e_a_do_hub(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        assert ht.rede_da_equipa(_processo(db)) == REDE_DOMUS
        _processo(db)["hub_triage"] = {"state": "triagem", "network_id": REDE_INCUMBENTE}
        assert ht.rede_da_equipa(_processo(db)) == REDE_INCUMBENTE

    @pytest.mark.asyncio
    async def test_membros_da_rede_por_ucr_e_por_conta_antiga(self, fake_async_db):
        import services.hub_triage as ht

        db = _mundo(fake_async_db)
        db.users.docs.append({"id": "u-velho", "name": "V", "role": "consultor", "company": "Domus", "is_active": True})
        with _ambiente(db):
            assert await ht.user_ids_da_rede(REDE_DOMUS) == {"u-dina", "u-bruno", "u-velho"}
            assert await ht.user_ids_da_rede("") is None
            assert await ht.user_ids_da_rede("rede:inexistente") == set()


# ════════════════════════════════════════════════════════════════════
# Quem pode marcar o Hub
# ════════════════════════════════════════════════════════════════════
class TestSoOMasterMarcaOHub:
    @pytest.mark.asyncio
    async def test_um_admin_local_nao_marca_o_hub(self, fake_async_db):
        from fastapi import HTTPException

        import services.companies_crud_api_mutate as m
        from models.company import CompanyUpdate

        db = _mundo(fake_async_db)
        admin = {"id": "u-adm", "role": "admin"}
        with _ambiente(db), patch.object(m, "db", db), \
                patch.object(m, "exigir_empresas_concediveis", AsyncMock()):
            with pytest.raises(HTTPException) as erro:
                await m.run_update_company("cmp-domus", CompanyUpdate(is_hub=True), actor=admin)
        assert erro.value.status_code == 403
        assert "is_hub" not in next(c for c in db.companies.docs if c["id"] == "cmp-domus")

    @pytest.mark.asyncio
    async def test_o_master_marca_o_hub(self, fake_async_db):
        import services.companies_crud_api_mutate as m
        from models.company import CompanyUpdate

        db = _mundo(fake_async_db)
        master = {"id": "u-m", "role": "master"}
        with _ambiente(db), patch.object(m, "db", db), \
                patch.object(m, "exigir_empresas_concediveis", AsyncMock()):
            await m.run_update_company("cmp-power", CompanyUpdate(is_hub=True), actor=master)
        assert next(c for c in db.companies.docs if c["id"] == "cmp-power")["is_hub"] is True

    def test_uma_empresa_nova_nao_e_hub(self):
        from models.company import CompanyCreate

        assert CompanyCreate(name="Nova").is_hub is False


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
