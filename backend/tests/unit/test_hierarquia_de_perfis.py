"""
Hierarquia de perfis: UM global (Master), o resto local (adenda de RBAC, Out 2026).

O PEDIDO
  * MASTER — único perfil global (todas as empresas, configuração global,
    infraestrutura).
  * ADMIN — estritamente local: só a sua empresa/rede (igual ao CEO).
  * CEO — local.
  * Os 9 perfis reconhecidos pelo motor e pelas tipagens: Master, Admin,
    CEO, Diretor, Administrativo, Consultor, Intermediario, Parceiro e Index.

O QUE ESTES TESTES FAZEM QUE UM TESTE DE UNIDADE NÃO FAZ
  A maior parte do risco desta mudança não está numa função: está nas
  ~340 listas de papéis espalhadas pelo código (`[ADMIN, CEO]`) e nas ~110
  rotas que eram «só Admin». Um único sítio esquecido deixa o Master de
  fora (falha visível) ou o Admin dentro (fuga). Por isso há inventários
  por AST que falham por OMISSÃO — o mesmo padrão dos inventários de rotas
  desta casa — e cada um tem a sua contraprova de que lê mesmo.
"""
from __future__ import annotations

import ast
from unittest.mock import patch
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from models.auth import PERFIS_DO_SISTEMA, UserRole, UserRoleEnum, normalizar_papel
from services.auth import effective_role_is_allowed
from services.role_scope import (
    PAPEIS_GLOBAIS,
    e_papel_global,
    pode_conceder_papel,
    utilizador_e_global,
)
from services.tenant_network import (
    TenantScope,
    build_network_scope_condition,
    build_process_scope_condition,
    documento_no_ambito,
    processo_no_ambito,
    resolve_tenant_scope,
)
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    casa,
    por_id,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]
FRONTEND = BACKEND.parent / "frontend" / "src"

MASTER = {"id": "u-master", "name": "Master", "email": "m@x.pt", "role": "master", "effective_role": "master"}
ADMIN_POWER = {"id": "u-mara", "name": "Mara", "email": "mara@power.pt", "role": "admin", "effective_role": "admin"}
CEO_DOMUS = {"id": "u-rui", "name": "Rui", "email": "rui@domus.pt", "role": "ceo", "effective_role": "ceo"}

UCRS_EXTRA = [
    {"user_id": "u-mara", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "admin", "is_default": True},
    {"user_id": "u-rui", "company_id": "cmp-domus", "company_name": "Domus",
     "role": "ceo", "is_default": True},
]


def _semear(fake_db):
    semear(fake_db)
    fake_db.user_company_roles.docs.extend(dict(u) for u in UCRS_EXTRA)
    return fake_db


# ════════════════════════════════════════════════════════════════════
#  OS 9 PERFIS
# ════════════════════════════════════════════════════════════════════
class TestOsNovePerfis:
    ESPERADOS = {
        "master", "admin", "ceo", "diretor", "administrativo",
        "consultor", "intermediario", "parceiro", "indexacao",
    }

    def test_o_enum_reconhece_exactamente_os_9_perfis_mais_o_pseudo_papel_cliente(self):
        valores = {e.value for e in UserRoleEnum}
        assert valores - {"cliente"} == self.ESPERADOS

    def test_a_lista_canonica_tem_os_9(self):
        assert set(PERFIS_DO_SISTEMA) == self.ESPERADOS
        assert len(PERFIS_DO_SISTEMA) == 9

    def test_ALL_ROLES_e_UserRole_dizem_o_mesmo(self):
        assert set(UserRole.ALL_ROLES) - {"cliente"} == self.ESPERADOS
        assert UserRole.MASTER == "master"

    def test_master_e_staff_e_gere_utilizadores(self):
        assert UserRole.is_staff("master")
        assert UserRole.can_manage_users("master")
        assert UserRole.can_access_admin_panel("master")

    @pytest.mark.parametrize("entrada,esperado", [
        ("Index", "indexacao"), ("index", "indexacao"), (" INDEX ", "indexacao"),
        ("Master", "master"), ("Admin", "admin"), ("Intermediario", "intermediario"),
    ])
    def test_Index_e_o_nome_no_ecra_do_perfil_indexacao(self, entrada, esperado):
        """O valor guardado continua `indexacao`: renomeá-lo partia os dados
        e os UCRs existentes. «Index» é apenas como o perfil se chama."""
        assert normalizar_papel(entrada) == esperado
        assert UserRoleEnum.from_string(entrada).value == esperado

    def test_o_frontend_lista_os_mesmos_9_perfis(self):
        """Duas listas em linguagens diferentes que ninguém cruza divergem."""
        fonte = (FRONTEND / "utils" / "roleUtils.js").read_text(encoding="utf-8")
        bloco = re.search(r"export const VALID_ROLES = \[(.*?)\];", fonte, re.S).group(1)
        assert set(re.findall(r'"(\w+)"', bloco)) == self.ESPERADOS

    def test_o_ucr_aceita_master(self):
        from models.user_company_role import CompanyRoleEnum

        assert {e.value for e in CompanyRoleEnum} == self.ESPERADOS


