"""
Um processo em fase terminal não se altera: a equipa tem de o REABRIR primeiro.

O ACHADO
  O Portal do Cliente já fechava com o processo. O CRM não: o único bloqueio
  era no `PUT /processes/{id}` e (1) corria depois de gravar a ficha do
  cliente e a troca de titular, (2) isentava Master/Admin/CEO e (3) o resto
  do CRM — atribuições, notas, uploads, mover/renomear/eliminar documentos,
  pedidos ao Portal — nem perguntava.

COMO SE TESTA
  * a dependência lê `request.path_params`: monta-se uma aplicação com os
    ROUTERS REAIS e as rotas saem DOS ROUTERS (uma rota nova entra sozinha);
  * a ordem das verificações é comportamento: a escrita do cliente no `PUT`
    nunca pode ter acontecido quando o 403 chega;
  * «está fechado» não é um oráculo sobre um processo de outra rede.
"""
from __future__ import annotations

import ast
import contextlib
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from services import process_closed_guard as guarda
from services.auth import get_current_user
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

RAIZ = Path(__file__).resolve().parents[2]

MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "M"}
ANA = {"id": "u-ana", "role": "diretor", "effective_role": "diretor", "name": "Ana"}      # Power
BRUNO = {"id": "u-bruno", "role": "diretor", "effective_role": "diretor", "name": "Bruno"}  # Domus

FECHADO = "p-fechado"
ABERTO = "p-aberto"
FECHADO_DA_POWER = "p-fechado-power"


def _modulos_dos_routers():
    import routes.documents as documentos
    import routes.onedrive as onedrive
    import routes.processes as processos
    import routes.storage as storage
    import routes.voice_notes as notas_de_voz

    return {
        "processes": processos, "documents": documentos, "onedrive": onedrive,
        "storage": storage, "voice_notes": notas_de_voz,
    }


def _rotas_de_escrita_com_process_id() -> list[tuple[str, str, str]]:
    """(router, método, caminho) de TODAS as rotas de escrita com `{process_id}`."""
    achadas = []
    for nome, modulo in _modulos_dos_routers().items():
        for rota in modulo.router.routes:
            if not isinstance(rota, APIRoute) or "{process_id}" not in rota.path:
                continue
            for metodo in sorted(rota.methods - {"GET", "HEAD", "OPTIONS"}):
                achadas.append((nome, metodo, rota.path))
    return achadas


def _preencher(caminho: str, process_id: str) -> str:
    caminho = caminho.replace("{process_id}", process_id)
    return re.sub(r"\{\w+(:\w+)?\}", "x", caminho)


def _permitida(metodo: str, caminho: str) -> bool:
    return any(
        metodo == m and caminho.endswith(sufixo)
        for (m, sufixo) in guarda.ROTAS_QUE_FUNCIONAM_COM_O_PROCESSO_FECHADO
    )


def _cenario(fake_db):
    semear(fake_db)
    fake_db.user_company_roles.docs.append(
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "master", "is_default": True}
    )
    fake_db.processes.docs.extend([
        {"id": FECHADO, "status": "concluido", "client_name": "Fechado"},
        {"id": ABERTO, "status": "fase_bancaria", "client_name": "Aberto"},
        {"id": FECHADO_DA_POWER, "status": "concluido", "client_name": "Da Power",
         "company_id": "cmp-power", "network_id": "grupo_power_precision"},
    ])
    return fake_db


@pytest.fixture
def app_e_cliente(fake_async_db, rede_de_omissao_incumbente):
    """Os routers REAIS, o utilizador activo à escolha e a BD falsa em toda a cadeia."""
    import services.auth as auth_mod
    import services.process_scope_guard as psg
    import services.workflow_phases as wp

    _cenario(fake_async_db)
    atual = {"user": MASTER}

    app = FastAPI()
    for modulo in _modulos_dos_routers().values():
        app.include_router(modulo.router)
    app.dependency_overrides[get_current_user] = lambda: atual["user"]

    with tenant_db(fake_async_db, guarda, auth_mod, psg, wp):
        cliente = TestClient(app, raise_server_exceptions=False)
        cliente.definir_utilizador = lambda u: atual.update(user=u)
        yield cliente


def _fechou(resposta) -> bool:
    return resposta.status_code == 403 and "fechado" in resposta.text


# ====================================================================
# A REGRA PURA
# ====================================================================

