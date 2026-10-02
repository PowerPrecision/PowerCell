"""Email «Documentação Recebida»: lista de NOMES, sem anexos (Lote 2, ponto 2).

O QUE JÁ FUNCIONAVA
===================
O gatilho existia e estava ligado aos DOIS caminhos de upload
(`portal_upload_ops.run_confirm_portal_upload` para o cliente e
`document_portal_fulfill` para a equipa no CRM), era idempotente por
processo e já tinha o fallback de SMTP. Isso está aqui afirmado porque é
o que o guião de teste de produção exercita, e uma ligação que ninguém
afirma é uma ligação que se perde na próxima extracção.

O QUE FALTAVA
=============
O email confirmava "toda a documentação" **sem dizer qual**. Uma
confirmação que não enumera o que recebeu não serve de recibo: quem a lê
não consegue detectar que faltou uma peça, que é precisamente a razão de
se mandar a confirmação.

DUAS REGRAS QUE FICAM AFIRMADAS
===============================
1. **Os nomes vão no CORPO, os ficheiros NUNCA em anexo.** Reenviar ao
   cliente os documentos que ele acabou de submeter põe dados pessoais a
   circular por email sem necessidade — e o Portal é onde eles vivem.
   Sem teste, "juntar os anexos" é a melhoria óbvia que alguém faz a
   seguir.
2. **O nome do ficheiro é texto do CLIENTE.** Entra num corpo HTML, logo
   é conteúdo externo e leva escape. Um nome com `<` partia o email.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import portal_documents_notify as pdn  # noqa: E402
from services.document_portal_counts import COMPLETED_PORTAL_STATUSES  # noqa: E402
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios  # noqa: E402


def _pedido(**campos) -> dict:
    base = {"process_id": "p1", "status": "RECEIVED"}
    base.update(campos)
    return base


class TestONomeDeUmPedido:
    def test_prefere_o_que_foi_PEDIDO_ao_nome_do_ficheiro(self):
        """O email confirma o PEDIDO, não o upload: "Recibo de Vencimento"
        diz ao cliente o que ficou satisfeito; "scan_0012.pdf" não."""
        doc = _pedido(custom_label="Recibo de Vencimento", original_filename="scan_0012.pdf")
        assert pdn.nome_legivel_do_pedido(doc) == "Recibo de Vencimento"

    def test_cai_para_o_nome_do_ficheiro_quando_nao_ha_etiqueta(self):
        assert pdn.nome_legivel_do_pedido(_pedido(original_filename="irs2025.pdf")) == "irs2025.pdf"

    def test_cai_para_a_categoria_em_ultimo_recurso(self):
        assert pdn.nome_legivel_do_pedido(_pedido(category="financeiros")) == "financeiros"

    def test_um_pedido_sem_nome_nenhum_nao_vira_linha_em_branco(self):
        assert pdn.nome_legivel_do_pedido(_pedido()) == ""
        assert pdn.nome_legivel_do_pedido(None) == ""

    def test_a_ordem_de_preferencia_esta_declarada(self):
        """Contraprova de cobertura: a ordem É a regra, e sem isto um campo
        que caia da constante não acusa."""
        assert pdn.CAMPOS_DO_NOME_DO_PEDIDO[0] == "custom_label"
        assert "original_filename" in pdn.CAMPOS_DO_NOME_DO_PEDIDO


class TestAListaDosRecebidos:
    @pytest.mark.asyncio
    async def test_lista_os_documentos_concluidos(self, fake_async_db, monkeypatch):
        fake_async_db.documents.docs.extend([
            _pedido(custom_label="Cartão de Cidadão"),
            _pedido(custom_label="Recibo de Vencimento"),
        ])
        monkeypatch.setattr(pdn, "db", fake_async_db)
        assert await pdn.nomes_dos_documentos_recebidos("p1") == [
            "Cartão de Cidadão",
            "Recibo de Vencimento",
        ]

    @pytest.mark.asyncio
    async def test_um_pedido_AINDA_PENDENTE_nao_entra_na_lista(self, fake_async_db, monkeypatch):
        """Senão o recibo listava o que não chegou."""
        fake_async_db.documents.docs.extend([
            _pedido(custom_label="Recebido"),
            _pedido(custom_label="Em falta", status="REQUESTED"),
        ])
        monkeypatch.setattr(pdn, "db", fake_async_db)
        assert await pdn.nomes_dos_documentos_recebidos("p1") == ["Recebido"]

    @pytest.mark.asyncio
    async def test_os_documentos_de_OUTRO_processo_nao_entram(self, fake_async_db, monkeypatch):
        fake_async_db.documents.docs.extend([
            _pedido(custom_label="Meu"),
            _pedido(custom_label="Do vizinho", process_id="p2"),
        ])
        monkeypatch.setattr(pdn, "db", fake_async_db)
        assert await pdn.nomes_dos_documentos_recebidos("p1") == ["Meu"]

    @pytest.mark.asyncio
    async def test_diz_quantos_ficheiros_quando_sao_varios(self, fake_async_db, monkeypatch):
        """É por aqui que o cliente confirma a QUANTIDADE — "3 recibos"
        pedidos e 3 entregues."""
        fake_async_db.documents.docs.append(
            _pedido(custom_label="Recibos de Vencimento", attached_files=["a", "b", "c"])
        )
        monkeypatch.setattr(pdn, "db", fake_async_db)
        assert await pdn.nomes_dos_documentos_recebidos("p1") == [
            "Recibos de Vencimento (3 ficheiros)"
        ]

    @pytest.mark.asyncio
    async def test_um_so_ficheiro_nao_leva_contagem(self, fake_async_db, monkeypatch):
        fake_async_db.documents.docs.append(
            _pedido(custom_label="Cartão de Cidadão", attached_files=["a"])
        )
        monkeypatch.setattr(pdn, "db", fake_async_db)
        assert await pdn.nomes_dos_documentos_recebidos("p1") == ["Cartão de Cidadão"]

    @pytest.mark.asyncio
    async def test_uma_falha_de_leitura_nao_impede_o_email(self, monkeypatch):
        """Um email sem a lista é melhor do que email nenhum."""
        class DbQueRebenta:
            def __getattr__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(pdn, "db", DbQueRebenta())
        assert await pdn.nomes_dos_documentos_recebidos("p1") == []

    def test_os_estados_de_CONCLUIDO_vem_do_ponto_unico(self):
        """Uma segunda lista de estados escrita aqui divergiria desta na
        primeira vez que aparecesse um estado novo."""
        fonte = codigo_da_funcao_sem_comentarios(pdn.nomes_dos_documentos_recebidos)
        assert "COMPLETED_PORTAL_STATUSES" in fonte
        assert '"RECEIVED"' not in fonte and "'RECEIVED'" not in fonte
        # CONTRAPROVA: o ponto único traz mesmo o estado que interessa.
        assert "RECEIVED" in COMPLETED_PORTAL_STATUSES


class TestOsNomesAparecemNOSDoisCorpos:
    """Texto simples E HTML. Corrigir um e esquecer o outro é invisível —
    o cliente vê o HTML e o fallback de texto fica a mentir."""

    def test_o_HTML_leva_a_lista(self):
        corpo = pdn._build_documents_complete_html("Ana", ["Cartão de Cidadão", "IRS"])
        assert "Documentos recebidos:" in corpo
        assert "Cartão de Cidadão" in corpo
        assert "IRS" in corpo

    def test_sem_nomes_o_HTML_nao_desenha_caixa_vazia(self):
        """Um título com nada por baixo lê-se como avaria."""
        corpo = pdn._build_documents_complete_html("Ana", [])
        assert "Documentos recebidos:" not in corpo
        # Mas o email continua a existir e a dizer o que importa.
        assert "Ana" in corpo and "Análise de Crédito" in corpo

    def test_o_HTML_continua_a_funcionar_sem_o_argumento_novo(self):
        """Compatibilidade: a assinatura ganhou um parâmetro opcional."""
        assert "Ana" in pdn._build_documents_complete_html("Ana")

    def test_o_corpo_de_TEXTO_tambem_leva_a_lista(self):
        """Afirmado sobre a fonte da função de envio, que é quem o monta."""
        fonte = codigo_da_funcao_sem_comentarios(pdn.check_and_notify_documents_complete)
        assert "lista_em_texto" in fonte
        assert "nomes_dos_documentos_recebidos" in fonte


class TestOsNomesSaoCONTEUDOEXTERNO:
    """O nome do ficheiro é texto que o cliente escolheu."""

    def test_um_nome_com_HTML_e_escapado(self):
        corpo = pdn._build_documents_complete_html("Ana", ['<script>alert(1)</script>'])
        assert "<script>" not in corpo
        assert "&lt;script&gt;" in corpo

    def test_as_aspas_tambem(self):
        corpo = pdn._build_documents_complete_html("Ana", ['recibo "final".pdf'])
        assert "&quot;" in corpo


class TestNUNCAVaoAnexos:
    """Reenviar ao cliente os documentos que ele acabou de submeter põe
    dados pessoais a circular por email sem necessidade nenhuma. Sem este
    teste, "juntar os anexos" é a melhoria óbvia que alguém faz a seguir."""

    def test_o_envio_SMTP_nao_junta_anexos(self):
        fonte = codigo_da_funcao_sem_comentarios(pdn._send_via_smtp)
        assert "MIMEBase" not in fonte
        assert "add_attachment" not in fonte
        assert "attach_file" not in fonte
        assert "Content-Disposition" not in fonte

    def test_o_fallback_da_empresa_tambem_nao(self):
        fonte = codigo_da_funcao_sem_comentarios(pdn.check_and_notify_documents_complete)
        assert "attachments" not in fonte
        assert "attached_files" not in fonte

    def test_CONTRAPROVA_o_envio_leva_mesmo_os_dois_corpos(self):
        """Sem isto, "não leva anexos" passaria num envio que não leva nada."""
        fonte = codigo_da_funcao_sem_comentarios(pdn._send_via_smtp)
        assert "text_body" in fonte and "html_body" in fonte
        assert "alternative" in fonte


class TestOGatilhoContinuaLigadoAosDoisCaminhos:
    """O guião de teste de produção depende destas duas ligações."""

    def test_o_upload_do_CLIENTE_dispara(self):
        from services import portal_upload_ops
        fonte = Path(portal_upload_ops.__file__).read_text(encoding="utf-8")
        assert "check_and_notify_documents_complete" in fonte

    def test_o_upload_da_EQUIPA_no_CRM_dispara(self):
        from services import document_portal_fulfill
        fonte = Path(document_portal_fulfill.__file__).read_text(encoding="utf-8")
        assert "check_and_notify_documents_complete" in fonte

    def test_so_dispara_quando_NAO_ha_pendentes(self):
        """O "100%" do guião: um pedido obrigatório em falta tem de travar."""
        fonte = codigo_da_funcao_sem_comentarios(pdn.check_and_notify_documents_complete)
        assert "pending_count" in fonte
        assert "pending_documents" in fonte

    def test_os_OPCIONAIS_nao_travam(self):
        fonte = codigo_da_funcao_sem_comentarios(pdn.check_and_notify_documents_complete)
        assert "is_optional" in fonte

    def test_e_idempotente_por_processo(self):
        fonte = codigo_da_funcao_sem_comentarios(pdn.check_and_notify_documents_complete)
        assert "documents_complete_notified_at" in fonte
        assert "already_notified" in fonte