# ════════════════════════════════════════════════════════════════════
#  GUARDAS DE PAPEL
# ════════════════════════════════════════════════════════════════════
class TestGuardasDePapel:
    def test_o_master_passa_tudo(self):
        for gate in ([UserRole.CONSULTOR], [UserRole.ADMIN], [UserRole.MASTER], [UserRole.PARCEIRO]):
            assert effective_role_is_allowed("master", gate) is True

    def test_o_admin_passa_as_guardas_normais(self):
        assert effective_role_is_allowed("admin", [UserRole.ADMIN, UserRole.CEO]) is True
        assert effective_role_is_allowed("admin", [UserRole.CONSULTOR]) is True

    def test_o_admin_NAO_passa_uma_guarda_so_master(self):
        """É isto que faz `require_roles([UserRole.MASTER])` ser uma parede e
        não um adorno: o bypass antigo do Admin deixava-o passar tudo."""
        assert effective_role_is_allowed("admin", [UserRole.MASTER]) is False

    def test_o_ceo_nunca_passa_uma_guarda_so_master(self):
        assert effective_role_is_allowed("ceo", [UserRole.MASTER]) is False

    @pytest.mark.parametrize("papel", ["diretor", "administrativo", "consultor",
                                       "intermediario", "indexacao", "parceiro"])
    def test_ninguem_mais_passa_uma_guarda_so_master(self, papel):
        assert effective_role_is_allowed(papel, [UserRole.MASTER]) is False

    def test_e_papel_global_so_responde_sim_ao_master(self):
        assert e_papel_global("master") and e_papel_global(" Master ")
        for papel in ("admin", "ceo", "diretor", "indexacao", "", None):
            assert not e_papel_global(papel)
        assert PAPEIS_GLOBAIS == frozenset({"master"})

    def test_o_papel_global_decide_pelo_perfil_ACTIVO_nao_pelo_da_conta(self):
        """Um Master que entra como Consultor vê o que um Consultor vê."""
        assert utilizador_e_global({"role": "master", "effective_role": "master"})
        assert not utilizador_e_global({"role": "master", "effective_role": "consultor"})
        # «Todos os perfis» não decide permissões: recua para o perfil base.
        assert utilizador_e_global({"role": "master", "effective_role": "__all_roles__"})
        assert not utilizador_e_global({"role": "admin", "effective_role": "__all_roles__"})

    def test_so_o_master_concede_master(self):
        assert pode_conceder_papel(MASTER, "master")
        assert not pode_conceder_papel(ADMIN_POWER, "master")
        assert not pode_conceder_papel(CEO_DOMUS, "Master")
        assert pode_conceder_papel(ADMIN_POWER, "consultor")


