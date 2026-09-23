"""
Regra de ouro: o perfil Indexação não deixa rasto (Lote 4, restrição de segurança).

A REGRA (PACOTE BJ, reafirmada pelo dono neste lote)
  As acções do perfil `indexacao` NÃO geram registos de atividade nem de
  histórico. O indexador actua de forma silenciosa no mural do processo.

  O `audit_trail_service` é EXCLUÍDO desta regra de propósito: é um trilho
  de conformidade (com IP e política de retenção) e tem de manter
  rastreabilidade mesmo quando o histórico visível ao utilizador é
  silenciado. Não "corrigir" isso.

O QUE ESTE FICHEIRO ENCONTROU
  1. `_is_stealth_user` olhava só para `user["role"]` — o papel do JWT.
     Num sistema multi-perfil, quem entra COMO Indexação tem
     `effective_role == "indexacao"` e um `role` base diferente: deixava
     rasto apesar de estar a trabalhar como indexador. É o caso mais
     provável de todos, porque é precisamente assim que o produto quer
     que as pessoas troquem de chapéu.
  2. `document_portal_request` tinha uma CÓPIA INLINE da regra
     (`user.get("role") != "indexacao"`) — a conclusão certa pela metade:
     ignorava o interruptor `track_history=False`.
  3. `restore_api_document` não tinha guarda nenhuma.

  Os escritores em `admin_*` não são fuga: são endpoints de administração
  (`require_roles([ADMIN, CEO])`), onde um indexador nunca entra. E o
  `temp_link_api_public` grava com `created_by: None` — é o cliente, não
  um utilizador com perfil.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios


SERVICOS = Path(__file__).resolve().parents[2] / "services"


class TestQuemESilenciado:
    def test_papel_base_indexacao(self):
        from services.history import _is_stealth_user

        assert _is_stealth_user({"role": "indexacao"}) is True

    def test_interruptor_global_desligado(self):
        from services.history import _is_stealth_user

        assert _is_stealth_user({"role": "consultor", "track_history": False}) is True

    def test_consultor_normal_deixa_rasto(self):
        from services.history import _is_stealth_user

        assert _is_stealth_user({"role": "consultor"}) is False

    def test_PERFIL_ACTIVO_indexacao_tambem_e_silenciado(self):
        """O furo principal. Multi-perfil: o papel do JWT é `consultor`,
        mas a pessoa está a trabalhar COMO Indexação (`X-Active-Role`).
        Olhar só para o papel base deixa rasto de quem o produto promete
        manter invisível."""
        from services.history import _is_stealth_user

        assert _is_stealth_user(
            {"role": "consultor", "effective_role": "indexacao"}
        ) is True

    def test_perfil_activo_normal_nao_desfaz_o_silencio_do_papel_base(self):
        """Contraprova: quem é indexador de base continua silencioso
        mesmo com outro perfil activo — a regra ACRESCENTA, não substitui."""
        from services.history import _is_stealth_user

        assert _is_stealth_user(
            {"role": "indexacao", "effective_role": "consultor"}
        ) is True

    def test_sem_utilizador_nao_silencia(self):
        """Escritas do sistema (sem utilizador) não são acções de ninguém
        e continuam a registar-se."""
        from services.history import _is_stealth_user

        assert _is_stealth_user(None) is False
        assert _is_stealth_user({}) is False


class TestNinguemReconstroiARegra:
    def test_nenhum_servico_compara_o_papel_a_mao(self):
        """Uma cópia inline da regra é a conclusão certa pela metade:
        a de `document_portal_request` ignorava o `track_history=False`
        e não via o perfil activo. A regra sai de `_is_stealth_user`, ou
        não sai de lado nenhum."""
        infractores = []
        for ficheiro in SERVICOS.glob("*.py"):
            if ficheiro.name in ("history.py", "audit_cdc.py"):
                continue
            codigo = codigo_sem_comentarios(ficheiro.read_text("utf-8")).replace('"', "'")
            if "'indexacao'" in codigo and "history.insert_one" in codigo:
                if "_is_stealth_user" not in codigo:
                    infractores.append(ficheiro.name)
        assert not infractores, (
            f"{infractores} decidem o silêncio à mão em vez de perguntar a "
            "`history._is_stealth_user`"
        )

    @pytest.mark.parametrize(
        "modulo",
        ["document_portal_request.py", "restore_api_document.py", "voice_note_engine.py"],
    )
    def test_os_escritores_directos_perguntam_a_guarda(self, modulo):
        """Contraprova do teste acima: sem isto, apagar a chamada
        satisfazia o guarda e reabria a fuga."""
        fonte = (SERVICOS / modulo).read_text("utf-8")
        assert "_is_stealth_user" in fonte, f"{modulo} não consulta a guarda"


class TestHistoricoNaPratica:
    @pytest.mark.asyncio
    async def test_indexador_nao_escreve_no_historico(self, fake_async_db):
        import services.history as history

        with patch.object(history, "db", fake_async_db):
            await history.log_history("p-1", {"id": "u-1", "role": "indexacao"}, "Abriu")

        assert fake_async_db.history.docs == []

    @pytest.mark.asyncio
    async def test_perfil_activo_indexacao_nao_escreve_no_historico(self, fake_async_db):
        import services.history as history

        with patch.object(history, "db", fake_async_db):
            await history.log_history(
                "p-1",
                {"id": "u-1", "role": "consultor", "effective_role": "indexacao"},
                "Abriu",
            )

        assert fake_async_db.history.docs == []

    @pytest.mark.asyncio
    async def test_consultor_escreve_no_historico(self, fake_async_db):
        """Contraprova: silenciar toda a gente passaria nos testes acima."""
        import services.history as history

        with patch.object(history, "db", fake_async_db):
            await history.log_history(
                "p-1", {"id": "u-1", "name": "Ana", "role": "consultor"}, "Abriu",
            )

        assert len(fake_async_db.history.docs) == 1

    @pytest.mark.asyncio
    async def test_restaurar_documento_como_indexador_nao_deixa_rasto(self, fake_async_db):
        import services.restore_api_document as restore

        fake_async_db.documents.docs.append(
            {"id": "d-1", "process_id": "p-1", "filename": "CC.pdf", "deleted": True},
        )
        with patch.object(restore, "db", fake_async_db):
            await restore.run_restore_document(
                "d-1", {"id": "u-1", "name": "Indexador", "role": "indexacao"},
            )

        assert fake_async_db.history.docs == []

    @pytest.mark.asyncio
    async def test_restaurar_documento_como_consultor_deixa_rasto(self, fake_async_db):
        import services.restore_api_document as restore

        fake_async_db.documents.docs.append(
            {"id": "d-1", "process_id": "p-1", "filename": "CC.pdf", "deleted": True},
        )
        with patch.object(restore, "db", fake_async_db):
            await restore.run_restore_document(
                "d-1", {"id": "u-1", "name": "Ana", "role": "consultor"},
            )

        assert len(fake_async_db.history.docs) == 1


class TestAuditTrailNaoEIgual:
    def test_o_trilho_de_conformidade_fica_de_fora_de_propósito(self):
        """O `audit_trail_service` mantém rastreabilidade mesmo para o
        perfil silenciado: é conformidade, não o mural do processo.
        Silenciá-lo seria transformar uma funcionalidade de produto num
        buraco de auditoria."""
        fonte = (SERVICOS / "audit_trail_service.py").read_text("utf-8")
        assert "_is_stealth_user" not in fonte
