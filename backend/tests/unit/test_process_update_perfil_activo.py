"""
A permissão de escrita segue o PERFIL ACTIVO, não o papel do JWT.

A brecha: `run_update_process` resolvia `can_update_status` (e o bloqueio
de estados terminais) a partir de `user["role"]` — o papel base do token.
Quem trocasse para o perfil de Indexação no ContextSwitcher continuava a
poder mudar a fase de um processo pela API, apesar de o produto inteiro
— menus, botões, Kanban, regras de silêncio do histórico — já decidir
pelo chapéu que a pessoa tem posto.

É o mesmo padrão fechado no Kanban (Lote 5, ponto 12) e no
`_is_stealth_user` (Lote 4). Aqui era mais grave do que nos dois: não era
uma questão de VER a mais, era de ESCREVER.

A regra é fail-closed por construção: `get_effective_role` só honra o
header `X-Active-Role` quando a cache UCR o validou (ou quando coincide
com o papel do JWT). Um header inventado nunca alarga — recua para o
papel base.
"""
import pytest
from unittest.mock import patch

from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
from services.auth import resolve_concrete_role
from services.process_update import (
    run_update_process,
    build_role_update_permissions,
)
from models.process import ProcessUpdate


# ====================================================================
# resolve_concrete_role — o ponto único
# ====================================================================

class TestResolveConcreteRole:
    def test_o_perfil_activo_ganha_ao_papel_do_jwt(self):
        assert resolve_concrete_role(
            "indexacao", {"role": "consultor"},
        ) == "indexacao"

    def test_all_roles_recua_para_o_papel_do_jwt(self):
        # "Todos os perfis" é um conceito de LISTAGEM (união de
        # visibilidades). Não há união de permissões que faça sentido
        # num PUT, e cair no ramo de gestão seria um alargamento.
        assert resolve_concrete_role(
            "__all_roles__", {"role": "indexacao"},
        ) == "indexacao"

    def test_vazio_ou_nulo_recua_para_o_papel_do_jwt(self):
        for vazio in (None, "", "   "):
            assert resolve_concrete_role(vazio, {"role": "consultor"}) == "consultor"

    def test_apara_espacos(self):
        assert resolve_concrete_role("  diretor  ", {"role": "x"}) == "diretor"

    def test_sem_utilizador_nao_rebenta(self):
        assert resolve_concrete_role("__all_roles__", None) == ""
        assert resolve_concrete_role(None, {}) == ""

    def test_o_quadro_kanban_delega_na_mesma_regra(self):
        # Uma segunda cópia desta condição foi o que deixou
        # `document_portal_request` a ignorar `track_history=False`.
        from services.process_kanban_enrichment import resolver_papel_do_quadro

        assert resolver_papel_do_quadro(
            "__all_roles__", {"role": "indexacao"},
        ) == "indexacao"
        assert resolver_papel_do_quadro(
            "consultor", {"role": "indexacao"},
        ) == "consultor"


# ====================================================================
# run_update_process — o comportamento a sério
# ====================================================================

class PedidoFalso:
    """Request mínimo: corpo JSON + headers + `state`.

    DUAS formas de declarar o perfil activo, porque são dois caminhos
    diferentes em `get_effective_role` e só um deles pode produzir um
    papel DIFERENTE do JWT:

    - `ucr=` escreve a cache que o `get_current_user` deixa em
      `request.state` depois de validar o UCR na base de dados. É o
      caminho REAL de um utilizador multi-perfil, e o único em que a
      brecha era alcançável.
    - `papel_activo=` escreve só o header `X-Active-Role`. Sem cache
      UCR, `get_effective_role` só o honra quando COINCIDE com o papel
      do JWT — é fail-closed e serve para provar isso mesmo.
    """

    def __init__(self, corpo=None, papel_activo=None, ucr=None):
        self._corpo = corpo or {}
        self.headers = {"X-Active-Role": papel_activo} if papel_activo else {}
        self.state = type("Estado", (), {})()
        if ucr is not None:
            from services.auth import _EFFECTIVE_ROLE_CACHE

            setattr(self.state, _EFFECTIVE_ROLE_CACHE, ucr)


def _identidade(doc, *args, **kwargs):
    return doc


async def _nada(*args, **kwargs):
    return None