class TestSeOProcessoEstaFechado:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", ["concluido", "concluidos", "cancelado", "arquivo"])
    async def test_as_fases_terminais_fecham(self, fake_async_db, estado):
        with tenant_db(fake_async_db, guarda):
            assert await guarda.processo_esta_fechado({"id": "p", "status": estado}) is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", ["fase_bancaria", "novo", "cpcv"])
    async def test_as_fases_activas_nao_fecham(self, fake_async_db, estado):
        with tenant_db(fake_async_db, guarda):
            assert await guarda.processo_esta_fechado({"id": "p", "status": estado}) is False

    @pytest.mark.asyncio
    async def test_sem_processo_ou_sem_fase_nao_ha_o_que_fechar(self, fake_async_db):
        with tenant_db(fake_async_db, guarda):
            assert await guarda.processo_esta_fechado(None) is False
            assert await guarda.processo_esta_fechado({"id": "p"}) is False
            await guarda.exigir_processo_aberto(None)

    @pytest.mark.asyncio
    async def test_sem_fase_nem_se_vai_a_base_de_dados(self):
        """Um processo sem fase (lead) não custa uma leitura das fases."""
        carregar = AsyncMock(return_value=[])
        with patch.object(guarda, "carregar_fases", carregar):
            assert await guarda.processo_esta_fechado({"id": "p"}) is False
        carregar.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uma_fase_fechada_pelo_admin_no_motor_tambem_fecha(self, fake_async_db):
        """A autoridade é o MOTOR (`is_active: False`), não uma lista no código."""
        fake_async_db.workflow_statuses.docs.append(
            {"name": "renegociacao", "label": "Renegociação", "is_active": False, "order": 1})
        with tenant_db(fake_async_db, guarda):
            import services.workflow_phases as wp
            wp.invalidar_cache_de_fases()
            assert await guarda.processo_esta_fechado({"id": "p", "status": "renegociacao"}) is True

    @pytest.mark.asyncio
    async def test_a_recusa_e_403_e_diz_como_sair(self, fake_async_db):
        with tenant_db(fake_async_db, guarda):
            with pytest.raises(HTTPException) as exc:
                await guarda.exigir_processo_aberto({"id": "p", "status": "concluido"})
        assert exc.value.status_code == 403
        assert "Reabra" in exc.value.detail


# ====================================================================
# AS ROTAS — saem dos routers, uma rota nova entra sozinha
# ====================================================================

class TestAsRotasDeEscritaRecusamUmProcessoFechado:
    def test_o_leitor_das_rotas_le_mesmo_os_routers(self):
        """Contraprova: sem ela, uma lista vazia dava testes parametrizados vazios."""
        rotas = _rotas_de_escrita_com_process_id()
        assert len(rotas) >= 25
        caminhos = {(m, c) for (_n, m, c) in rotas}
        assert ("POST", "/processes/{process_id}/assign") in caminhos
        assert ("POST", "/documents/rename-smart/{process_id}") in caminhos
        assert ("POST", "/processes/{process_id}/voice-notes") in caminhos

    @pytest.mark.parametrize("router,metodo,caminho", _rotas_de_escrita_com_process_id())
    def test_fechado_recusa_e_o_handler_nem_corre(self, app_e_cliente, router, metodo, caminho):
        resposta = app_e_cliente.request(metodo, _preencher(caminho, FECHADO))
        if _permitida(metodo, caminho):
            assert not _fechou(resposta), f"{metodo} {caminho} devia funcionar fechado"
        else:
            assert _fechou(resposta), f"{metodo} {caminho} → {resposta.status_code} {resposta.text[:120]}"

    @pytest.mark.parametrize("router,metodo,caminho", _rotas_de_escrita_com_process_id())
    def test_aberto_a_guarda_nao_atrapalha(self, app_e_cliente, router, metodo, caminho):
        """Contraprova: uma guarda que recusasse sempre passava o teste de cima."""
        resposta = app_e_cliente.request(metodo, _preencher(caminho, ABERTO))
        assert not _fechou(resposta), f"{metodo} {caminho} → {resposta.text[:120]}"

    def test_um_id_que_nao_existe_e_resposta_do_handler(self, app_e_cliente):
        resposta = app_e_cliente.post(_preencher("/processes/{process_id}/assign", "nao-existe"))
        assert not _fechou(resposta)

    def test_a_leitura_nunca_e_bloqueada(self, app_e_cliente):
        assert not _fechou(app_e_cliente.get(f"/processes/{FECHADO}"))
        assert not _fechou(app_e_cliente.get(f"/documents/process/{FECHADO}"))

    def test_o_master_tambem_e_bloqueado(self, app_e_cliente):
        """Sem bypass: o ecrã trata toda a gente por igual."""
        app_e_cliente.definir_utilizador(MASTER)
        resposta = app_e_cliente.post(f"/processes/{FECHADO}/assign")
        assert _fechou(resposta)