# ════════════════════════════════════════════════════════════════════
#  ÂMBITO DE DADOS
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAmbitoDeDados:
    async def test_o_master_nao_tem_fronteira(self, fake_async_db):
        _semear(fake_async_db)
        with tenant_db(fake_async_db):
            scope = await resolve_tenant_scope(MASTER)
        assert scope.sem_fronteira is True
        assert build_network_scope_condition(scope) == {}
        # E vê tudo, incluindo o que nenhuma rede reclama.
        docs = fake_async_db.processes.docs
        cond = build_process_scope_condition(scope)
        assert por_id(d for d in docs if casa(d, cond)) == por_id(docs)

    async def test_o_admin_so_ve_a_sua_rede(self, fake_async_db, rede_de_omissao_incumbente):
        _semear(fake_async_db)
        with tenant_db(fake_async_db):
            scope = await resolve_tenant_scope(ADMIN_POWER)
        assert scope.sem_fronteira is False
        cond = build_network_scope_condition(scope)
        visiveis = por_id(d for d in fake_async_db.processes.docs if casa(d, cond))
        assert "p-power" in visiveis
        assert "p-domus" not in visiveis and "p-domus-sem-rede" not in visiveis

    async def test_o_ceo_da_domus_nao_ve_a_power(self, fake_async_db, rede_de_omissao_incumbente):
        _semear(fake_async_db)
        with tenant_db(fake_async_db):
            scope = await resolve_tenant_scope(CEO_DOMUS)
        cond = build_network_scope_condition(scope)
        visiveis = por_id(d for d in fake_async_db.processes.docs if casa(d, cond))
        assert "p-domus" in visiveis
        assert "p-power" not in visiveis and "p-legado" not in visiveis

    async def test_um_master_que_veste_o_chapeu_de_admin_fica_limitado(
        self, fake_async_db, rede_de_omissao_incumbente,
    ):
        _semear(fake_async_db)
        fake_async_db.user_company_roles.docs.append(
            {"user_id": "u-master", "company_id": "cmp-domus", "company_name": "Domus", "role": "admin"}
        )
        com_chapeu = {**MASTER, "effective_role": "admin"}
        with tenant_db(fake_async_db):
            scope = await resolve_tenant_scope(com_chapeu)
        assert scope.sem_fronteira is False
        assert REDE_DOMUS in scope.network_ids and REDE_INCUMBENTE not in scope.network_ids

    def test_sem_fronteira_so_se_liga_no_resolve(self):
        """`TenantScope()` por omissão é FECHADO — o `sem_fronteira` não é um
        valor por omissão que alguém ligue por esquecimento."""
        assert TenantScope().sem_fronteira is False
        assert build_network_scope_condition(TenantScope()) != {}
        assert documento_no_ambito({"network_id": "x"}, TenantScope()) is False
        assert documento_no_ambito({"network_id": "x"}, TenantScope(sem_fronteira=True)) is True
        assert processo_no_ambito({"network_id": "x"}, TenantScope(sem_fronteira=True)) is True

    def test_a_cache_das_estatisticas_distingue_o_master_de_um_utilizador_sem_redes(self):
        """Ambos têm listas vazias. Se partilhassem a chave, o utilizador sem
        redes serviria os números do sistema inteiro."""
        from services.stats_scope import sufixo_de_cache

        assert sufixo_de_cache(TenantScope(sem_fronteira=True)) != sufixo_de_cache(TenantScope())

    @pytest.mark.asyncio
    async def test_as_chaves_do_relatorio_executivo_distinguem_master_de_vazio(self, fake_async_db):
        from services import executive_report as er

        import services.admin_users_scope as scope_mod

        with tenant_db(fake_async_db, scope_mod):
            a = await er.resolver_ambito_do_scope(TenantScope(sem_fronteira=True))
            b = await er.resolver_ambito_do_scope(TenantScope())
        assert a.chave != b.chave


# ════════════════════════════════════════════════════════════════════
#  INVENTÁRIOS POR AST
# ════════════════════════════════════════════════════════════════════
def _py_do_produto():
    for pasta in ("services", "routes", "models", "utils", "middleware"):
        for p in sorted((BACKEND / pasta).rglob("*.py")):
            yield p


def _eh_enum(no, nome):
    return isinstance(no, ast.Attribute) and no.attr == nome and getattr(no.value, "id", "") == "UserRole"


def _eh_str(no, valor):
    return isinstance(no, ast.Constant) and no.value == valor


def _listas_com(predicado):
    achados = []
    for p in _py_do_produto():
        try:
            arvore = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for no in ast.walk(arvore):
            if isinstance(no, (ast.List, ast.Tuple, ast.Set)) and any(predicado(e) for e in no.elts):
                achados.append((p.relative_to(BACKEND).as_posix(), no.lineno, no))
    return achados


#: Listas que mencionam o ADMIN e, de propósito, NÃO levam o Master. Cada uma
#: com o motivo — uma excepção sem motivo é um esquecimento com boas maneiras.
EXCEPCOES_SEM_MASTER = {
    # Mailboxes partilhadas POR NOME DE CAIXA («admin» é uma caixa), não perfis.
    "services/shared_email_helpers.py",
    # Quem recebe alertas por CARGO: o Master é global e inundaria a caixa com
    # os alertas de todas as redes. Audiência de alertas é por rede.
    "services/alerts.py",
    # Destinatários do relatório de IA / stale processes: o Master não é
    # destinatário por cargo (recebe o consolidado em separado).
    "services/scheduled_tasks.py",
    # Perfis que um Admin PODE conceder (o Master nunca é concedido por quem
    # não é Master).
    "services/user_management_scope.py",
    "services/master_promotion.py",
    # Quem recebe o relatório da SUA rede: CEO e Admin. O Master não é
    # destinatário local — o dele é o consolidado (`destino_global`).
    "services/relatorio_semanal_destinos.py",
}


