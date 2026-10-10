"""
PORTAL DO PARCEIRO — INVENTÁRIOS POR AST

Um inventário falha por OMISSÃO: o que se escreve amanhã e ninguém lembrou
de declarar aqui é o que o teste aponta. Cada leitor traz a sua CONTRAPROVA
de que leu mesmo — uma asserção `x in nomes` continua a passar com um leitor
que devolva pouco, e um verde assim é pior do que um vermelho.

  1. rotas do parceiro: todas com sessão, excepto as três declaradas;
  2. nenhuma rota do parceiro usa a identidade do staff (nem o contrário);
  3. `db.partners` só é lido/escrito pelos módulos de identidade;
  4. toda a consulta a processos/clientes de `services/partner_*` passa pelas
     condições de visibilidade — ou é uma excepção ESCRITA;
  5. todo o escritor de processos do CRM aplica a herança do parceiro — ou é
     uma excepção ESCRITA (migrações e sementes).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


def _arvore(caminho: str) -> ast.Module:
    return ast.parse((BACKEND / caminho).read_text(encoding="utf-8"))


def _funcoes(arvore: ast.AST):
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield no


def _nomes_chamados(no: ast.AST) -> set[str]:
    nomes = set()
    for sub in ast.walk(no):
        if isinstance(sub, ast.Call):
            f = sub.func
            nomes.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    return nomes


def _nomes_usados(arvore: ast.AST) -> set[str]:
    """Identificadores e atributos que o CÓDIGO usa — nunca o texto de uma
    docstring. Uma guarda que lê as explicações proíbe a explicação do
    defeito que previne (e a saída óbvia é apagá-la)."""
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, (ast.Import, ast.ImportFrom)):
            nomes.update(a.asname or a.name.split(".")[-1] for a in no.names)
    return nomes


def _e_rota(fn) -> bool:
    return any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
        and isinstance(d.func.value, ast.Name) and d.func.value.id == "router"
        for d in fn.decorator_list
    )


def _depende_de(fn, nome: str) -> bool:
    for default in [*fn.args.defaults, *fn.args.kw_defaults]:
        if default is None:
            continue
        if "Depends" in ast.unparse(default) and nome in ast.unparse(default):
            return True
    return False


def _rotas(caminho: str) -> list:
    return [fn for fn in _funcoes(_arvore(caminho)) if _e_rota(fn)]


# ════════════════════════════════════════════════════════════════════
#  1 e 2. AS ROTAS
# ════════════════════════════════════════════════════════════════════
class TestAsRotasDoParceiro:
    def test_o_leitor_encontra_as_rotas(self):
        """Contraprova: se o leitor devolvesse pouco, os testes abaixo
        passavam por cegueira."""
        nomes = {fn.name for fn in _rotas("routes/partner_portal.py")}
        assert {"partner_login", "partner_me", "partner_dashboard", "partner_list_cases", "partner_get_case",
                "partner_submit_lead", "partner_upload_url", "partner_confirm_upload",
                "partner_download_url"} <= nomes
        assert len(nomes) >= 12

    def test_toda_a_rota_exige_sessao_excepto_as_declaradas(self):
        from routes.partner_portal import ROTAS_SEM_SESSAO

        sem_sessao = {fn.name for fn in _rotas("routes/partner_portal.py") if not _depende_de(fn, "get_current_partner")}
        assert sem_sessao == set(ROTAS_SEM_SESSAO), (
            f"rotas sem sessão que não estão declaradas (ou declaradas que a têm): {sem_sessao ^ set(ROTAS_SEM_SESSAO)}"
        )

    def test_as_rotas_sem_sessao_sao_so_a_entrada(self):
        from routes.partner_portal import ROTAS_SEM_SESSAO

        assert ROTAS_SEM_SESSAO == {"partner_login", "partner_get_invite", "partner_accept_invite"}

    def test_o_router_do_parceiro_nao_usa_a_identidade_do_staff(self):
        usados = _nomes_usados(_arvore("routes/partner_portal.py"))
        assert "get_current_partner" in usados, "o leitor não viu a dependência (cegueira)"
        for proibido in ("get_current_user", "require_roles", "require_staff", "require_admin", "get_current_client"):
            assert proibido not in usados, proibido

    def test_nenhum_router_do_staff_usa_a_identidade_do_parceiro(self):
        for caminho in sorted((BACKEND / "routes").rglob("*.py")):
            if caminho.name == "partner_portal.py":
                continue
            assert "get_current_partner" not in caminho.read_text(encoding="utf-8"), caminho.name

    def test_a_gestao_de_parceiros_exige_gestao_em_todas_as_rotas(self):
        rotas = _rotas("routes/partners_admin.py")
        assert len(rotas) >= 5
        for fn in rotas:
            assert _depende_de(fn, "require_roles"), fn.name
            assert "get_current_partner" not in ast.unparse(fn)

    def test_as_rotas_de_gestao_passam_o_actor_ao_servico(self):
        """O OBJECTO verifica-se no serviço, e só se o actor lá chegar."""
        for fn in _rotas("routes/partners_admin.py"):
            chamadas = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                        and isinstance(c.func, ast.Name) and c.func.id.startswith("run_")]
            assert chamadas, fn.name
            for c in chamadas:
                assert any(isinstance(a, ast.Name) and a.id == "user" for a in c.args), fn.name

    def test_os_routers_estao_registados_no_servidor(self):
        fonte = (BACKEND / "server.py").read_text(encoding="utf-8")
        assert 'app.include_router(partner_portal_router, prefix="/api")' in fonte
        assert 'app.include_router(partners_admin_router, prefix="/api")' in fonte


# ════════════════════════════════════════════════════════════════════
#  3. QUEM TOCA EM `db.partners`
# ════════════════════════════════════════════════════════════════════
class TestQuemTocaEmPartners:
    #: identidade + a declaração dos índices (que só os CRIA).
    PERMITIDOS = {"services/partner_security.py", "services/partner_accounts.py", "services/db_indexes.py"}

    @staticmethod
    def _toca_em_partners(arvore: ast.AST) -> bool:
        return any(
            isinstance(no, ast.Attribute) and no.attr == "partners"
            and isinstance(no.value, ast.Name) and no.value.id == "db"
            for no in ast.walk(arvore)
        )

    def _modulos_que_usam(self) -> set[str]:
        achados = set()
        for pasta in ("services", "routes", "middleware"):
            for caminho in sorted((BACKEND / pasta).rglob("*.py")):
                if self._toca_em_partners(ast.parse(caminho.read_text(encoding="utf-8"))):
                    achados.add(str(caminho.relative_to(BACKEND)))
        return achados

    def test_a_colecao_so_e_acedida_pelos_modulos_de_identidade(self):
        achados = self._modulos_que_usam()
        assert self.PERMITIDOS <= achados, "o leitor não encontrou os módulos de identidade (cegueira)"
        assert achados == self.PERMITIDOS, f"módulo novo a tocar em db.partners: {achados - self.PERMITIDOS}"

    def test_o_segredo_do_parceiro_so_vive_no_modulo_de_seguranca(self):
        for pasta in ("services", "routes", "middleware"):
            for caminho in sorted((BACKEND / pasta).rglob("*.py")):
                if caminho.name == "partner_security.py":
                    continue
                literais = {
                    no.value for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8")))
                    if isinstance(no, ast.Constant) and isinstance(no.value, str) and no.value == "JWT_PARTNER_SECRET"
                }
                assert not literais, str(caminho)


# ════════════════════════════════════════════════════════════════════
#  4. AS CONSULTAS DO PARCEIRO PASSAM PELAS CONDIÇÕES
# ════════════════════════════════════════════════════════════════════
MODULOS_DO_PARCEIRO = (
    "services/partner_portal_read.py",
    "services/partner_upload_ops.py",
    "services/partner_leads.py",
)

#: (módulo, função) → porque é que NÃO precisa da condição.
EXCEPCOES_DE_CONSULTA = {
    ("services/partner_upload_ops.py", "_avisar_a_equipa"): (
        "lê só os ids de atribuição de um processo JÁ resolvido por `resolver_caso` (que usa a condição)"
    ),
    ("services/partner_leads.py", "_contar_leads_recentes"): "conta as leads do próprio parceiro (filtro pelo id dele)",
    ("services/partner_leads.py", "_candidatos_a_duplicado"): (
        "procura iguais DENTRO da rede do parceiro para a triagem — `build_network_scope_condition`, "
        "nunca devolvidos ao parceiro"
    ),
    ("services/partner_leads.py", "run_submit_lead"): "duplo clique: filtra por `submitted_by_partner_id == eu`",
}


def _consultas(caminho: str):
    """(função, coleção, método) de cada `db.processes|clients.<método>(...)`."""
    for fn in _funcoes(_arvore(caminho)):
        for sub in ast.walk(fn):
            if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                    and isinstance(sub.func.value, ast.Attribute)
                    and isinstance(sub.func.value.value, ast.Name) and sub.func.value.value.id == "db"
                    and sub.func.value.attr in ("processes", "clients")
                    and sub.func.attr in ("find", "find_one", "count_documents", "aggregate")):
                yield fn, sub.func.value.attr, sub.func.attr


class TestAsConsultasPassamPelasCondicoes:
    def test_o_leitor_encontra_consultas(self):
        total = sum(len(list(_consultas(c))) for c in MODULOS_DO_PARCEIRO)
        assert total >= 5, f"o leitor só viu {total} consultas (cegueira)"

    @pytest.mark.parametrize("caminho", MODULOS_DO_PARCEIRO)
    def test_cada_consulta_usa_a_condicao_ou_e_uma_excepcao_escrita(self, caminho):
        condicao = {"processes": "condicao_de_processos", "clients": "condicao_de_leads"}
        for fn, colecao, metodo in _consultas(caminho):
            if (caminho, fn.name) in EXCEPCOES_DE_CONSULTA:
                continue
            assert condicao[colecao] in ast.unparse(fn), (
                f"{caminho}::{fn.name} consulta db.{colecao}.{metodo} sem {condicao[colecao]} "
                "(declare a excepção, com o motivo, ou use a condição)"
            )

    def test_as_excepcoes_escritas_ainda_existem(self):
        """Uma excepção para uma função que já não existe é lixo que aprova
        em silêncio a próxima função com esse nome."""
        for (caminho, nome), motivo in EXCEPCOES_DE_CONSULTA.items():
            assert motivo and any(f.name == nome for f in _funcoes(_arvore(caminho))), (caminho, nome)

    def test_a_visibilidade_nao_usa_o_ramo_das_redes_convidadas(self):
        usados = _nomes_usados(_arvore("services/partner_visibility.py"))
        assert "build_network_scope_condition" in usados, "o leitor não viu a condição (cegueira)"
        assert "build_process_scope_condition" not in usados
        assert "CAMPO_REDES_PARCEIRAS" not in usados

    def test_a_visibilidade_nao_tem_acesso_a_base_de_dados(self):
        """A regra é PURA: prova-se sem Mongo e lê-se num sítio só."""
        arvore = _arvore("services/partner_visibility.py")
        usados = _nomes_usados(arvore)
        assert "db" not in usados and "database" not in usados
        assert not any(isinstance(f, ast.AsyncFunctionDef) for f in _funcoes(arvore))


# ════════════════════════════════════════════════════════════════════
#  5. OS ESCRITORES DE PROCESSOS HERDAM O PARCEIRO
# ════════════════════════════════════════════════════════════════════
#: função → porque é que NÃO herda o parceiro de um cliente.
EXCEPCOES_DE_ESCRITORES = {
    ("services/admin_proc_migration_api.py", "run_rollback_migration"): (
        "repõe processos de uma cópia anterior à migração (dados que já existiam)"
    ),
    ("services/admin_dev_ops.py", "run_seed_realistic_data"): "semente de desenvolvimento (só-Master, bloqueada em produção)",
}


def _escritores_de_processos() -> list[tuple[str, str]]:
    achados = []
    for caminho in sorted((BACKEND / "services").rglob("*.py")):
        rel = str(caminho.relative_to(BACKEND))
        for fn in _funcoes(ast.parse(caminho.read_text(encoding="utf-8"))):
            for sub in ast.walk(fn):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr in ("insert_one", "insert_many")
                        and isinstance(sub.func.value, ast.Attribute) and sub.func.value.attr == "processes"):
                    achados.append((rel, fn.name))
                    break
    return achados


class TestOsEscritoresDeProcessosHerdamOParceiro:
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

    def test_todo_o_escritor_aplica_a_heranca_ou_e_uma_excepcao_escrita(self):
        em_falta = []
        for rel, nome in _escritores_de_processos():
            if (rel, nome) in EXCEPCOES_DE_ESCRITORES:
                continue
            fn = next(f for f in _funcoes(_arvore(rel)) if f.name == nome and any(
                isinstance(s, ast.Attribute) and s.attr == "processes" for s in ast.walk(f)))
            # O escritor pode herdar na própria função ou numa que ele chama
            # no mesmo módulo (ex.: o bundle de criação): procura-se no módulo.
            modulo = (BACKEND / rel).read_text(encoding="utf-8")
            if "aplicar_parceiro_do_cliente" not in modulo:
                em_falta.append(f"{rel}::{fn.name}")
        assert not em_falta, (
            "escritores de processos que nunca herdam o parceiro (o caso desaparece do ecrã dele): "
            f"{em_falta}"
        )

    def test_a_heranca_corre_antes_da_gravacao(self):
        """No mesmo corpo, a chamada à herança antecede o `insert_one` — herdar
        depois de gravar não escreve em lado nenhum."""
        for rel in ("services/client_assign.py", "services/onboarding_mandatory_config.py",
                    "services/client_process_ops.py"):
            fonte = (BACKEND / rel).read_text(encoding="utf-8")
            herdar = fonte.index("aplicar_parceiro_do_cliente(")
            gravar = fonte.index("processes.insert_one(", herdar)
            assert herdar < gravar, rel

    def test_as_excepcoes_escritas_ainda_existem(self):
        for (rel, nome), motivo in EXCEPCOES_DE_ESCRITORES.items():
            assert motivo and any(f.name == nome for f in _funcoes(_arvore(rel))), (rel, nome)

    def test_a_funcao_de_heranca_e_pura(self):
        arvore = _arvore("services/partner_attribution.py")
        assert "db" not in _nomes_usados(arvore) and "database" not in _nomes_usados(arvore)
        assert not any(isinstance(n, (ast.Await, ast.AsyncFunctionDef)) for n in ast.walk(arvore))