@pytest.fixture
def processo_na_base(fake_async_db):
    fake_async_db.processes.docs.append({
        "id": "proc-1",
        "status": "fase_bancaria",
        "client_id": "cli-1",
        "client_email": "",
    })
    return fake_async_db


async def _actualizar(fake_db, *, papel_jwt, papel_activo=None, ucr=None,
                      novo_estado, estado_actual=None):
    """Corre o PUT com as fronteiras pesadas falseadas.

    O que NÃO é falseado é a decisão em teste: `build_role_update_permissions`
    e `assert_process_editable_for_role` correm a sério.
    """
    import services.process_update as mod

    if estado_actual:
        fake_db.processes.docs[0]["status"] = estado_actual

    pedido = PedidoFalso(
        {"status": novo_estado}, papel_activo=papel_activo, ucr=ucr,
    )
    user = {"id": "u1", "role": papel_jwt, "name": "Teste"}

    with patch.object(mod, "db", fake_db), \
         patch.object(mod, "load_valid_workflow_status_names", return_value=[]), \
         patch.object(mod, "encrypt_process_update_payload", side_effect=lambda d, _p: d), \
         patch.object(mod, "run_process_update_side_effects", _nada), \
         patch.object(mod, "decrypt_and_populate_updated_process", side_effect=_identidade), \
         patch.object(mod, "build_process_response_or_500", side_effect=lambda d, _p: d), \
         patch("services.history.log_history", _nada), \
         patch("services.history.log_data_changes", _nada), \
         patch("services.audit_trail_service.log_audit_event", _nada), \
         patch("services.notification_service."
               "send_notification_with_preference_check", _nada):
        return await run_update_process(
            "proc-1",
            ProcessUpdate(status=novo_estado),
            pedido,
            user,
            decrypt_fn=_identidade,
            populate_fn=_identidade,
            extract_client_updates_fn=lambda _b: {},
            inject_cdc_fn=lambda _d, _u: None,
            broadcast_fn=_nada,
            ensure_finance_snapshot_fn=_nada,
            log_history_fn=_nada,
            log_audit_event_fn=_nada,
            cliente_role="cliente",
        )