class TestInventarioDasListasDePapeis:
    def test_o_leitor_encontra_listas_de_papeis(self):
        """Contraprova: sem isto, um leitor cego daria «nenhuma lista sem
        Master» e o inventário passava a provar nada."""
        enum = _listas_com(lambda e: _eh_enum(e, "ADMIN"))
        assert len(enum) > 100, f"o leitor só encontrou {len(enum)} listas com UserRole.ADMIN"

    def test_toda_a_lista_com_UserRole_ADMIN_tem_tambem_MASTER(self):
        em_falta = []
        for ficheiro, linha, no in _listas_com(lambda e: _eh_enum(e, "ADMIN")):
            if ficheiro in EXCEPCOES_SEM_MASTER:
                continue
            if not any(_eh_enum(e, "MASTER") for e in no.elts):
                em_falta.append(f"{ficheiro}:{linha}")
        assert not em_falta, (
            "Listas de papéis com ADMIN mas sem MASTER (o Master ficaria de fora; "
            "se a omissão é de propósito, declara-a em EXCEPCOES_SEM_MASTER com o motivo):\n  "
            + "\n  ".join(em_falta)
        )

    def test_toda_a_lista_de_strings_com_admin_tem_tambem_master(self):
        em_falta = []
        for ficheiro, linha, no in _listas_com(lambda e: _eh_str(e, "admin")):
            if ficheiro in EXCEPCOES_SEM_MASTER:
                continue
            if not any(_eh_str(e, "master") for e in no.elts):
                em_falta.append(f"{ficheiro}:{linha}")
        assert not em_falta, (
            "Listas de strings com 'admin' mas sem 'master':\n  " + "\n  ".join(em_falta)
        )

    def test_nenhuma_lista_de_papeis_sem_fronteira_inclui_admin_ou_ceo(self):
        """A fronteira de rede tem UMA excepção (`PAPEIS_GLOBAIS`). Se
        alguém voltar a escrever `{ADMIN, CEO}` à mão para dizer «sem
        fronteira», o Admin volta a ser global — e isto apanha-o."""
        suspeitos = []
        for p in _py_do_produto():
            arvore = ast.parse(p.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Assign):
                    continue
                for alvo in no.targets:
                    nome = getattr(alvo, "id", "")
                    if not re.search(r"SEM_FRONTEIRA|ATRAVESSAM_REDES|RECONCILIACAO", nome):
                        continue
                    texto = ast.unparse(no.value)
                    if re.search(r"\bADMIN\b|'admin'|\bCEO\b|'ceo'", texto):
                        suspeitos.append(f"{p.relative_to(BACKEND).as_posix()}:{no.lineno} {nome} = {texto}")
        assert not suspeitos, "\n".join(suspeitos)

    def test_as_constantes_de_fronteira_derivam_do_papel_global(self):
        """Contraprova do teste de cima: as constantes existem e valem só Master."""
        from services.deadline_scope import PAPEIS_SEM_FRONTEIRA_DE_REDE
        from services.email_access import PAPEIS_QUE_ATRAVESSAM_REDES
        from services.origem_financeira import PAPEIS_SEM_FRONTEIRA as ORIGEM
        from services.process_sharing_api import PAPEIS_SEM_FRONTEIRA as PARTILHA
        from services.s3_explorer_scope import PAPEIS_DE_RECONCILIACAO
        from services.workflow_phases import papeis_de_reconciliacao

        assert set(PAPEIS_SEM_FRONTEIRA_DE_REDE) == {"master"}
        assert set(PAPEIS_QUE_ATRAVESSAM_REDES) == {"master"}
        assert set(ORIGEM) == {"master"}
        assert set(PARTILHA) == {"master"}
        assert {getattr(p, "value", p) for p in PAPEIS_DE_RECONCILIACAO} == {"master"}
        assert {getattr(p, "value", p) for p in papeis_de_reconciliacao()} == {"master"}


# ── rotas ──────────────────────────────────────────────────────────
def _rotas():
    """(ficheiro, funcao, linha-da-assinatura) de todos os handlers de rotas."""
    for p in sorted((BACKEND / "routes").rglob("*.py")):
        fonte = p.read_text(encoding="utf-8")
        for no in ast.walk(ast.parse(fonte)):
            if isinstance(no, (ast.AsyncFunctionDef, ast.FunctionDef)) and no.decorator_list:
                yield p.relative_to(BACKEND).as_posix(), no.name, ast.unparse(no.args) + " " + " ".join(
                    ast.unparse(d) for d in no.decorator_list
                )


