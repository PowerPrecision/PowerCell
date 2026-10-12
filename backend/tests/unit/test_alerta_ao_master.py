"""
Alerta ao Master quando um perfil LOCAL repõe o workflow ou o formulário ao modelo.

O QUE SE GARANTE
  * EXCLUSIVAMENTE o Master recebe (notificação interna por destinatário + email urgente): nem o
    autor, nem o Admin/CEO da rede, nem o de outra rede, nem um Master inactivo;
  * o aviso diz QUEM fez e EM QUE REDE (no título — é o que o sino mostra);
  * só dispara quando a reposição ACONTECEU: password errada, pedido sem efeito (a rede já usava o
    modelo), 409 por processos em curso e rede fora do âmbito não alertam;
  * um Master a trabalhar como Master não se avisa a si próprio; um Master com o chapéu de Admin
    avisa os OUTROS Master;
  * o alerta nunca derruba a operação (nem a notificação nem o email);
  * a password nunca aparece no aviso.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services import workflow_phases as wp
from services.auth import hash_password
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

SENHA = "Segredo-Certo-9!"

MODELO = [
    {"id": "m-novo", "name": "novo", "label": "Novo", "order": 1, "is_active": True},
    {"id": "m-concluidos", "name": "concluidos", "label": "Concluídos", "order": 2, "is_active": False},
]

ADMIN = {"id": "u-admin", "role": "admin", "effective_role": "admin", "name": "Ana Admin", "email": "ana@power.pt"}
CEO = {"id": "u-ceo", "role": "ceo", "effective_role": "ceo", "name": "Carlos CEO", "email": "carlos@power.pt"}
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Mário Master", "email": "mario@sistema.pt"}
MASTER_COMO_ADMIN = {**MASTER, "effective_role": "admin"}

USERS = [
    {"id": "u-master", "role": "master", "email": "mario@sistema.pt", "name": "Mário Master", "is_active": True},
    {"id": "u-master2", "role": "master", "email": "marta@sistema.pt", "name": "Marta Master", "is_active": True},
    {"id": "u-master-off", "role": "master", "email": "off@sistema.pt", "name": "Inactivo", "is_active": False},
    {"id": "u-admin", "role": "admin", "email": "ana@power.pt", "name": "Ana Admin", "is_active": True},
    {"id": "u-admin-domus", "role": "admin", "email": "dom@domus.pt", "name": "Admin Domus", "is_active": True},
    {"id": "u-ceo", "role": "ceo", "email": "carlos@power.pt", "name": "Carlos CEO", "is_active": True},
    {"id": "u-dir", "role": "diretor", "email": "dir@power.pt", "name": "Dir", "is_active": True},
]


def _pedido(company_id="cmp-power"):
    return MagicMock(headers={"X-Company-Id": company_id}, state=MagicMock(spec=[]))


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.admin_helpers as helpers
    import services.alerta_ao_master as alerta
    import services.client_uniqueness as cu
    import services.form_config_scope as fcs
    import services.reauth_password as reauth
    import services.repor_ao_modelo as repor
    import services.workflow_scope as ws

    bd = semear(fake_async_db)
    bd.workflow_statuses.docs.extend([dict(f) for f in MODELO])
    bd.workflow_statuses.docs.extend([
        {"id": f"p:{n}", "name": n, "label": n, "order": i, "is_active": True, "network_id": REDE_INCUMBENTE}
        for i, n in enumerate(["novo", "fase_custom", "concluidos"], 1)
    ])
    bd.form_config.docs.extend([
        {"type": "public_form", "fields": []},
        {"type": "public_form", "network_id": REDE_INCUMBENTE, "fields": []},
    ])
    bd.user_company_roles.docs.extend([
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "admin", "is_default": True},
        {"user_id": "u-ceo", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "ceo", "is_default": True},
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "master", "is_default": True},
    ])
    for u in USERS:
        bd.users.docs.append({**u, "password": hash_password(SENHA)})

    tarefas = []

    def captar(coro, *, name=None):
        tarefas.append(coro)
        return MagicMock()

    with tenant_db(bd, ws, helpers, reauth, repor, cu, fcs, alerta), \
            patch("services.auth.get_active_company_id_async", AsyncMock(return_value="cmp-power")), \
            patch.object(alerta, "spawn_background_task", captar):
        wp.invalidar_cache_de_fases()
        yield bd, repor, alerta, tarefas
    wp.invalidar_cache_de_fases()
    for coro in tarefas:  # as que o teste não correu: fecham-se, não ficam "never awaited"
        coro.close()


def _alertas(bd):
    return [n for n in bd.notifications.docs if n.get("type") == "destructive_action_alert"]


def _corpo(repor, senha=SENHA, **kw):
    return repor.ReporAoModeloIn(password=senha, **kw)


class TestSoOMasterRecebe:
    async def test_admin_repoe_o_workflow_e_so_os_master_activos_recebem(self, mundo):
        bd, repor, _, _ = mundo
        r = await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert r["reposto"] is True
        assert sorted(n["user_id"] for n in _alertas(bd)) == ["u-master", "u-master2"]

    async def test_ninguem_mais_recebe(self, mundo):
        """Nem o autor, nem o CEO da rede, nem o Admin de outra rede, nem um Master inactivo."""
        bd, repor, _, _ = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        destinatarios = {n["user_id"] for n in bd.notifications.docs}
        assert destinatarios.isdisjoint({"u-admin", "u-ceo", "u-admin-domus", "u-dir", "u-master-off"})

    async def test_o_ceo_tambem_dispara(self, mundo):
        bd, repor, _, _ = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), CEO, _pedido())
        assert len(_alertas(bd)) == 2
        assert all(n["actor_id"] == "u-ceo" and n["actor_role"] == "ceo" for n in _alertas(bd))

    async def test_o_aviso_diz_quem_e_em_que_rede_logo_no_titulo(self, mundo):
        bd, repor, _, _ = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        n = _alertas(bd)[0]
        assert "Ana Admin" in n["message"] and REDE_INCUMBENTE in n["message"]
        assert "WORKFLOW" in n["message"]
        assert n["network_id"] == REDE_INCUMBENTE and n["read"] is False
        assert "Power Real Estate" in n["details"] and "ana@power.pt" in n["details"]
        assert "Fases removidas: 3" in n["details"]

    async def test_a_password_nunca_aparece_no_aviso(self, mundo):
        bd, repor, _, tarefas = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert SENHA not in repr(bd.notifications.docs)

    async def test_o_formulario_tambem_alerta(self, mundo):
        bd, repor, _, _ = mundo
        r = await repor.run_repor_formulario_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert r["reposto"] is True
        assert len(_alertas(bd)) == 2
        assert "FORMULÁRIO" in _alertas(bd)[0]["message"]
        assert _alertas(bd)[0]["action"] == "formulario_reposto_ao_modelo"


class TestSoQuandoAcontece:
    async def test_password_errada_nao_alerta(self, mundo):
        bd, repor, _, _ = mundo
        with pytest.raises(HTTPException):
            await repor.run_repor_workflow_ao_modelo(_corpo(repor, "errada"), ADMIN, _pedido())
        assert _alertas(bd) == []

    async def test_pedido_sem_efeito_nao_alerta(self, mundo):
        """A rede já usa o modelo: não houve nada destruído, não há nada a avisar."""
        bd, repor, _, _ = mundo
        bd.workflow_statuses.docs[:] = [d for d in bd.workflow_statuses.docs if not d.get("network_id")]
        bd.form_config.docs[:] = [d for d in bd.form_config.docs if not d.get("network_id")]
        r1 = await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        r2 = await repor.run_repor_formulario_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert r1["reposto"] is False and r2["reposto"] is False
        assert _alertas(bd) == []

    async def test_recusa_por_processos_em_curso_nao_alerta(self, mundo):
        bd, repor, _, _ = mundo
        bd.processes.docs.append({"id": "x1", "status": "fase_custom", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"})
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert erro.value.status_code == 409
        assert _alertas(bd) == []

    async def test_rede_fora_do_ambito_nao_alerta(self, mundo):
        bd, repor, _, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor, network_id=REDE_DOMUS), ADMIN, _pedido())
        assert erro.value.status_code == 404
        assert _alertas(bd) == []

    async def test_formulario_que_ja_nao_estava_nao_alerta(self, mundo):
        """`delete_one` sem efeito (corrida): reposto=false, logo nada a avisar."""
        bd, repor, _, _ = mundo
        with patch.object(repor, "tem_formulario_proprio", AsyncMock(return_value=True)):
            bd.form_config.docs[:] = [d for d in bd.form_config.docs if not d.get("network_id")]
            r = await repor.run_repor_formulario_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert r["reposto"] is False
        assert _alertas(bd) == []


class TestOMasterNaoSeAvisaASiProprio:
    async def test_master_como_master_nao_dispara(self, mundo):
        bd, repor, _, _ = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor, network_id=REDE_INCUMBENTE), MASTER, _pedido())
        assert _alertas(bd) == []

    async def test_master_com_o_chapeu_de_admin_avisa_os_outros_master(self, mundo):
        bd, repor, _, _ = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), MASTER_COMO_ADMIN, _pedido())
        assert [n["user_id"] for n in _alertas(bd)] == ["u-master2"]


class TestNuncaDerrubaAOperacao:
    async def test_falha_a_gravar_a_notificacao_a_reposicao_conclui(self, mundo):
        bd, repor, _, _ = mundo
        with patch.object(bd.notifications, "insert_many", AsyncMock(side_effect=RuntimeError("bd em baixo"))):
            r = await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert r["reposto"] is True
        assert not [d for d in bd.workflow_statuses.docs if d.get("network_id") == REDE_INCUMBENTE]

    async def test_falha_a_procurar_os_master_a_reposicao_conclui(self, mundo):
        bd, repor, _, _ = mundo
        with patch.object(bd.users, "find", side_effect=RuntimeError("bd em baixo")):
            r = await repor.run_repor_formulario_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert r["reposto"] is True

    async def test_sem_nenhum_master_activo_diz_se_e_a_reposicao_conclui(self, mundo, caplog):
        bd, repor, _, _ = mundo
        for u in bd.users.docs:
            if u.get("role") == "master":
                u["is_active"] = False
        with caplog.at_level("WARNING"):
            r = await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert r["reposto"] is True and _alertas(bd) == []
        assert "não há nenhum Master activo" in caplog.text


class TestOEmail:
    async def test_email_urgente_so_para_os_master_e_nao_bloqueia(self, mundo):
        bd, repor, _, tarefas = mundo
        enviar = AsyncMock(return_value=True)
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        assert len(tarefas) == 1, "o email vai em segundo plano, não no pedido"
        with patch("services.notification_service.send_notification_with_preference_check", enviar):
            await tarefas[0]
        assert sorted(c.args[0] for c in enviar.await_args_list) == ["mario@sistema.pt", "marta@sistema.pt"]
        assert all(c.kwargs["is_urgent"] is True for c in enviar.await_args_list)
        assert "Ana Admin" in enviar.await_args_list[0].args[1] and REDE_INCUMBENTE in enviar.await_args_list[0].args[1]
        assert SENHA not in repr(enviar.await_args_list)

    async def test_um_email_que_falha_nao_impede_os_outros(self, mundo):
        bd, repor, _, tarefas = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), ADMIN, _pedido())
        enviar = AsyncMock(side_effect=[RuntimeError("smtp"), True])
        with patch("services.notification_service.send_notification_with_preference_check", enviar):
            await tarefas[0]
        assert enviar.await_count == 2

    async def test_sem_alerta_nao_ha_tarefa_de_email(self, mundo):
        _, repor, _, tarefas = mundo
        with pytest.raises(HTTPException):
            await repor.run_repor_workflow_ao_modelo(_corpo(repor, "errada"), ADMIN, _pedido())
        assert tarefas == []


RAIZ = Path(__file__).resolve().parents[2]


class TestLigacao:
    def test_o_registar_do_repor_chama_o_alerta(self):
        """Sem isto, apagar a chamada deixava todos os testes de comportamento… a falhar, mas por outro motivo."""
        arvore = ast.parse((RAIZ / "services/repor_ao_modelo.py").read_text(encoding="utf-8"))
        no = next(n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_registar")
        assert "alertar_masters" in {ast.unparse(n.func) for n in ast.walk(no) if isinstance(n, ast.Call)}

    def test_os_destinatarios_saem_do_papel_global_e_nao_de_uma_lista_a_mao(self):
        fonte = (RAIZ / "services/alerta_ao_master.py").read_text(encoding="utf-8")
        assert "PAPEIS_GLOBAIS" in fonte
        arvore = ast.parse(fonte)
        literais = {n.value for n in ast.walk(arvore) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert not ({"admin", "ceo", "diretor"} & literais)

    def test_o_tipo_de_alerta_esta_nos_dois_ecras_de_notificacoes(self):
        from services.alerta_ao_master import TIPO_DE_ALERTA

        for ficheiro in ("components/NotificationsDropdown.js", "pages/NotificationsPage.js"):
            assert TIPO_DE_ALERTA in (RAIZ.parent / "frontend/src" / ficheiro).read_text(encoding="utf-8"), ficheiro
