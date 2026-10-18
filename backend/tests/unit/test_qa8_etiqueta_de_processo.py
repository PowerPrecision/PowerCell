"""QA-8 (1): a etiqueta `[Ref: #id]` liga o email ao processo certo (envio e sincronização).

Um cliente com vários processos: o endereço não distingue qual; a etiqueta no assunto, e as
cabeçalhos `In-Reply-To`/`References` contra o `Message-ID` do que o sistema enviou, sim.
"""
import pytest

from services.email_process_link import (
    assunto_tem_a_etiqueta,
    etiqueta_do_processo,
    extrair_id_da_etiqueta,
    processo_da_etiqueta,
    sem_etiquetas,
)


class TestEtiqueta:
    def test_o_formato_novo_e_o_legado_leem_se(self):
        assert extrair_id_da_etiqueta("Re: Documentos [Ref: #abc-123]") == "abc-123"
        assert extrair_id_da_etiqueta("Re: Documentos [Proc-abc-123]") == "abc-123"
        assert extrair_id_da_etiqueta("RE: x [ref:#abc-123]") == "abc-123"  # espaços e maiúsculas

    def test_sem_etiqueta_nao_liga_nada(self):
        assert extrair_id_da_etiqueta("Olá, sobre o crédito") is None
        assert extrair_id_da_etiqueta(None) is None
        assert extrair_id_da_etiqueta("[Ref: #]") is None

    def test_a_ida_e_a_volta(self):
        assert extrair_id_da_etiqueta(f"Assunto {etiqueta_do_processo('p-9')}") == "p-9"

    def test_nao_se_etiqueta_duas_vezes(self):
        assert assunto_tem_a_etiqueta("Re: x [Proc-p-9]", "p-9")
        assert assunto_tem_a_etiqueta("Re: x [Ref: #p-9]", "p-9")
        # contraprova: outra etiqueta NÃO conta como esta
        assert not assunto_tem_a_etiqueta("Re: x [Ref: #p-10]", "p-9")

    def test_sem_etiquetas_limpa_os_dois_formatos(self):
        assert sem_etiquetas("Docs [Ref: #a] [Proc-b] fim") == "Docs fim"

    @pytest.mark.asyncio
    async def test_so_liga_a_um_processo_que_existe(self, fake_async_db):
        fake_async_db.processes.docs.append({"id": "p-1"})
        assert await processo_da_etiqueta(fake_async_db, "x [Ref: #p-1]") == "p-1"
        # uma etiqueta inventada não liga a nada
        assert await processo_da_etiqueta(fake_async_db, "x [Ref: #nao-existe]") is None


class TestEnvio:
    @pytest.mark.asyncio
    async def test_o_assunto_sai_com_a_etiqueta_e_a_relacao_fica_guardada(self):
        import services.email_service as mod
        from pathlib import Path
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(Path(mod.__file__).read_text())
        assert "etiqueta_do_processo(process_id)" in fonte
        assert "'process_id': ligado_ao_processo" in fonte
        # e o formato antigo já não é ESCRITO por ninguém
        assert "f'[Proc-{process_id}]'" not in fonte


class TestSincronizacao:
    def test_os_quatro_sincronizadores_usam_o_ponto_unico(self):
        from pathlib import Path

        import services.email_service as mod
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(Path(mod.__file__).read_text())
        assert fonte.count("processo_da_etiqueta(db,") == 4
        # nenhum sincronizador lê a etiqueta com uma expressão regular própria
        assert "re.search('\\\\[Proc-" not in fonte