class TestInventarioDasRotas:
    def test_o_leitor_de_rotas_le_mesmo(self):
        rotas = list(_rotas())
        assert len(rotas) > 500
        assert sum("require_roles" in a for _, _, a in rotas) > 200

    def test_nenhuma_rota_e_so_admin_a_infraestrutura_e_so_master(self):
        """Antes da adenda havia ~108 rotas «só Admin» — logs, backups,
        índices, encriptação, S3, jobs, IA. Eram o perfil global a operar a
        infraestrutura. Hoje são do Master; uma rota de infraestrutura que
        volte a aceitar o Admin é a fuga que isto fecha."""
        sobras = [
            f"{f}::{n}" for f, n, a in _rotas()
            if "require_roles([UserRole.MASTER, UserRole.ADMIN])" in a
        ]
        assert not sobras, sobras

    def test_a_infraestrutura_global_e_so_master(self):
        """Módulos inteiros cuja natureza é global (migrações da base,
        diagnósticos, encriptação, backups)."""
        precisam = {
            "routes/admin_migration.py", "routes/admin_process_migration.py",
            "routes/diagnostics.py", "routes/admin_encryption.py", "routes/backup.py",
            "routes/admin_storage.py",
        }
        for ficheiro, nome, a in _rotas():
            if ficheiro not in precisam:
                continue
            gates = re.findall(r"require_roles\(\[(.*?)\]\)", a)
            for g in gates:
                # `admin_storage` mantém uma leitura de mapeamentos para gestão,
                # já com âmbito de rede (ver o teste de rotas com âmbito).
                if ficheiro == "routes/admin_storage.py" and nome in {"get_client_s3_mappings_alias"}:
                    continue
                assert g.strip() == "UserRole.MASTER", f"{ficheiro}::{nome} aceita {g}"

    def test_os_resets_e_migracoes_nao_estao_ao_alcance_do_diretor(self):
        """O `admin_migration` e o `admin_process_migration` aceitavam o
        DIRETOR — para reencriptar a base inteira e fazer reset de processos."""
        for ficheiro, nome, a in _rotas():
            if ficheiro in {"routes/admin_migration.py", "routes/admin_process_migration.py"}:
                assert "DIRETOR" not in a and "CEO" not in a, f"{nome}"

    def test_a_anonimizacao_em_lote_e_so_master(self):
        a = next(a for f, n, a in _rotas() if f == "routes/gdpr.py" and n == "anonymize_batch")
        assert "require_roles([UserRole.MASTER])" in a

    def test_a_edicao_global_de_fases_e_so_master(self):
        for nome in ("create_workflow_status", "update_workflow_status", "delete_workflow_status"):
            a = next(a for f, n, a in _rotas() if f == "routes/admin.py" and n == nome)
            assert "require_roles([UserRole.MASTER])" in a, nome

    def test_criar_e_apagar_empresas_e_so_master(self):
        fonte = (BACKEND / "routes" / "companies_crud.py").read_text(encoding="utf-8")
        for nome in ("create_company", "delete_company"):
            i = fonte.index(f"async def {nome}")
            cabeca = fonte[fonte.rfind("@router", 0, i):i]
            assert "require_master()" in cabeca, nome

    def test_a_migracao_de_ucr_e_so_master(self):
        fonte = (BACKEND / "routes" / "user_company_roles.py").read_text(encoding="utf-8")
        for rota in ('"/migrate"', '"/migrate-email-configs"'):
            linha = next(l for l in fonte.splitlines() if rota in l and "@router" in l)
            assert "require_master()" in linha, rota

    def test_as_rotas_de_ucr_e_empresas_recebem_o_actor(self):
        """O âmbito corre dentro do serviço, que só o aplica se a rota lho
        passar. Uma rota que esqueça o `actor=` deixava a parede em casa."""
        for ficheiro in ("routes/user_company_roles.py", "routes/companies.py", "routes/companies_crud.py"):
            fonte = (BACKEND / ficheiro).read_text(encoding="utf-8")
            for no in ast.walk(ast.parse(fonte)):
                if not isinstance(no, ast.AsyncFunctionDef) or not no.decorator_list:
                    continue
                corpo = ast.unparse(no)
                if re.search(r"await run_(?!list_available|test_email)\w+\(", corpo) and "dependencies=[Depends(require_master" not in corpo:
                    if "migrate" in no.name or no.name in {"create_company", "delete_company", "test_email_connection"}:
                        continue
                    assert "actor=" in corpo or "user=user" in corpo, (
                        f"{ficheiro}::{no.name} não passa o actor"
                    )


# ════════════════════════════════════════════════════════════════════
#  GESTÃO DE UTILIZADORES: QUEM PODE TOCAR EM QUEM
# ════════════════════════════════════════════════════════════════════
@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    _semear(fake_async_db)
    fake_async_db.users.docs.extend([
        {"id": "u-mara", "name": "Mara", "email": "mara@power.pt", "role": "admin", "company": "Power Real Estate"},
        {"id": "u-rui", "name": "Rui", "email": "rui@domus.pt", "role": "ceo", "company": "Domus"},
        {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor", "company": "Power Real Estate"},
        {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "diretor", "company": "Domus"},
        {"id": "u-master", "name": "Master", "email": "m@x.pt", "role": "master"},
    ])
    fake_async_db.user_company_roles.docs.append(
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "admin"}
    )
    return fake_async_db


