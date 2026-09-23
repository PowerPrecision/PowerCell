"""
Kanban e Ficheiros: o isolamento por Rede tem de ser absoluto (Lote 5, ponto 1).

PORQUE É QUE O KANBAN VAZOU
  Não vazou: o isolamento nunca lá chegou. O Lote 4 ligou a condição de
  rede ao `build_process_list_query` e ao `run_get_processes*` — e o
  Kanban tem um construtor de query SEPARADO (`build_kanban_query`) que
  não passa por nenhum dos dois. Um utilizador de uma empresa isolada não
  via processos na listagem e via-os todos no quadro.

  A lição é de método, não de código: fiz um ponto único para a CONDIÇÃO
  e não fiz o inventário dos sítios que LISTAM. Este ficheiro é também
  esse inventário, com um teste por superfície.

FICHEIROS (`/ficheiros`)
  O explorador de S3 é global e o bucket está organizado por pasta de
  CLIENTE, não por empresa: filtrar por rede obrigaria a mapear pasta →
  processo → rede em cada listagem. Decisão do dono: restringir a página
  a quem já tem visão global (Admin e CEO) e adiar o filtro por pasta —
  com o multi-tenant, as empresas comuns chegam aos ficheiros pela ficha
  do processo, não por aqui.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from tests.unit.test_tenant_network_isolation import (
    ANA, BRUNO, REDE_DOMUS, REDE_INCUMBENTE, _semear, _tenant_db, _por_id,
)


async def _noop(*a, **k):
    return None


def _semear_quadro(fake_db):
    """Cenário do isolamento + as COLUNAS do quadro.

    Sem colunas, `build_kanban_columns` devolve uma lista vazia e o teste
    da fuga passa sem provar nada — foi a contraprova que o denunciou.
    """
    db = _semear(fake_db)
    db.workflow_statuses.docs.append(
        {"name": "novo", "label": "Novo", "order": 1, "is_active": True},
    )
    return db


def _sem_enriquecimento():
    """Desliga o enriquecimento do quadro (portal, actividades).

    São consultas de apresentação sobre processos JÁ filtrados; o que
    está sob teste é a query, não os adornos. `run_get_kanban_board`
    importa-as dentro da função, por isso o patch é no módulo de origem.
    """
    import contextlib

    import services.process_list_enrichment as ple

    @contextlib.contextmanager
    def _ctx():
        with patch.object(ple, "enrich_processes_portal_flags", _noop), \
             patch.object(ple, "enrich_processes_latest_activity", _noop, create=True):
            yield

    return _ctx()


class TestKanbanIsolado:
    @pytest.mark.asyncio
    async def test_diretora_de_outra_rede_nao_ve_o_quadro_da_power(
        self, fake_async_db, monkeypatch,
    ):
        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
        import services.process_kanban_enrichment as kanban
        import services.tenant_network as tn  # noqa: F401  (usado por _tenant_db)

        db = _semear_quadro(fake_async_db)
        with _tenant_db(db), patch.object(kanban, "db", db), _sem_enriquecimento():
            resposta = await kanban.run_get_kanban_board(
                user=BRUNO, role="diretor", show_all=True,
                consultor_id=None, mediador_id=None, indexacao_id=None,
                parceiro_id=None, view_mode="all", completed_days=0,
                decrypt_list_fn=lambda docs, **kw: docs,
                kanban_projection={"_id": 0},
            )

        vistos = _ids_do_quadro(resposta)
        assert "p-power" not in vistos, "FUGA: Domus a ver o quadro da Power"
        assert "p-legado" not in vistos

    @pytest.mark.asyncio
    async def test_o_grupo_incumbente_continua_a_ver_o_seu_quadro(
        self, fake_async_db, monkeypatch,
    ):
        """Contraprova: esvaziar o quadro a toda a gente passaria no teste
        acima."""
        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
        import services.process_kanban_enrichment as kanban

        db = _semear_quadro(fake_async_db)
        with _tenant_db(db), patch.object(kanban, "db", db), _sem_enriquecimento():
            resposta = await kanban.run_get_kanban_board(
                user=ANA, role="diretor", show_all=True,
                consultor_id=None, mediador_id=None, indexacao_id=None,
                parceiro_id=None, view_mode="all", completed_days=0,
                decrypt_list_fn=lambda docs, **kw: docs,
                kanban_projection={"_id": 0},
            )

        assert "p-power" in _ids_do_quadro(resposta)


def _ids_do_quadro(resposta) -> set:
    """Os ids de todas as colunas do quadro, seja qual for a forma."""
    encontrados = set()

    def recolher(valor):
        if isinstance(valor, dict):
            if "id" in valor and "client_name" in valor:
                encontrados.add(valor["id"])
                return
            for item in valor.values():
                recolher(item)
        elif isinstance(valor, list):
            for item in valor:
                recolher(item)

    recolher(resposta)
    return encontrados


class TestExploradorDeFicheirosRestrito:
    """Decisão do dono: o S3 Explorer global é de Admin e CEO."""

    def test_ver_ficheiros_e_so_para_a_gestao_de_topo(self):
        from models.auth import UserRole
        from services.admin_s3_explorer import FILE_VIEW_ROLES

        assert set(FILE_VIEW_ROLES) == {UserRole.ADMIN, UserRole.CEO}

    def test_operar_sobre_ficheiros_e_so_para_a_gestao_de_topo(self):
        from models.auth import UserRole
        from services.admin_s3_explorer import FILE_OPS_ROLES

        assert set(FILE_OPS_ROLES) == {UserRole.ADMIN, UserRole.CEO}

    def test_o_consultor_perde_o_explorador_global(self):
        """O que estava a vazar: um consultor de uma empresa isolada
        navegava o bucket inteiro."""
        from models.auth import UserRole
        from services.admin_s3_explorer import FILE_OPS_ROLES, FILE_VIEW_ROLES

        for papel in (UserRole.CONSULTOR, UserRole.INTERMEDIARIO,
                      UserRole.INDEXACAO, UserRole.DIRETOR,
                      UserRole.ADMINISTRATIVO):
            assert papel not in FILE_VIEW_ROLES
            assert papel not in FILE_OPS_ROLES

    def test_a_listagem_do_explorador_usa_a_constante_restrita(self):
        """Guarda: a rota tinha a lista de papéis escrita À MÃO, mais
        larga do que a constante ao lado dela."""
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = (
            Path(__file__).resolve().parents[2] / "routes" / "admin_storage.py"
        ).read_text("utf-8")
        codigo = codigo_sem_comentarios(fonte)
        bloco = codigo[codigo.index("def get_s3_folder_contents"):]
        bloco = bloco[: bloco.index("def s3_rename")]
        assert "FILE_VIEW_ROLES" in bloco, (
            "a rota do explorador volta a declarar os papéis à mão"
        )
        assert "UserRole.CONSULTOR" not in bloco

    def test_os_ficheiros_do_PROCESSO_continuam_acessiveis(self):
        """O consultor perde o explorador GLOBAL, não os ficheiros dos
        processos dele — esses vão por `/documents/*`, outro caminho."""
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2] / "routes" / "documents.py"
        ).read_text("utf-8")
        assert "FILE_VIEW_ROLES" not in fonte
