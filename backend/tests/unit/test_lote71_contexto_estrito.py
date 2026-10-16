"""Contexto estrito de empresa — as peças puras, o cabeçalho real e os inventários (Lote 7.1).

O comportamento contra dados está em `tests/integration/test_lote71_contexto_estrito_mongo.py` (MongoDB
real). Aqui ficam: o `get_current_user` real a ler o cabeçalho, o predicado do passe livre, e os
INVENTÁRIOS por AST — que falham por OMISSÃO para um guarda de posse novo que volte a dar passe livre
ao Master por cargo, ou para um chamador novo do âmbito COMPLETO.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SERVICOS = RAIZ / "services"


# ════════════════════════════════════════════════════════════════════
#  O PASSE LIVRE SÓ EXISTE NA VISTA «SISTEMA»
# ════════════════════════════════════════════════════════════════════
class TestFronteiraLevantada:
    def test_o_master_sem_empresa_escolhida_passa(self):
        from services.role_scope import fronteira_levantada

        master = {"role": "master", "effective_role": "master"}
        assert fronteira_levantada(master) is True
        assert fronteira_levantada(master, por_conta=True) is True

    def test_com_empresa_escolhida_deixa_de_passar_nas_duas_leituras(self):
        from services.role_scope import fronteira_levantada

        master = {"role": "master", "effective_role": "master", "vista_empresa_id": "cmp-domus"}
        assert fronteira_levantada(master) is False
        assert fronteira_levantada(master, por_conta=True) is False

    @pytest.mark.parametrize("vazio", ["", "   ", None])
    def test_uma_empresa_vazia_nao_conta_como_escolhida(self, vazio):
        from services.role_scope import fronteira_levantada

        assert fronteira_levantada({"role": "master", "effective_role": "master", "vista_empresa_id": vazio}) is True

    @pytest.mark.parametrize("papel", ["admin", "ceo", "diretor", "consultor", "indexacao"])
    def test_ninguem_que_nao_seja_master_passa(self, papel):
        from services.role_scope import fronteira_levantada

        assert fronteira_levantada({"role": papel, "effective_role": papel}) is False
        assert fronteira_levantada({"role": papel, "effective_role": papel}, por_conta=True) is False

    def test_o_chapeu_conta_so_na_leitura_por_perfil(self):
        """Master com o chapéu de Admin: por perfil não passa; por CONTA passa (abrir por id)."""
        from services.role_scope import fronteira_levantada

        master_como_admin = {"role": "master", "effective_role": "admin"}
        assert fronteira_levantada(master_como_admin) is False
        assert fronteira_levantada(master_como_admin, por_conta=True) is True


# ════════════════════════════════════════════════════════════════════
#  O CABEÇALHO REAL CHEGA AO UTILIZADOR (um nível abaixo do âmbito)
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOCabecalhoNaSessaoReal:
    @staticmethod
    def _pedido(**cabecalhos):
        class _Req:
            headers = dict(cabecalhos)

        return _Req()

    async def _sessao(self, fake_db, papel, **cabecalhos):
        from fastapi.security import HTTPAuthorizationCredentials

        from services import auth
        from tests.unit.test_ws_portal_isolation import token_de_staff

        await fake_db.users.insert_one({"id": f"u-{papel}", "name": papel, "is_active": True, "role": papel})
        credenciais = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_de_staff(f"u-{papel}"))
        with patch.object(auth, "db", fake_db):
            return await auth.get_current_user(self._pedido(**cabecalhos), credenciais)

    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor", "consultor", "indexacao"])
    async def test_todo_o_staff_recebe_a_empresa_do_cabecalho(self, fake_async_db, papel):
        user = await self._sessao(fake_async_db, papel, **{"X-Company-Id": "cmp-domus"})
        assert user["vista_empresa_id"] == "cmp-domus"

    @pytest.mark.parametrize("valor", ["", "default", "all", "   "])
    async def test_valores_que_nao_sao_uma_empresa_nao_criam_contexto(self, fake_async_db, valor):
        user = await self._sessao(fake_async_db, "ceo", **{"X-Company-Id": valor})
        assert "vista_empresa_id" not in user

    async def test_sem_cabecalho_nao_ha_contexto(self, fake_async_db):
        user = await self._sessao(fake_async_db, "ceo")
        assert "vista_empresa_id" not in user


# ════════════════════════════════════════════════════════════════════
#  INVENTÁRIOS POR AST
# ════════════════════════════════════════════════════════════════════
def _nomes_importados_e_chamados(caminho: Path) -> tuple[set[str], set[str]]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    importados: set[str] = set()
    chamados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            importados.update(a.name for a in no.names)
        elif isinstance(no, ast.Call):
            f = no.func
            chamados.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
    return importados, chamados


#: Os módulos que fazem de GUARDA DE POSSE por id/caminho/ficheiro: nenhum pode dar passe livre ao
#: Master por cargo (`utilizador_e_global` / `conta_e_master`) — só `fronteira_levantada`, que olha
#: para a empresa escolhida. Acrescentar aqui um guarda novo.
GUARDAS_DE_POSSE = (
    "process_scope_guard.py",
    "by_id_scope.py",
    "document_path_scope.py",
    "document_visibility.py",
    "client_window.py",
    "process_closed_guard.py",
    "document_bulk_download.py",
)


class TestNenhumGuardaDaPasseLivreAoMasterPorCargo:
    @pytest.mark.parametrize("modulo", GUARDAS_DE_POSSE)
    def test_o_guarda_usa_fronteira_levantada(self, modulo):
        importados, chamados = _nomes_importados_e_chamados(SERVICOS / modulo)
        assert "fronteira_levantada" in chamados, f"{modulo}: deixou de usar fronteira_levantada"
        assert "utilizador_e_global" not in importados and "utilizador_e_global" not in chamados, (
            f"{modulo}: voltou a dar passe livre ao Master pelo cargo — com uma empresa escolhida "
            "isso abre os registos de outra empresa (Lote 7.1)"
        )
        assert "conta_e_master" not in importados and "conta_e_master" not in chamados, (
            f"{modulo}: idem, pela conta"
        )

    def test_a_contraprova_o_leitor_encontra_mesmo_as_chamadas(self):
        """Sem isto, um leitor que devolvesse conjuntos vazios fazia o inventário passar sempre."""
        importados, chamados = _nomes_importados_e_chamados(SERVICOS / "process_scope_guard.py")
        assert "fronteira_levantada" in importados
        assert {"find_one", "processo_no_ambito", "resolve_tenant_scope"} <= chamados


#: Quem pode pedir o âmbito COMPLETO (sem a empresa activa), e porquê. Tudo o resto pergunta
#: `resolve_tenant_scope`, que já vem estreitado: o contexto estrito é o omisso e o alargamento
#: é que tem de se justificar por escrito.
AMBITO_COMPLETO_ESCRITO = {
    "search_api_global.py": "a pesquisa global é a ÚNICA excepção ao contexto estrito (Lote 7.1)",
    "assignment_network_guard.py": (
        "combina a empresa escolhida com o alcance do processo (Master) e mede as redes de quem "
        "vai ser atribuído, que não são as do ator"
    ),
}


class TestOAmbitoCompletoTemChamadoresEscritos:
    def _chamadores(self) -> set[str]:
        achados = set()
        for caminho in sorted(SERVICOS.glob("*.py")) + sorted((RAIZ / "routes").glob("*.py")):
            if caminho.name == "tenant_network.py":
                continue
            _, chamados = _nomes_importados_e_chamados(caminho)
            if "resolve_tenant_scope_completo" in chamados:
                achados.add(caminho.name)
        return achados

    def test_so_os_chamadores_escritos(self):
        assert self._chamadores() == set(AMBITO_COMPLETO_ESCRITO)

    def test_a_contraprova_o_inventario_encontra_algum(self):
        assert self._chamadores(), "o leitor não encontrou nenhum chamador: o inventário ficou cego"


class TestOMasterComEmpresaEscolhidaNaoTemPapelSemFronteiraNosDados:
    """O calendário, as visitas, os imóveis e as finanças decidem por PAPEL: o contexto despromove."""

    def test_as_duas_portas_do_papel_de_dados_passam_pelo_helper(self):
        for modulo, nome in (("tenant_access_context.py", "carregar_contexto_de_acesso"), ("property_scope.py", "papel_efectivo")):
            fonte = (SERVICOS / modulo).read_text(encoding="utf-8")
            arvore = ast.parse(fonte)
            funcao = next(n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == nome)
            assert "papel_para_os_dados" in ast.unparse(funcao), f"{modulo}::{nome} perdeu papel_para_os_dados"


class TestAPesquisaGlobalEEstritaNaPesquisaAvancada:
    """A excepção é só da pesquisa global: as outras pesquisas ficam na empresa activa."""

    def test_a_pesquisa_avancada_e_as_sugestoes_nao_usam_o_ambito_completo(self):
        for modulo in ("search_api_processes.py", "search_api_suggestions.py"):
            _, chamados = _nomes_importados_e_chamados(SERVICOS / modulo)
            assert "resolve_tenant_scope_completo" not in chamados, modulo