class TestSemOraculo:
    """«Está fechado» não pode confirmar o estado de um processo de outra rede."""

    def test_a_rede_dona_ve_o_fechado(self, app_e_cliente):
        app_e_cliente.definir_utilizador(ANA)
        resposta = app_e_cliente.post(f"/documents/categorize/{FECHADO_DA_POWER}")
        assert _fechou(resposta)

    def test_outra_rede_nao_ve_o_estado(self, app_e_cliente):
        app_e_cliente.definir_utilizador(BRUNO)
        resposta = app_e_cliente.post(f"/documents/categorize/{FECHADO_DA_POWER}")
        assert not _fechou(resposta)

    def test_no_router_dos_processos_outra_rede_recebe_o_404_de_sempre(self, app_e_cliente):
        app_e_cliente.definir_utilizador(BRUNO)
        resposta = app_e_cliente.post(f"/processes/{FECHADO_DA_POWER}/assign")
        assert resposta.status_code == 404


# ====================================================================
# OS INVENTÁRIOS — uma rota ou um router novo não pode escapar
# ====================================================================

class TestInventarios:
    def test_todos_os_routers_de_escrita_levam_a_dependencia(self):
        for nome, modulo in _modulos_dos_routers().items():
            dependencias = [d.dependency for d in modulo.router.dependencies]
            assert guarda.exigir_processo_editavel in dependencias, nome

    def test_no_router_dos_processos_a_rede_vem_ANTES_do_estado(self):
        """Senão «está fechado» respondia antes do 404 de outra rede."""
        from services.process_scope_guard import exigir_processo_no_ambito

        dependencias = [d.dependency for d in _modulos_dos_routers()["processes"].router.dependencies]
        assert dependencias.index(exigir_processo_no_ambito) < dependencias.index(
            guarda.exigir_processo_editavel)

    def test_cada_excepcao_tem_motivo_e_corresponde_a_uma_rota_real(self):
        reais = {(m, c) for (_n, m, c) in _rotas_de_escrita_com_process_id()}
        for (metodo, sufixo), motivo in guarda.ROTAS_QUE_FUNCIONAM_COM_O_PROCESSO_FECHADO.items():
            assert len(motivo.strip()) > 20, (metodo, sufixo)
            assert any(m == metodo and c.endswith(sufixo) for (m, c) in reais), (
                f"{metodo} {sufixo} já não existe: a excepção ficou órfã"
            )

    #: Routers que escrevem com `{process_id}` no caminho e NÃO levam a
    #: dependência — cada um com o motivo. Um router novo aqui falha o teste.
    FORA_DA_GUARDA = {
        "admin.py": "Ferramentas de administração do Master sobre registos de clientes.",
        "admin_encryption.py": "Infraestrutura do Master (encriptação); não edita dados de negócio.",
        "ai_analysis.py": "Gera uma análise de IA guardada à parte; não altera os campos do processo.",
        "alerts.py": "Cria um lembrete de escritura; não altera o processo.",
        "clients.py": "Desligar um cliente de um processo (D-31): pertence à ficha do cliente.",
        "document_extraction.py": "Só LÊ o ficheiro e propõe; quem grava é outra rota.",
        "emails.py": "Comunicação e sincronização de correio; não alteram os dados do processo.",
        "portal_admin.py": "«Ver como cliente»: abre o Portal, que se bloqueia a si próprio.",
        "restore.py": "Repor um processo eliminado: tem de funcionar sobre o que está fechado.",
        "templates.py": "Pede documentos ao cliente por email; não altera o processo.",
    }

    def test_nenhum_outro_router_escreve_num_processo_sem_estar_justificado(self):
        cobertos = {f"{n}.py" for n in _modulos_dos_routers()}
        encontrados: set[str] = set()
        for ficheiro in sorted((RAIZ / "routes").glob("*.py")):
            if ficheiro.name in cobertos:
                continue
            arvore = ast.parse(ficheiro.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for dec in no.decorator_list:
                    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                        continue
                    if dec.func.attr not in {"post", "put", "patch", "delete"}:
                        continue
                    if dec.args and isinstance(dec.args[0], ast.Constant) \
                            and "{process_id}" in str(dec.args[0].value):
                        encontrados.add(ficheiro.name)
        assert encontrados == set(self.FORA_DA_GUARDA), (
            f"routers com escrita em {{process_id}}: {sorted(encontrados)} "
            f"(justificados: {sorted(self.FORA_DA_GUARDA)})"
        )


# ====================================================================
# OS SERVIÇOS — o processo que não vem no caminho
# ====================================================================

class TestUploadsEEliminacoes:
    @pytest.mark.asyncio
    async def test_carregar_ficheiros_para_um_processo_fechado_e_403(self, fake_async_db):
        import services.document_visibility as dv

        with tenant_db(fake_async_db, guarda), \
                patch.object(dv, "assert_can_view_process_documents", AsyncMock()):
            with pytest.raises(HTTPException) as exc:
                await dv.assert_can_upload_to_process(MASTER, {"id": "p", "status": "concluido"})
        assert exc.value.status_code == 403 and "Reabra" in exc.value.detail

    @pytest.mark.asyncio
    async def test_a_um_processo_aberto_continua_a_poder(self, fake_async_db):
        import services.document_visibility as dv

        with tenant_db(fake_async_db, guarda), \
                patch.object(dv, "assert_can_view_process_documents", AsyncMock()):
            await dv.assert_can_upload_to_process(MASTER, {"id": "p", "status": "fase_bancaria"})

    @pytest.mark.asyncio
    async def test_a_visibilidade_vem_primeiro_sem_oraculo(self, fake_async_db):
        """Quem não pode ver o processo recebe a recusa da visibilidade, não «fechado»."""
        import services.document_visibility as dv

        negado = HTTPException(status_code=403, detail="sem acesso")
        with tenant_db(fake_async_db, guarda), \
                patch.object(dv, "assert_can_view_process_documents", AsyncMock(side_effect=negado)):
            with pytest.raises(HTTPException) as exc:
                await dv.assert_can_upload_to_process(ANA, {"id": "p", "status": "concluido"})
        assert exc.value.detail == "sem acesso"

    @pytest.mark.asyncio
    async def test_eliminar_um_ficheiro_de_um_processo_fechado_nao_toca_no_S3(self, fake_async_db):
        import services.document_delete as dd

        s3 = MagicMock()
        with tenant_db(fake_async_db, guarda), \
                patch.object(dd, "resolve_process_from_flexible_id",
                             AsyncMock(return_value=({"id": "p", "status": "concluido"}, "p"))), \
                patch.object(dd, "assert_s3_file_belongs_to_process", MagicMock()), \
                patch.object(dd, "s3_service", s3):
            with pytest.raises(HTTPException) as exc:
                await dd.run_delete_file_s3("p", "Documentação Clientes/p/x.pdf", user=MASTER)
        assert exc.value.status_code == 403
        s3.delete_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_eliminar_em_massa_de_um_processo_fechado_nao_toca_no_S3(self, fake_async_db):
        import services.document_delete as dd

        s3 = MagicMock()
        with tenant_db(fake_async_db, guarda), \
                patch.object(dd, "resolve_process_from_flexible_id",
                             AsyncMock(return_value=({"id": "p", "status": "concluido"}, "p"))), \
                patch.object(dd, "s3_service", s3):
            with pytest.raises(HTTPException) as exc:
                await dd.run_bulk_delete_files(
                    "p", {"file_paths": ["Documentação Clientes/p/x.pdf"]}, user=MASTER)
        assert exc.value.status_code == 403
        s3.delete_file.assert_not_called()


class TestOPutRecusaAntesDeGravar:
    """O defeito original: o 403 chegava com a ficha do cliente já alterada."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["consultor", "admin", "ceo", "master"])
    async def test_nada_foi_gravado_quando_o_processo_esta_fechado(self, fake_async_db, papel):
        import services.process_update as pu
        from models.process import ProcessUpdate

        fake_async_db.processes.docs.append(
            {"id": "proc-1", "status": "concluido", "client_id": "cli-1", "client_email": ""})
        escreve_cliente = AsyncMock()
        troca_titular = AsyncMock()
        nada = AsyncMock(return_value=None)

        pedido = MagicMock()
        pedido.headers = {}
        pedido.state = type("E", (), {})()
        pedido.json = AsyncMock(return_value={"nome": "Novo Nome", "client_id": "cli-2"})

        with tenant_db(fake_async_db, guarda), \
                patch.object(pu, "db", fake_async_db), \
                patch.object(pu, "apply_client_personal_updates_from_process_put", escreve_cliente), \
                patch.object(pu, "maybe_reassign_primary_client_with_audit", troca_titular):
            with pytest.raises(HTTPException) as exc:
                await pu.run_update_process(
                    "proc-1", ProcessUpdate(), pedido,
                    {"id": "u1", "role": papel, "name": "T"},
                    decrypt_fn=lambda d, *a, **k: d, populate_fn=lambda d, *a, **k: d,
                    extract_client_updates_fn=lambda _b: {"nome": "Novo Nome"},
                    inject_cdc_fn=lambda _d, _u: None, broadcast_fn=nada,
                    ensure_finance_snapshot_fn=nada, log_history_fn=nada,
                    log_audit_event_fn=nada, cliente_role="cliente",
                )
        assert exc.value.status_code == 403
        escreve_cliente.assert_not_awaited()
        troca_titular.assert_not_awaited()
        assert fake_async_db.processes.docs[-1]["status"] == "concluido"


# ====================================================================
# REABRIR
# ====================================================================

class TestReabrir:
    FASES = [
        {"name": "fase_bancaria", "is_active": True, "order": 1},
        {"name": "cpcv", "is_active": True, "order": 2},
        {"name": "concluido", "is_active": False, "order": 3},
    ]

    def _preparar(self, fake_db, estado="concluido"):
        import services.workflow_phases as wp

        fake_db.workflow_statuses.docs.extend(dict(f) for f in self.FASES)
        fake_db.processes.docs.append({"id": "p1", "status": estado})
        wp.invalidar_cache_de_fases()

    async def _reabrir(self, fake_db, destino, *, pode_ver=True):
        import services.process_reopen as pr

        mover = AsyncMock(return_value={"message": "Processo movido com sucesso", "new_status": destino})
        with tenant_db(fake_db, guarda, pr), patch.object(pr, "run_move_process_kanban", mover):
            resultado = await pr.run_reopen_process(
                "p1", destino, MASTER,
                can_view_fn=lambda _u, _p: pode_ver, inject_cdc_fn=MagicMock(),
                broadcast_fn=AsyncMock(), create_finance_snapshot_fn=AsyncMock(),
            )
        return resultado, mover

    @pytest.mark.asyncio
    async def test_reabre_para_uma_fase_activa_pelo_movimento_de_fase(self, fake_async_db):
        self._preparar(fake_async_db)
        resultado, mover = await self._reabrir(fake_async_db, "cpcv")
        mover.assert_awaited_once()
        assert mover.await_args.args[:2] == ("p1", "cpcv")
        assert resultado["reopened"] is True

    @pytest.mark.asyncio
    async def test_reabrir_um_processo_aberto_e_400_e_nao_move(self, fake_async_db):
        self._preparar(fake_async_db, estado="fase_bancaria")
        with pytest.raises(HTTPException) as exc:
            await self._reabrir(fake_async_db, "cpcv")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("destino", ["concluido", "nao_existe", ""])
    async def test_o_destino_tem_de_ser_uma_fase_activa(self, fake_async_db, destino):
        self._preparar(fake_async_db)
        import services.process_reopen as pr

        mover = AsyncMock()
        with tenant_db(fake_async_db, guarda, pr), patch.object(pr, "run_move_process_kanban", mover):
            with pytest.raises(HTTPException) as exc:
                await pr.run_reopen_process(
                    "p1", destino, MASTER, can_view_fn=lambda *_: True,
                    inject_cdc_fn=MagicMock(), broadcast_fn=AsyncMock(),
                    create_finance_snapshot_fn=AsyncMock(),
                )
        assert exc.value.status_code == 400
        mover.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sem_permissao_para_ver_e_403(self, fake_async_db):
        self._preparar(fake_async_db)
        with pytest.raises(HTTPException) as exc:
            await self._reabrir(fake_async_db, "cpcv", pode_ver=False)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_processo_inexistente_e_404(self, fake_async_db):
        import services.process_reopen as pr

        with tenant_db(fake_async_db, guarda, pr):
            with pytest.raises(HTTPException) as exc:
                await pr.run_reopen_process(
                    "nada", "cpcv", MASTER, can_view_fn=lambda *_: True,
                    inject_cdc_fn=MagicMock(), broadcast_fn=AsyncMock(),
                    create_finance_snapshot_fn=AsyncMock(),
                )
        assert exc.value.status_code == 404

    def test_a_rota_de_reabrir_existe_e_esta_na_lista_de_excepcoes(self):
        reais = {(m, c) for (_n, m, c) in _rotas_de_escrita_com_process_id()}
        assert ("POST", "/processes/{process_id}/reopen") in reais
        assert _permitida("POST", "/processes/{process_id}/reopen")