@pytest.mark.asyncio
class TestGestaoDeUtilizadores:
    async def _carregar(self, mundo, alvo, actor):
        import services.admin_users_scope as scope_mod
        import services.user_management_scope as ums

        with tenant_db(mundo, scope_mod, ums):
            return await ums.carregar_utilizador_gerivel(alvo, actor)

    async def test_o_admin_gere_um_utilizador_da_sua_empresa(self, mundo):
        alvo = await self._carregar(mundo, "u-ana", ADMIN_POWER)
        assert alvo["id"] == "u-ana"

    async def test_o_admin_NAO_gere_um_utilizador_de_outra_rede_e_recebe_404(self, mundo):
        with pytest.raises(HTTPException) as erro:
            await self._carregar(mundo, "u-bruno", ADMIN_POWER)
        assert erro.value.status_code == 404

    async def test_o_404_de_um_alheio_e_igual_ao_de_um_inexistente(self, mundo):
        """Distinguir «não existe» de «não é teu» é um directório de utilizadores."""
        with pytest.raises(HTTPException) as alheio:
            await self._carregar(mundo, "u-bruno", ADMIN_POWER)
        with pytest.raises(HTTPException) as nada:
            await self._carregar(mundo, "u-nao-existe", ADMIN_POWER)
        assert alheio.value.status_code == nada.value.status_code == 404
        assert alheio.value.detail == nada.value.detail

    async def test_o_master_gere_qualquer_um(self, mundo):
        assert (await self._carregar(mundo, "u-bruno", MASTER))["id"] == "u-bruno"

    async def test_um_perfil_local_nunca_gere_um_master_mesmo_na_sua_empresa(self, mundo):
        """O Master tem UCR de admin na Power: está «dentro» da empresa da Mara
        e mesmo assim a Mara não lhe pode mudar a password."""
        with pytest.raises(HTTPException) as erro:
            await self._carregar(mundo, "u-master", ADMIN_POWER)
        assert erro.value.status_code == 404

    async def test_o_master_esta_escondido_mesmo_que_a_consulta_de_ambito_o_deixasse_passar(self, mundo):
        """Duas camadas dizem o mesmo (a pré-verificação do papel global e o
        `$nin` da consulta de âmbito); com ambas ligadas, apagar uma não parte
        nada. Isola-se a primeira neutralizando a segunda — «teste fraco»,
        não mutação perdida."""
        import services.admin_users_scope as scope_mod
        import services.user_management_scope as ums

        async def consulta_larga(_ambito):
            return {}

        with tenant_db(mundo, scope_mod, ums), patch.object(ums, "build_users_scope_query", consulta_larga):
            with pytest.raises(HTTPException) as erro:
                await ums.carregar_utilizador_gerivel("u-master", ADMIN_POWER)
            assert erro.value.status_code == 404
            # contraprova: a mesma consulta larga deixa passar um utilizador comum
            assert (await ums.carregar_utilizador_gerivel("u-ana", ADMIN_POWER))["id"] == "u-ana"

    async def test_cada_um_gere_a_propria_conta(self, mundo):
        assert (await self._carregar(mundo, "u-mara", ADMIN_POWER))["id"] == "u-mara"

    async def test_a_listagem_de_utilizadores_esconde_o_master_a_quem_e_local(self, mundo):
        import services.admin_users_scope as scope_mod
        from services.admin_users_scope import build_users_scope_query, empresas_do_ambito

        with tenant_db(mundo, scope_mod):
            consulta = await build_users_scope_query(await empresas_do_ambito(ADMIN_POWER))
            visiveis = por_id(u for u in mundo.users.docs if casa(u, consulta))
            tudo = await build_users_scope_query(await empresas_do_ambito(MASTER))
        assert "u-ana" in visiveis and "u-mara" in visiveis
        assert "u-master" not in visiveis and "u-bruno" not in visiveis
        assert tudo == {}, "o Master vê todos os utilizadores"

    def test_so_o_master_concede_o_perfil_master(self):
        from services.user_management_scope import exigir_papeis_concediveis

        exigir_papeis_concediveis(MASTER, ["master", "admin"])
        exigir_papeis_concediveis(ADMIN_POWER, ["consultor", "admin", "ceo"])
        with pytest.raises(HTTPException) as erro:
            exigir_papeis_concediveis(ADMIN_POWER, ["consultor", "master"])
        assert erro.value.status_code == 403
        with pytest.raises(HTTPException):
            exigir_papeis_concediveis(CEO_DOMUS, ["Master"])

    async def test_so_se_concede_acesso_a_empresas_do_proprio_ambito(self, mundo):
        import services.admin_users_scope as scope_mod
        import services.user_management_scope as ums

        with tenant_db(mundo, scope_mod, ums):
            await ums.exigir_empresas_concediveis(ADMIN_POWER, ["cmp-power"])
            await ums.exigir_empresas_concediveis(ADMIN_POWER, ["Precision Crédito"])  # mesma rede
            with pytest.raises(HTTPException) as erro:
                await ums.exigir_empresas_concediveis(ADMIN_POWER, ["cmp-domus"])
            await ums.exigir_empresas_concediveis(MASTER, ["cmp-domus"])
        assert erro.value.status_code == 404