class TestOPerfilActivoMandaNaEscrita:

    @pytest.mark.asyncio
    async def test_consultor_com_chapeu_de_indexacao_NAO_muda_a_fase(
        self, processo_na_base,
    ):
        # A brecha, exactamente. Indexação não está em `can_update_status`.
        await _actualizar(
            processo_na_base,
            papel_jwt="consultor", ucr="indexacao",
            novo_estado="cpcv",
        )
        assert processo_na_base.processes.docs[0]["status"] == "fase_bancaria"

    @pytest.mark.asyncio
    async def test_consultor_sem_troca_de_chapeu_muda_a_fase(
        self, processo_na_base,
    ):
        # Contraprova: sem ela, um `can_update_status` sempre falso
        # passaria no teste de cima e partia o produto todo.
        await _actualizar(
            processo_na_base,
            papel_jwt="consultor", papel_activo=None,
            novo_estado="cpcv",
        )
        assert processo_na_base.processes.docs[0]["status"] == "cpcv"

    @pytest.mark.asyncio
    async def test_o_perfil_Todos_recua_para_o_papel_base(
        self, processo_na_base,
    ):
        # `X-Active-Role: all` num indexador não pode virar passe livre.
        await _actualizar(
            processo_na_base,
            papel_jwt="indexacao", ucr="__all_roles__",
            novo_estado="cpcv",
        )
        assert processo_na_base.processes.docs[0]["status"] == "fase_bancaria"

    @pytest.mark.asyncio
    async def test_indexador_com_chapeu_de_consultor_VALIDADO_muda_a_fase(
        self, processo_na_base,
    ):
        # O sentido inverso, e é legítimo: quem é indexador numa empresa
        # e consultor noutra tem mesmo o chapéu de consultor quando o
        # UCR o confirma. Respeitar o perfil activo a 100% implica
        # também não lhe TIRAR o que ele tem de direito.
        await _actualizar(
            processo_na_base,
            papel_jwt="indexacao", ucr="consultor",
            novo_estado="cpcv",
        )
        assert processo_na_base.processes.docs[0]["status"] == "cpcv"

    @pytest.mark.asyncio
    async def test_um_header_nao_validado_nunca_alarga(
        self, processo_na_base,
    ):
        # `get_effective_role` é fail-closed: sem cache UCR, o header só
        # vale se COINCIDIR com o papel do JWT. Um indexador a declarar
        # "sou admin" continua indexador.
        await _actualizar(
            processo_na_base,
            papel_jwt="indexacao", papel_activo="admin",
            novo_estado="cpcv",
        )
        assert processo_na_base.processes.docs[0]["status"] == "fase_bancaria"

    @pytest.mark.asyncio
    async def test_o_bloqueio_de_estado_terminal_tambem_segue_o_chapeu(
        self, processo_na_base,
    ):
        # `assert_process_editable_for_role` isenta admin/CEO. Um admin
        # que trocou para consultor deixa de ter essa isenção.
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await _actualizar(
                processo_na_base,
                papel_jwt="admin", ucr="consultor",
                novo_estado="cpcv", estado_actual="concluido",
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_o_admin_sem_troca_de_chapeu_mantem_a_isencao(
        self, processo_na_base,
    ):
        # Contraprova do teste anterior.
        await _actualizar(
            processo_na_base,
            papel_jwt="admin", papel_activo=None,
            novo_estado="cpcv", estado_actual="concluido",
        )
        assert processo_na_base.processes.docs[0]["status"] == "cpcv"


# ====================================================================
# Guarda sobre o código-fonte — e a contraprova
# ====================================================================

class TestNaoVoltaAOPapelDoJWT:

    def test_a_permissao_nao_se_deriva_de_user_role(self):
        # `ast.unparse` NORMALIZA as aspas: procurar `user["role"]` com
        # aspas duplas nunca encontraria `user['role']`, e esta guarda
        # passava com a brecha aberta. Comparar sem aspas nenhumas.
        fonte = codigo_da_funcao_sem_comentarios(run_update_process)
        sem_aspas = fonte.replace('"', "").replace("'", "")
        assert "user[role]" not in sem_aspas, (
            "a permissão voltou a ler o papel do JWT em vez do perfil activo"
        )

    def test_a_permissao_deriva_do_perfil_activo(self):
        fonte = codigo_da_funcao_sem_comentarios(run_update_process)
        assert "get_effective_role" in fonte
        assert "resolve_concrete_role" in fonte

    def test_contraprova_os_papeis_nao_dao_todos_o_mesmo(self):
        # Sem isto, uma `build_role_update_permissions` que devolvesse
        # sempre True satisfazia as guardas de cima e os testes de
        # comportamento seriam os únicos a ver.
        assert build_role_update_permissions("consultor")["can_update_status"]
        assert not build_role_update_permissions("indexacao")["can_update_status"]
        assert not build_role_update_permissions("parceiro")["can_update_status"]


class TestAContaDeClienteNuncaAbreOCaminhoDoStaff:
    """
    O perfil activo passou a poder diferir do papel do JWT. O ramo que
    aplica alterações de NEGÓCIO tem de continuar fechado a uma conta de
    cliente do Portal, mesmo que um dia uma cache de perfil fique
    errada. A identidade de um cliente é a conta dele, não um chapéu.
    """

    @pytest.mark.asyncio
    async def test_cliente_com_perfil_de_consultor_na_cache_nao_muda_a_fase(
        self, processo_na_base,
    ):
        processo_na_base.processes.docs[0]["client_id"] = "u1"
        await _actualizar(
            processo_na_base,
            papel_jwt="cliente", ucr="consultor",
            novo_estado="cpcv",
        )
        assert processo_na_base.processes.docs[0]["status"] == "fase_bancaria"

    @pytest.mark.asyncio
    async def test_cliente_normal_tambem_nao_muda_a_fase(
        self, processo_na_base,
    ):
        processo_na_base.processes.docs[0]["client_id"] = "u1"
        await _actualizar(
            processo_na_base,
            papel_jwt="cliente", novo_estado="cpcv",
        )
        assert processo_na_base.processes.docs[0]["status"] == "fase_bancaria"

    @pytest.mark.asyncio
    async def test_cliente_continua_a_nao_poder_tocar_no_processo_de_outro(
        self, processo_na_base,
    ):
        # Contraprova de que a guarda de posse não foi enfraquecida.
        from fastapi import HTTPException

        processo_na_base.processes.docs[0]["client_id"] = "outro-cliente"
        with pytest.raises(HTTPException) as exc:
            await _actualizar(
                processo_na_base,
                papel_jwt="cliente", novo_estado="cpcv",
            )
        assert exc.value.status_code == 403
