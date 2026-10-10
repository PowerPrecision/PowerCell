"""Controlo de histórico: o admin liga/desliga o registo por pessoa e por perfil.

O PEDIDO (Bloco 1, ponto 4)
===========================
«Criar a possibilidade de o master/admin ativar ou desativar (na área de
gestão) se as acções ficam guardadas no histórico para um determinado user
ou perfil. Por default, fica tudo ativo.»

AS DECISÕES DE PRODUTO
======================
* **Os dois eixos, pessoa vence perfil** — a mesma regra dos overrides
  pessoais do `capability_gate`;
* **o perfil `indexacao` é sempre silencioso**: o interruptor nunca o
  pode ligar (restrição de segurança de dia zero do sistema);
* o `audit_trail_service` NÃO é silenciado por este interruptor
  (conformidade: IP, retenção) — é um registo de outra natureza.

O QUE JÁ EXISTIA
================
`history._is_stealth_user` já honrava `user["track_history"] is False`,
mas ninguém o gravava: era um campo sem interruptor. E o eixo por perfil
não existia. Esta bateria monta o fluxo REAL — `get_current_user` →
`log_history` — porque um teste que forje o utilizador à mão prova só o
`_is_stealth_user`, que nunca foi o que faltava.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from config import JWT_ALGORITHM, JWT_SECRET

ADMIN = {"id": "u-admin", "name": "Admin", "email": "admin@x.pt", "role": "admin"}


def _token(user_id: str) -> HTTPAuthorizationCredentials:
    token = jwt.encode(
        {"sub": user_id, "type": "access"}, JWT_SECRET, algorithm=JWT_ALGORITHM
    )
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class _Pedido:
    def __init__(self, papel=None, empresa=None):
        self.headers = {}
        if papel:
            self.headers["X-Active-Role"] = papel
        if empresa:
            self.headers["X-Company-Id"] = empresa


@pytest.fixture
def mundo(fake_async_db):
    """Utilizadores de cada perfil + a política em branco."""
    import services.admin_helpers as admin_helpers
    import services.auth as auth
    import services.history as history
    import services.history_tracking as ht

    for u in (
        {"id": "u-consultor", "name": "Cons", "email": "c@x.pt", "role": "consultor", "is_active": True},
        {"id": "u-diretor", "name": "Dir", "email": "d@x.pt", "role": "diretor", "is_active": True},
        {"id": "u-indexacao", "name": "Index", "email": "i@x.pt", "role": "indexacao", "is_active": True},
        # Base consultor, mas também diretor numa empresa: o PERFIL ACTIVO conta.
        {"id": "u-dois", "name": "Dois", "email": "dois@x.pt", "role": "consultor", "is_active": True},
        {"id": "u-admin", "name": "Admin", "email": "admin@x.pt", "role": "admin", "is_active": True},
    ):
        fake_async_db.users.docs.append(u)
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-dois", "company_id": "cmp-a", "company_name": "A", "role": "consultor", "is_default": True},
        {"user_id": "u-dois", "company_id": "cmp-b", "company_name": "B", "role": "diretor", "is_default": False},
    ])
    ht.invalidar_cache()
    with patch.object(auth, "db", fake_async_db), \
            patch.object(history, "db", fake_async_db), \
            patch.object(ht, "db", fake_async_db), \
            patch.object(admin_helpers, "db", fake_async_db), \
            patch("database.db", fake_async_db):
        yield fake_async_db
    ht.invalidar_cache()


async def _autenticar(user_id: str, papel=None, empresa=None) -> dict:
    from services import auth

    return await auth.get_current_user(_Pedido(papel, empresa), _token(user_id))


async def _agir(user: dict) -> int:
    """O utilizador faz UMA acção que deixa histórico; quantas linhas ficaram?"""
    from database import db
    from services.history import log_history

    antes = len(db.history.docs)
    await log_history("proc-1", user, "Alterou estado", "status", "novo", "em_analise")
    return len(db.history.docs) - antes


async def _desligar_perfil(role: str, db):
    import services.history_tracking as ht

    await ht.run_set_role_history(role, False, ADMIN)
    ht.invalidar_cache()


# ════════════════════════════════════════════════════════════════════
#  O ATAQUE — hoje não há forma de desligar nada por perfil
# ════════════════════════════════════════════════════════════════════
class TestAExploracao:
    @pytest.mark.asyncio
    async def test_desligar_um_perfil_cala_quem_trabalha_com_esse_perfil(self, mundo):
        await _desligar_perfil("consultor", mundo)
        user = await _autenticar("u-consultor")
        assert await _agir(user) == 0

    @pytest.mark.asyncio
    async def test_desligar_uma_pessoa_cala_so_essa_pessoa(self, mundo):
        import services.history_tracking as ht

        await ht.run_set_user_history("u-consultor", False, ADMIN)
        assert await _agir(await _autenticar("u-consultor")) == 0
        assert await _agir(await _autenticar("u-diretor")) == 1


# ════════════════════════════════════════════════════════════════════
#  AS REGRAS
# ════════════════════════════════════════════════════════════════════
class TestPorOmissaoTudoAtivo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("quem", ["u-consultor", "u-diretor", "u-admin"])
    async def test_sem_politica_nem_override_regista(self, mundo, quem):
        assert await _agir(await _autenticar(quem)) == 1


class TestPessoaVenceOPerfil:
    @pytest.mark.asyncio
    async def test_pessoa_ligada_apesar_do_perfil_desligado(self, mundo):
        import services.history_tracking as ht

        await _desligar_perfil("consultor", mundo)
        await ht.run_set_user_history("u-consultor", True, ADMIN)
        assert await _agir(await _autenticar("u-consultor")) == 1

    @pytest.mark.asyncio
    async def test_pessoa_desligada_apesar_do_perfil_ligado(self, mundo):
        import services.history_tracking as ht

        await ht.run_set_user_history("u-diretor", False, ADMIN)
        assert await _agir(await _autenticar("u-diretor")) == 0

    @pytest.mark.asyncio
    async def test_remover_o_override_devolve_a_pessoa_ao_perfil(self, mundo):
        import services.history_tracking as ht

        await _desligar_perfil("consultor", mundo)
        await ht.run_set_user_history("u-consultor", True, ADMIN)
        await ht.run_set_user_history("u-consultor", None, ADMIN)
        assert await _agir(await _autenticar("u-consultor")) == 0
        user_doc = next(u for u in mundo.users.docs if u["id"] == "u-consultor")
        assert "track_history" not in user_doc, "None remove o campo, não o põe a null"


class TestOPerfilActivoConta:
    @pytest.mark.asyncio
    async def test_a_politica_segue_o_perfil_EFECTIVO_e_nao_o_de_base(self, mundo):
        """Base consultor, a trabalhar COMO diretor: manda o diretor."""
        await _desligar_perfil("diretor", mundo)

        como_diretor = await _autenticar("u-dois", papel="diretor", empresa="cmp-b")
        assert como_diretor["effective_role"] == "diretor"
        assert await _agir(como_diretor) == 0

        # Contraprova: o MESMO utilizador, como consultor, deixa rasto.
        como_consultor = await _autenticar("u-dois", papel="consultor", empresa="cmp-a")
        assert await _agir(como_consultor) == 1

    @pytest.mark.asyncio
    async def test_o_modo_todos_os_perfis_nao_cala_ninguem(self, mundo):
        """`__all_roles__` não é um perfil: sem saber qual, regista."""
        await _desligar_perfil("consultor", mundo)
        await _desligar_perfil("diretor", mundo)
        user = await _autenticar("u-admin", papel="__all_roles__")
        assert await _agir(user) == 1


class TestIndexacaoNuncaSeLiga:
    @pytest.mark.asyncio
    async def test_a_api_recusa_ligar_o_perfil_indexacao(self, mundo):
        import services.history_tracking as ht

        with pytest.raises(HTTPException) as exc:
            await ht.run_set_role_history("indexacao", True, ADMIN)
        assert exc.value.status_code == 400
        # A mensagem diz PORQUÊ — «perfil inválido» mandava procurar um erro de escrita.
        assert exc.value.detail == ht.MOTIVO_INDEXACAO
        assert not mundo.history_policy.docs

    @pytest.mark.asyncio
    async def test_nem_sequer_se_guarda_uma_politica_para_indexacao(self, mundo):
        """Desligar também é recusado: já é sempre silencioso, e guardar um
        valor que não manda em nada é uma mentira à espera de ser lida."""
        import services.history_tracking as ht

        with pytest.raises(HTTPException) as exc:
            await ht.run_set_role_history("indexacao", False, ADMIN)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_api_recusa_ligar_uma_pessoa_cuja_base_e_indexacao(self, mundo):
        import services.history_tracking as ht

        with pytest.raises(HTTPException) as exc:
            await ht.run_set_user_history("u-indexacao", True, ADMIN)
        assert exc.value.status_code == 400
        doc = next(u for u in mundo.users.docs if u["id"] == "u-indexacao")
        assert "track_history" not in doc

    @pytest.mark.asyncio
    async def test_mesmo_com_o_estado_forjado_na_base_de_dados_continua_silencioso(self, mundo):
        """Defesa em profundidade: alguém escreve à mão `track_history: True`
        e uma política `indexacao: True`. O interruptor não pode ganhar."""
        mundo.history_policy.docs.append({"_id": "roles", "roles": {"indexacao": True}})
        next(u for u in mundo.users.docs if u["id"] == "u-indexacao")["track_history"] = True

        user = await _autenticar("u-indexacao")
        assert await _agir(user) == 0

    @pytest.mark.asyncio
    async def test_quem_trabalha_COMO_indexacao_fica_silencioso_mesmo_com_override_ligado(self, mundo):
        import services.history_tracking as ht

        mundo.user_company_roles.docs.append(
            {"user_id": "u-dois", "company_id": "cmp-c", "company_name": "C", "role": "indexacao", "is_default": False}
        )
        await ht.run_set_user_history("u-dois", True, ADMIN)

        como_index = await _autenticar("u-dois", papel="indexacao", empresa="cmp-c")
        assert await _agir(como_index) == 0


class TestFalhaGraciosa:
    @pytest.mark.asyncio
    async def test_se_a_politica_nao_le_regista_na_mesma(self, mundo, caplog):
        """Sem poder ler o interruptor fica o default (tudo ativo): registar de
        mais é recuperável, perder histórico não é."""
        import services.history_tracking as ht

        async def rebenta(*_a, **_k):
            raise RuntimeError("mongo em baixo")

        with patch.object(ht, "_ler_politica_da_base", rebenta), \
                caplog.at_level("WARNING"):
            ht.invalidar_cache()
            user = await _autenticar("u-consultor")
            assert await _agir(user) == 1
        assert any("histórico" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_a_leitura_da_politica_e_guardada_em_cache(self, mundo):
        import services.history_tracking as ht

        chamadas = []
        original = ht._ler_politica_da_base

        async def conta():
            chamadas.append(1)
            return await original()

        with patch.object(ht, "_ler_politica_da_base", conta):
            ht.invalidar_cache()
            await _autenticar("u-consultor")
            await _autenticar("u-consultor")
            await _autenticar("u-diretor")
        assert len(chamadas) == 1

    @pytest.mark.asyncio
    async def test_escrever_a_politica_invalida_a_cache_local(self, mundo):
        import services.history_tracking as ht

        await _autenticar("u-consultor")           # aquece a cache sem política
        await ht.run_set_role_history("consultor", False, ADMIN)
        assert await _agir(await _autenticar("u-consultor")) == 0   # sem esperar o TTL


# ════════════════════════════════════════════════════════════════════
#  A API
# ════════════════════════════════════════════════════════════════════
class TestAApi:
    @pytest.mark.asyncio
    async def test_um_perfil_inexistente_e_recusado(self, mundo):
        import services.history_tracking as ht

        for role in ("rei", "cliente", ""):
            with pytest.raises(HTTPException) as exc:
                await ht.run_set_role_history(role, False, ADMIN)
            assert exc.value.status_code == 400, role

    @pytest.mark.asyncio
    async def test_um_utilizador_inexistente_da_404(self, mundo):
        import services.history_tracking as ht

        with pytest.raises(HTTPException) as exc:
            await ht.run_set_user_history("u-fantasma", False, ADMIN)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_listagem_de_perfis_diz_o_estado_e_o_bloqueio(self, mundo):
        import services.history_tracking as ht

        await _desligar_perfil("consultor", mundo)
        res = await ht.run_get_history_tracking(ADMIN)
        por_papel = {p["role"]: p for p in res["perfis"]}

        assert por_papel["consultor"]["enabled"] is False
        assert por_papel["diretor"]["enabled"] is True
        assert por_papel["indexacao"]["enabled"] is False
        assert por_papel["indexacao"]["locked"] is True
        assert not por_papel["consultor"]["locked"]
        assert "cliente" not in por_papel

    @pytest.mark.asyncio
    async def test_ligar_um_perfil_remove_a_entrada_em_vez_de_a_guardar_a_true(self, mundo):
        """O default é «ativo». Guardar `True` seria uma segunda forma de dizer
        a mesma coisa — e a que alguém um dia lê como «foi alterado»."""
        import services.history_tracking as ht

        await ht.run_set_role_history("consultor", False, ADMIN)
        await ht.run_set_role_history("consultor", True, ADMIN)
        doc = next(d for d in mundo.history_policy.docs if d["_id"] == "roles")
        assert "consultor" not in doc["roles"]

    @pytest.mark.asyncio
    async def test_a_listagem_de_utilizadores_traz_override_e_estado_efectivo(self, mundo):
        import services.history_tracking as ht

        await _desligar_perfil("consultor", mundo)
        await ht.run_set_user_history("u-diretor", False, ADMIN)
        res = await ht.run_list_users_history(search=None, page=1, size=50)
        por_id = {u["id"]: u for u in res["utilizadores"]}

        assert por_id["u-consultor"]["track_history"] is None
        assert por_id["u-consultor"]["efectivo"] is False       # herda o perfil
        assert por_id["u-diretor"]["track_history"] is False
        assert por_id["u-diretor"]["efectivo"] is False         # override pessoal
        assert por_id["u-admin"]["efectivo"] is True
        assert por_id["u-indexacao"]["bloqueado"] is True
        assert por_id["u-indexacao"]["efectivo"] is False
        assert res["total"] == 5

    @pytest.mark.asyncio
    async def test_a_listagem_de_utilizadores_pesquisa_e_pagina(self, mundo):
        import services.history_tracking as ht

        res = await ht.run_list_users_history(search="dir", page=1, size=50)
        assert [u["id"] for u in res["utilizadores"]] == ["u-diretor"]

        res = await ht.run_list_users_history(search=None, page=2, size=2)
        assert len(res["utilizadores"]) == 2
        assert res["total"] == 5


class TestAuditoriaDaDecisao:
    """Quem desligou o histórico de quem tem de ficar escrito."""

    @pytest.mark.asyncio
    async def test_desligar_uma_pessoa_deixa_rasto_na_auditoria(self, mundo):
        import services.history_tracking as ht

        await ht.run_set_user_history("u-consultor", False, ADMIN)
        linhas = [l for l in mundo.audit_logs.docs if l["action"] == "history_tracking_user_changed"]
        assert len(linhas) == 1
        assert linhas[0]["entity_id"] == "u-consultor"
        assert linhas[0]["performed_by_id"] == "u-admin"
        assert linhas[0]["details"]["novo"] is False

    @pytest.mark.asyncio
    async def test_desligar_um_perfil_deixa_rasto_na_auditoria(self, mundo):
        import services.history_tracking as ht

        await ht.run_set_role_history("consultor", False, ADMIN)
        linhas = [l for l in mundo.audit_logs.docs if l["action"] == "history_tracking_role_changed"]
        assert len(linhas) == 1 and linhas[0]["entity_id"] == "consultor"

    @pytest.mark.asyncio
    async def test_quem_e_indexacao_nao_deixa_rasto_nem_na_auditoria(self, mundo):
        """Restrição de segurança: as acções do perfil `indexacao` não geram
        registos de actividade/auditoria. Aqui o actor é indexação de base a
        trabalhar como admin: a decisão aplica-se, o rasto não se escreve."""
        import services.history_tracking as ht

        actor = {"id": "u-indexacao", "name": "Index", "email": "i@x.pt",
                 "role": "indexacao", "effective_role": "admin"}
        await ht.run_set_user_history("u-consultor", False, actor)

        assert next(u for u in mundo.users.docs if u["id"] == "u-consultor")["track_history"] is False
        assert not mundo.audit_logs.docs


class TestOsEscritoresDoAdminTambemObedecem:
    """`admin_observability` escrevia em `db.history` à mão: o interruptor (e a
    regra de ouro da Indexação) não os alcançava. Agora passam pelo ponto
    único. Cada teste tem a sua contraprova — sem ela, um escritor que nunca
    escrevesse passava."""

    @pytest.fixture
    def processo(self, mundo):
        import services.admin_observability as obs
        import services.history as history

        mundo.processes.docs.append({"id": "p1", "client_name": "Ana", "client_email": "a@x.pt"})
        with patch.object(obs, "db", mundo), patch.object(history, "db", mundo):
            yield obs

    @pytest.mark.asyncio
    async def test_editar_um_registo(self, processo, mundo):
        await processo.run_update_client_registration("p1", {"client_name": "Ana M."}, dict(ADMIN))
        assert len(mundo.history.docs) == 1, "contraprova: sem interruptor, regista"

        mundo.history.docs.clear()
        await processo.run_update_client_registration("p1", {"client_name": "Ana N."}, {**ADMIN, "track_history": False})
        assert mundo.history.docs == []

    @pytest.mark.asyncio
    async def test_eliminar_um_registo(self, processo, mundo):
        await processo.run_delete_client_registration("p1", {**ADMIN, "track_history": False})
        assert mundo.history.docs == []
        # E a eliminação em si NÃO foi afectada pelo silêncio.
        assert next(p for p in mundo.processes.docs if p["id"] == "p1")["is_deleted"] is True

    @pytest.mark.asyncio
    async def test_eliminar_um_registo_regista_por_omissao(self, processo, mundo):
        await processo.run_delete_client_registration("p1", dict(ADMIN))
        assert len(mundo.history.docs) == 1


# ════════════════════════════════════════════════════════════════════
#  A LIGAÇÃO
# ════════════════════════════════════════════════════════════════════
BACKEND = Path(__file__).resolve().parents[2]


class TestALigacao:
    def test_o_get_current_user_aplica_a_politica(self):
        fonte = (BACKEND / "services" / "auth.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        no = next(
            n for n in arvore.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_current_user"
        )
        assert "aplicar_politica_de_historico" in ast.unparse(no)

    def test_todas_as_rotas_sao_so_de_admin(self):
        """Só o Master (global). A política de histórico é por PERFIL de todo o
        sistema: nem o Admin nem o CEO locais a desligam."""
        arvore = ast.parse((BACKEND / "routes" / "history_tracking.py").read_text(encoding="utf-8"))
        handlers = [
            n for n in arvore.body
            if isinstance(n, ast.AsyncFunctionDef) and n.decorator_list
        ]
        assert len(handlers) >= 4
        for h in handlers:
            fonte = ast.unparse(h)
            assert "UserRole.MASTER" in fonte, h.name
            assert "UserRole.ADMIN" not in fonte, h.name
            assert "UserRole.CEO" not in fonte, h.name

    def test_o_router_esta_registado_no_servidor(self):
        fonte = (BACKEND / "server.py").read_text(encoding="utf-8")
        assert "history_tracking" in fonte

    def test_o_audit_trail_service_continua_fora_do_interruptor(self):
        """Conformidade (IP, retenção): este interruptor não lhe toca.

        Por AST e sobre os IMPORTS: a docstring do módulo explica a regra e
        nomeia o serviço, e uma guarda que lê o texto proíbe a explicação do
        que previne.
        """
        arvore = ast.parse((BACKEND / "services" / "history_tracking.py").read_text(encoding="utf-8"))
        importados = {
            n.module if isinstance(n, ast.ImportFrom) else a.name
            for n in ast.walk(arvore)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in getattr(n, "names", [])
        }
        assert "services.audit_trail_service" not in importados
        assert "services.history" in importados, "a contraprova: o leitor lê mesmo os imports"