@pytest.mark.asyncio
class TestAsEscritasDeUtilizadorEstaoLigadasAParede:
    """As três escritas que não verificavam o objecto."""

    def test_a_edicao_a_eliminacao_e_a_personificacao_usam_a_parede(self):
        from services import admin_users

        for nome in ("run_update_user", "run_delete_user", "run_impersonate_user"):
            corpo = ast.unparse(ast.parse((BACKEND / "services" / "admin_users.py").read_text(encoding="utf-8")))
            i = corpo.index(f"async def {nome}")
            fim = corpo.find("\nasync def ", i + 1)
            assert "carregar_utilizador_gerivel" in corpo[i:fim if fim > 0 else None], nome
        assert admin_users  # noqa: B018 — import usado

    def test_a_criacao_recusa_master_e_empresas_alheias_ANTES_de_inserir(self):
        corpo = (BACKEND / "services" / "admin_users.py").read_text(encoding="utf-8")
        i = corpo.index("async def run_create_user")
        fim = corpo.index("\nasync def ", i + 1)
        criar = corpo[i:fim]
        assert criar.index("exigir_papeis_concediveis") < criar.index("db.users.insert_one")
        assert criar.index("exigir_empresas_concediveis") < criar.index("db.users.insert_one")

    def test_os_ucr_passam_pela_parede_em_todas_as_operacoes(self):
        fonte = (BACKEND / "services" / "user_company_roles_api_crud.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        for no in arvore.body:
            if isinstance(no, ast.AsyncFunctionDef) and no.name.startswith("run_"):
                assert any(a.arg == "actor" for a in no.args.kwonlyargs), f"{no.name} não exige o actor"

    async def test_um_admin_nao_se_da_a_si_proprio_o_cargo_master_por_UCR(self, mundo):
        import services.admin_users_scope as scope_mod
        import services.user_company_roles_api_crud as crud
        import services.user_management_scope as ums
        from models.user_company_role import UserCompanyRoleCreate

        pedido = UserCompanyRoleCreate(
            user_id="u-mara", company_id="cmp-power", company_name="Power Real Estate", role="master",
        )
        with tenant_db(mundo, scope_mod, ums, crud):
            with pytest.raises(HTTPException) as erro:
                await crud.run_create_user_company_role(pedido, actor=ADMIN_POWER)
        assert erro.value.status_code == 403
        assert not [u for u in mundo.user_company_roles.docs
                    if u.get("user_id") == "u-mara" and u.get("role") == "master"]

    async def test_um_admin_nao_da_acesso_a_uma_empresa_de_outra_rede(self, mundo):
        import services.admin_users_scope as scope_mod
        import services.user_company_roles_api_crud as crud
        import services.user_management_scope as ums
        from models.user_company_role import UserCompanyRoleCreate

        pedido = UserCompanyRoleCreate(
            user_id="u-ana", company_id="cmp-domus", company_name="Domus", role="consultor",
        )
        with tenant_db(mundo, scope_mod, ums, crud):
            with pytest.raises(HTTPException) as erro:
                await crud.run_create_user_company_role(pedido, actor=ADMIN_POWER)
        assert erro.value.status_code == 404

    async def test_o_admin_lista_so_os_ucr_da_sua_rede(self, mundo):
        import services.admin_users_scope as scope_mod
        import services.user_company_roles_api_crud as crud
        import services.user_management_scope as ums

        with tenant_db(mundo, scope_mod, ums, crud):
            r = await crud.run_list_user_company_roles(actor=ADMIN_POWER)
            todos = await crud.run_list_user_company_roles(actor=MASTER)
        empresas = {x["company_id"] for x in r["roles"]}
        assert "cmp-domus" not in empresas and "cmp-power" in empresas
        assert "cmp-domus" in {x["company_id"] for x in todos["roles"]}
        assert all(x["role"] != "master" for x in r["roles"])

    async def test_um_admin_nao_muda_a_rede_de_uma_empresa(self, mundo):
        import services.admin_users_scope as scope_mod
        import services.companies_crud_api_mutate as mut
        import services.user_management_scope as ums
        from models.company import CompanyUpdate

        with tenant_db(mundo, scope_mod, ums, mut):
            with pytest.raises(HTTPException) as erro:
                await mut.run_update_company(
                    "cmp-power", CompanyUpdate(network_id=REDE_DOMUS), actor=ADMIN_POWER,
                )
        assert erro.value.status_code == 403
        power = next(c for c in mundo.companies.docs if c["id"] == "cmp-power")
        assert power["network_id"] == REDE_INCUMBENTE

    async def test_um_admin_nao_edita_a_empresa_de_outra_rede(self, mundo):
        import services.admin_users_scope as scope_mod
        import services.companies_crud_api_mutate as mut
        import services.user_management_scope as ums
        from models.company import CompanyUpdate

        with tenant_db(mundo, scope_mod, ums, mut):
            with pytest.raises(HTTPException) as erro:
                await mut.run_update_company("cmp-domus", CompanyUpdate(phone="1"), actor=ADMIN_POWER)
        assert erro.value.status_code == 404

    async def test_o_master_muda_a_rede(self, mundo):
        import services.admin_users_scope as scope_mod
        import services.companies_crud_api_mutate as mut
        import services.user_management_scope as ums
        from models.company import CompanyUpdate

        with tenant_db(mundo, scope_mod, ums, mut):
            await mut.run_update_company("cmp-domus", CompanyUpdate(network_id="outra"), actor=MASTER)
        assert next(c for c in mundo.companies.docs if c["id"] == "cmp-domus")["network_id"] == "outra"


# ════════════════════════════════════════════════════════════════════
#  PROMOVER A MASTER
# ════════════════════════════════════════════════════════════════════
class TestPromocaoAMaster:
    UTIL = [
        {"id": "1", "email": "dono@x.pt", "role": "admin"},
        {"id": "2", "email": "ceo@x.pt", "role": "ceo"},
        {"id": "3", "email": "cons@x.pt", "role": "consultor"},
        {"id": "4", "email": "ja@x.pt", "role": "master"},
        {"id": "5", "email": "off@x.pt", "role": "admin", "is_active": False},
    ]

    def test_promove_admin_e_ceo(self):
        from services.master_promotion import planear

        plano = planear(["dono@x.pt", "CEO@x.pt"], self.UTIL)
        assert [u["id"] for u in plano.promover] == ["1", "2"]
        assert plano.pode_aplicar

    def test_um_email_que_nao_existe_e_um_erro_dito_e_o_plano_nao_se_aplica(self):
        from services.master_promotion import planear

        plano = planear(["dono@x.pt", "fantasma@x.pt"], self.UTIL)
        assert [e for e, _ in plano.recusados] == ["fantasma@x.pt"]
        assert not plano.pode_aplicar, "meio plano é pior do que nenhum"

    def test_nao_promove_um_consultor_sem_a_bandeira(self):
        from services.master_promotion import planear

        assert not planear(["cons@x.pt"], self.UTIL).promover
        assert planear(["cons@x.pt"], self.UTIL, qualquer_papel=True).promover

    def test_nao_promove_contas_desactivadas_e_ignora_quem_ja_e_master(self):
        from services.master_promotion import planear

        plano = planear(["off@x.pt", "ja@x.pt"], self.UTIL)
        assert [e for e, _ in plano.recusados] == ["off@x.pt"]
        assert [u["id"] for u in plano.ja_master] == ["4"]

    @pytest.mark.asyncio
    async def test_aplicar_escreve_o_papel_e_deixa_rasto(self, fake_async_db):
        from services.master_promotion import aplicar, planear

        fake_async_db.users.docs.extend(dict(u) for u in self.UTIL)
        plano = planear(["dono@x.pt"], self.UTIL)
        assert await aplicar(plano, fake_async_db) == 1
        dono = next(u for u in fake_async_db.users.docs if u["id"] == "1")
        assert dono["role"] == "master" and dono["previous_role"] == "admin"
        assert fake_async_db.audit_logs.docs[0]["action"] == "promoted_to_master"

    @pytest.mark.asyncio
    async def test_um_plano_com_recusas_nao_escreve_nada(self, fake_async_db):
        from services.master_promotion import aplicar, planear

        fake_async_db.users.docs.extend(dict(u) for u in self.UTIL)
        plano = planear(["dono@x.pt", "fantasma@x.pt"], self.UTIL)
        with pytest.raises(ValueError):
            await aplicar(plano, fake_async_db)
        assert next(u for u in fake_async_db.users.docs if u["id"] == "1")["role"] == "admin"

    def test_o_script_so_escreve_com_aplicar(self):
        fonte = (BACKEND / "scripts" / "promote_to_master.py").read_text(encoding="utf-8")
        assert "args.aplicar" in fonte
        assert fonte.index("if not args.aplicar") < fonte.index("mp.aplicar(")
