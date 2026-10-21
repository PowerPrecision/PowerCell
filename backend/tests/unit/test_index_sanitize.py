"""PDF limpo e purga dos originais do Index (Lote 12, Fase 5).

O que se afirma, e porquê:
  · **Um PDF por documento distinto** (decisão da direcção): recibos nunca se juntam; extratos só
    quando são FOTOS do mesmo IBAN e mês; identificação só com UMA frente e UM verso; PDFs nunca.
  · **O PDF limpo está mesmo limpo**: sem metadados, XMP, anexos, JavaScript nem EXIF — medido
    procurando as cadeias sentinela nos bytes, não perguntando à função que os limpa.
  · **Nada muda de estado antes da verificação** (gravar → reler → comparar) e uma falha deixa os
    originais intactos e um alerta `sanitizacao_falhou`.
  · **A purga só apaga com a cópia limpa CONFIRMADA outra vez**, só depois da graça (30 dias) e só
    com o interruptor ligado (desligado por omissão, mesmo em produção).
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import index_sanitize as sz
from services import index_store as st
from services import process_ai_log as ailog

AGORA = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
PID = "proc-1"
PASTA = "Documentação Clientes/c-1/Index"
IBAN = "PT50000201231234567890154"


# ====================================================================
# fixtures de ficheiros reais (sentinelas dentro dos bytes)
# ====================================================================
def pdf_sujo(texto="Recibo", paginas=1) -> bytes:
    import fitz

    d = fitz.open()
    for i in range(paginas):
        d.new_page().insert_text((72, 72), f"{texto} {i}")
    d.set_metadata({"author": "SEGREDO_AUTOR", "title": "SEGREDO_TITULO", "producer": "SEGREDO_SCANNER",
                    "creator": "SEGREDO_CREATOR", "keywords": "SEGREDO_KEYWORDS"})
    d.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
                       "<rdf:Description rdf:about='' xmlns:dc='http://purl.org/dc/elements/1.1/'>"
                       "<dc:creator>SEGREDO_XMP</dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>")
    d.embfile_add("anexo.txt", b"SEGREDO_ANEXO")
    d.xref_set_key(d.pdf_catalog(), "OpenAction", "<</S/JavaScript/JS(app.alert\\(1\\))>>")
    return d.tobytes()


def jpeg_com_exif(cor="white") -> bytes:
    from PIL import Image

    imagem = Image.new("RGB", (120, 180), cor)
    exif = Image.Exif()
    exif[0x010F] = "SEGREDO_CAMARA"
    exif[0x013B] = "SEGREDO_AUTOR_EXIF"
    saida = io.BytesIO()
    imagem.save(saida, "JPEG", exif=exif)
    return saida.getvalue()


SENTINELAS = [b"SEGREDO_"]


def tem_sentinela(conteudo: bytes) -> bool:
    return any(s in conteudo for s in SENTINELAS)


def doc(id_, nome, *, categoria=None, sub=None, facts=None, subtype=None, criado="2026-10-01T10:00:00", **extra):
    return {"id": id_, "process_id": PID, "filename": nome, "s3_path": f"{PASTA}/{nome}", "ai_category": categoria,
            "ai_subcategory": sub, "ai_subtype": subtype, "index_facts": facts, "created_at": criado,
            "uploaded_by_index": True, **extra}


def extrato(id_, nome, iban=IBAN, inicio="2026-09-01", criado="2026-10-01T10:00:00"):
    return doc(id_, nome, categoria="Bancários", sub="Extrato Bancário", criado=criado,
               facts={"tipo": "extrato_bancario", "iban": iban, "period_start": inicio})


def identificacao(id_, nome, face, subtype="cc", criado="2026-10-01T10:00:00"):
    return doc(id_, nome, categoria="Identificação", sub="Cartão de Cidadão", subtype=subtype, criado=criado,
               facts={"tipo": "identificacao", "subtype": subtype, "face": face})


def recibo(id_, nome, criado="2026-10-01T10:00:00"):
    return doc(id_, nome, categoria="Rendimentos", sub="Recibo de Vencimento", criado=criado,
               facts={"tipo": "recibo_vencimento", "employer_nif": "501964843", "period": "2026-09"})


def ids(grupos):
    return [[d["id"] for d in g] for g in grupos]


# ====================================================================
# 1. AGRUPAR
# ====================================================================
class TestAgrupar:
    def test_o_tipo_decide_nao_so_a_chave_um_recibo_com_dados_de_extrato_nao_se_junta(self):
        """Mutação: se o agrupamento por extrato aceitasse recibos, duas fotos com os mesmos factos fundiam."""
        r1, r2 = recibo("r1", "a.jpg"), recibo("r2", "b.jpg")
        for r in (r1, r2):
            r["index_facts"].update({"iban": IBAN, "period_start": "2026-09-01"})
        assert ids(sz.agrupar_em_documentos([r1, r2])) == [["r1"], ["r2"]]

    def test_o_leitor_ve_fusoes(self):
        """Contraprova: se este leitor não fundisse nada, todas as asserções de «não junta» passavam."""
        grupos = sz.agrupar_em_documentos([extrato("e1", "p1.jpg"), extrato("e2", "p2.jpg")])
        assert ids(grupos) == [["e1", "e2"]]

    def test_recibos_nunca_se_juntam_mesmo_sendo_do_mesmo_mes_e_entidade(self):
        docs = [recibo("r1", "r1.jpg"), recibo("r2", "r2.jpg"), recibo("r3", "r3.pdf")]
        assert ids(sz.agrupar_em_documentos(docs)) == [["r1"], ["r2"], ["r3"]]

    def test_recibos_de_meses_diferentes_ficam_separados(self):
        docs = [recibo("r1", "set.pdf", "2026-10-01T10:00:00"), recibo("r2", "ago.pdf", "2026-10-02T10:00:00")]
        assert len(sz.agrupar_em_documentos(docs)) == 2

    def test_tres_fotos_do_mesmo_extrato_juntam_se_numa_so_ordem_de_carregamento(self):
        docs = [extrato("e3", "c.jpg", criado="2026-10-01T10:03:00"), extrato("e1", "a.jpg", criado="2026-10-01T10:01:00"),
                extrato("e2", "b.jpg", criado="2026-10-01T10:02:00")]
        assert ids(sz.agrupar_em_documentos(docs)) == [["e1", "e2", "e3"]]

    def test_extratos_de_meses_diferentes_nao_se_juntam(self):
        docs = [extrato("e1", "a.jpg", inicio="2026-08-01"), extrato("e2", "b.jpg", inicio="2026-09-01")]
        assert len(sz.agrupar_em_documentos(docs)) == 2

    def test_extratos_de_contas_diferentes_nao_se_juntam(self):
        docs = [extrato("e1", "a.jpg", iban=IBAN), extrato("e2", "b.jpg", iban="PT50000700000000000000000")]
        assert len(sz.agrupar_em_documentos(docs)) == 2

    def test_um_extrato_sem_iban_ou_sem_periodo_fica_sozinho(self):
        sem_iban = extrato("e1", "a.jpg", iban="")
        sem_periodo = extrato("e2", "b.jpg", inicio="")
        sem_periodo["index_facts"]["period_start"] = None
        assert ids(sz.agrupar_em_documentos([sem_iban, sem_periodo])) == [["e1"], ["e2"]]

    def test_extratos_em_pdf_nunca_se_juntam(self):
        docs = [extrato("e1", "a.pdf"), extrato("e2", "b.pdf")]
        assert ids(sz.agrupar_em_documentos(docs)) == [["e1"], ["e2"]]

    def test_uma_foto_e_um_pdf_do_mesmo_extrato_nao_se_juntam(self):
        docs = [extrato("e1", "a.jpg"), extrato("e2", "b.pdf")]
        assert len(sz.agrupar_em_documentos(docs)) == 2

    def test_frente_e_verso_do_cartao_de_cidadao_juntam_se(self):
        docs = [identificacao("i1", "f.jpg", "frente"), identificacao("i2", "v.jpg", "verso")]
        assert ids(sz.agrupar_em_documentos(docs)) == [["i1", "i2"]]

    def test_duas_pessoas_duas_frentes_dois_versos_nao_se_juntam(self):
        docs = [identificacao("i1", "a_f.jpg", "frente"), identificacao("i2", "a_v.jpg", "verso"),
                identificacao("i3", "b_f.jpg", "frente"), identificacao("i4", "b_v.jpg", "verso")]
        assert ids(sz.agrupar_em_documentos(docs)) == [["i1"], ["i2"], ["i3"], ["i4"]]

    def test_duas_frentes_nao_se_juntam(self):
        docs = [identificacao("i1", "a.jpg", "frente"), identificacao("i2", "b.jpg", "frente")]
        assert len(sz.agrupar_em_documentos(docs)) == 2

    def test_face_desconhecida_ou_ambas_nao_junta(self):
        docs = [identificacao("i1", "a.jpg", None), identificacao("i2", "b.jpg", "verso")]
        assert len(sz.agrupar_em_documentos(docs)) == 2
        docs = [identificacao("i1", "a.jpg", "ambas"), identificacao("i2", "b.jpg", "verso")]
        assert len(sz.agrupar_em_documentos(docs)) == 2

    def test_tipos_de_identificacao_diferentes_nao_se_juntam(self):
        docs = [identificacao("i1", "a.jpg", "frente", subtype="cc"), identificacao("i2", "b.jpg", "verso", subtype="bi")]
        assert len(sz.agrupar_em_documentos(docs)) == 2

    def test_pdfs_de_identificacao_nunca_se_juntam(self):
        docs = [identificacao("i1", "a.pdf", "frente"), identificacao("i2", "b.pdf", "verso")]
        assert len(sz.agrupar_em_documentos(docs)) == 2

    def test_documentos_de_tipo_desconhecido_ficam_sozinhos(self):
        docs = [doc("x1", "foto1.jpg"), doc("x2", "foto2.jpg")]
        assert ids(sz.agrupar_em_documentos(docs)) == [["x1"], ["x2"]]

    def test_e_deterministico_e_nao_altera_a_entrada(self):
        docs = [extrato("e2", "b.jpg", criado="2026-10-01T10:02:00"), recibo("r1", "r.pdf"),
                extrato("e1", "a.jpg", criado="2026-10-01T10:01:00")]
        copia = [dict(d) for d in docs]
        assert ids(sz.agrupar_em_documentos(docs)) == ids(sz.agrupar_em_documentos(list(reversed(docs))))
        assert docs == copia

    def test_todos_os_ficheiros_aparecem_exactamente_uma_vez(self):
        docs = [extrato("e1", "a.jpg"), extrato("e2", "b.jpg"), recibo("r1", "r.pdf"),
                identificacao("i1", "f.jpg", "frente"), identificacao("i2", "v.jpg", "verso"), doc("x", "z.jpg")]
        achatado = sorted(d["id"] for g in sz.agrupar_em_documentos(docs) for d in g)
        assert achatado == sorted(d["id"] for d in docs)


class TestNomes:
    def test_individual_usa_o_nome_do_proprio_ficheiro(self):
        assert sz.nome_do_pdf_limpo([recibo("r1", "Recibo Setembro (final).pdf")]) == "Recibo_Setembro_final_limpo.pdf"

    def test_extrato_fundido_leva_o_mes(self):
        g = [extrato("e1", "a.jpg", inicio="2026-01-01"), extrato("e2", "b.jpg", inicio="2026-01-01")]
        assert sz.nome_do_pdf_limpo(g) == "extrato_bancario_2026-01_limpo.pdf"

    def test_identificacao_fundida_leva_o_tipo(self):
        g = [identificacao("i1", "f.jpg", "frente"), identificacao("i2", "v.jpg", "verso")]
        assert sz.nome_do_pdf_limpo(g) == "identificacao_cc_limpo.pdf"

    def test_nome_sem_caracteres_perigosos(self):
        nome = sz.nome_do_pdf_limpo([doc("x", "../../etc/passwd ação.jpg")])
        assert "/" not in nome and ".." not in nome and nome.endswith("_limpo.pdf")


# ====================================================================
# 2. CONSTRUIR E VERIFICAR O PDF LIMPO (ficheiros reais)
# ====================================================================
class TestConstruirPdfLimpo:
    def test_o_fixture_esta_mesmo_sujo(self):
        sujo = pdf_sujo()
        assert tem_sentinela(sujo)
        assert sz.verificar_pdf_limpo(sujo, 1)[0] is False

    def test_um_pdf_sai_sem_metadados_xmp_anexos_nem_javascript(self):
        limpo, paginas = sz.construir_pdf_limpo([("r.pdf", pdf_sujo())])
        assert paginas == 1
        assert not tem_sentinela(limpo)
        assert b"JavaScript" not in limpo and b"OpenAction" not in limpo
        assert sz.verificar_pdf_limpo(limpo, 1) == (True, None)

    def test_o_autor_das_anotacoes_sai_e_o_texto_visivel_fica(self):
        """MEDIDO: o autor de um realce/comentário sobrevivia ao `scrub` e à cópia de páginas."""
        import fitz

        d = fitz.open()
        p = d.new_page()
        p.insert_text((72, 72), "Linha")
        nota = p.add_text_annot((100, 100), "n")
        nota.set_info(title="SEGREDO_STICKY", content="SEGREDO_NOTA")
        nota.update()
        livre = p.add_freetext_annot(fitz.Rect(50, 200, 200, 250), "texto livre visivel")
        livre.set_info(title="SEGREDO_FT", subject="SEGREDO_SUBJ")
        livre.update()
        realce = p.add_highlight_annot(fitz.Rect(72, 60, 100, 80))
        realce.set_info(title="SEGREDO_HL")
        realce.update()
        sujo = d.tobytes()
        assert sz.verificar_pdf_limpo(sujo, 1)[0] is False
        limpo, _ = sz.construir_pdf_limpo([("r.pdf", sujo)])
        assert not tem_sentinela(limpo)
        assert sz.verificar_pdf_limpo(limpo, 1) == (True, None)
        aberto = fitz.open(stream=limpo, filetype="pdf")[0]
        assert "texto livre visivel" in aberto.get_text()
        assert sorted(a.type[1] for a in aberto.annots()) == ["FreeText", "Highlight"]  # a nota adesiva saiu

    def test_o_conteudo_visivel_mantem_se(self):
        import fitz

        limpo, _ = sz.construir_pdf_limpo([("r.pdf", pdf_sujo("Salario liquido"))])
        assert "Salario liquido" in fitz.open(stream=limpo, filetype="pdf")[0].get_text()

    def test_varias_paginas_mantem_o_numero(self):
        limpo, paginas = sz.construir_pdf_limpo([("r.pdf", pdf_sujo(paginas=3))])
        assert paginas == 3 and sz.verificar_pdf_limpo(limpo, 3)[0]

    def test_a_imagem_perde_o_exif_na_cara(self):
        original = jpeg_com_exif()
        assert tem_sentinela(original)
        limpo, paginas = sz.construir_pdf_limpo([("f.jpg", original)])
        assert paginas == 1 and not tem_sentinela(limpo)
        assert sz.verificar_pdf_limpo(limpo, 1)[0]

    def test_varias_imagens_viram_varias_paginas_numa_ordem(self):
        limpo, paginas = sz.construir_pdf_limpo([("a.jpg", jpeg_com_exif()), ("b.png", self._png()), ("c.jpg", jpeg_com_exif("red"))])
        assert paginas == 3 and sz.verificar_pdf_limpo(limpo, 3)[0] and not tem_sentinela(limpo)

    @staticmethod
    def _png():
        from PIL import Image

        saida = io.BytesIO()
        Image.new("RGB", (50, 50), "blue").save(saida, "PNG")
        return saida.getvalue()

    def test_nunca_mistura_um_pdf_com_imagens(self):
        with pytest.raises(sz.ConversaoImpossivel):
            sz.construir_pdf_limpo([("a.pdf", pdf_sujo()), ("b.jpg", jpeg_com_exif())])

    @pytest.mark.parametrize("lixo", [b"", b"nao e um pdf", b"%PDF-1.4 truncado"])
    def test_pdf_corrompido_e_recusado(self, lixo):
        with pytest.raises(sz.ConversaoImpossivel):
            sz.construir_pdf_limpo([("x.pdf", lixo)])

    def test_imagem_corrompida_e_recusada(self):
        with pytest.raises(sz.ConversaoImpossivel):
            sz.construir_pdf_limpo([("x.jpg", b"isto nao e uma imagem")])

    def test_pdf_com_palavra_passe_e_recusado(self):
        import fitz

        d = fitz.open()
        d.new_page()
        protegido = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="a", owner_pw="b")
        with pytest.raises(sz.ConversaoImpossivel):
            sz.construir_pdf_limpo([("x.pdf", protegido)])

    def test_sem_ficheiros_e_recusado(self):
        with pytest.raises(sz.ConversaoImpossivel):
            sz.construir_pdf_limpo([])


class TestVerificarPdfLimpo:
    def test_recusa_paginas_a_menos_ou_a_mais(self):
        limpo, _ = sz.construir_pdf_limpo([("r.pdf", pdf_sujo(paginas=2))])
        assert sz.verificar_pdf_limpo(limpo, 2)[0]
        assert not sz.verificar_pdf_limpo(limpo, 3)[0]
        assert not sz.verificar_pdf_limpo(limpo, 1)[0]
        assert not sz.verificar_pdf_limpo(limpo, 0)[0]

    @pytest.mark.parametrize("lixo", [b"", None, b"abc", b"%PDF-"])
    def test_recusa_lixo(self, lixo):
        assert sz.verificar_pdf_limpo(lixo, 1)[0] is False

    def test_recusa_javascript_mesmo_sem_metadados(self):
        import fitz

        d = fitz.open()
        d.new_page()
        d.xref_set_key(d.pdf_catalog(), "OpenAction", "<</S/JavaScript/JS(app.alert\\(1\\))>>")
        ok, motivo = sz.verificar_pdf_limpo(d.tobytes(), 1)
        assert ok is False and "JavaScript" in motivo

    def test_recusa_anexos_embebidos(self):
        import fitz

        d = fitz.open()
        d.new_page()
        d.embfile_add("a.txt", b"x")
        assert sz.verificar_pdf_limpo(d.tobytes(), 1)[0] is False

    def test_recusa_anotacoes_com_autor(self):
        import fitz

        d = fitz.open()
        p = d.new_page()
        a = p.add_highlight_annot(fitz.Rect(10, 10, 50, 30))
        a.set_info(title="Ana Silva")
        a.update()
        ok, motivo = sz.verificar_pdf_limpo(d.tobytes(), 1)
        assert ok is False and "autor" in motivo

    def test_recusa_notas_adesivas(self):
        import fitz

        d = fitz.open()
        d.new_page().add_text_annot((50, 50), "nota")
        assert sz.verificar_pdf_limpo(d.tobytes(), 1)[0] is False

    def test_recusa_xmp(self):
        import fitz

        d = fitz.open()
        d.new_page()
        d.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'></x:xmpmeta>")
        assert sz.verificar_pdf_limpo(d.tobytes(), 1)[0] is False


# ====================================================================
# 3. INTERRUPTORES
# ====================================================================
class TestInterruptores:
    def test_a_graca_por_omissao_e_30_dias(self, monkeypatch):
        monkeypatch.delenv("INDEX_PURGE_GRACE_DAYS", raising=False)
        assert sz.graca_em_dias() == 30

    @pytest.mark.parametrize("valor", ["0", "-5", "abc", "", "7.5"])
    def test_valor_invalido_nunca_encurta_a_graca(self, monkeypatch, valor):
        monkeypatch.setenv("INDEX_PURGE_GRACE_DAYS", valor)
        assert sz.graca_em_dias() == 30

    def test_um_valor_valido_vale(self, monkeypatch):
        monkeypatch.setenv("INDEX_PURGE_GRACE_DAYS", "45")
        assert sz.graca_em_dias() == 45

    def test_a_purga_esta_desligada_por_omissao_mesmo_em_producao(self, monkeypatch):
        monkeypatch.delenv("INDEX_PURGE_ENABLED", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("TESTING", raising=False)
        assert sz.purga_ligada() is False

    @pytest.mark.parametrize("valor,esperado", [("true", True), ("1", True), ("false", False), ("", False), ("talvez", False)])
    def test_a_purga_so_liga_com_pedido_explicito(self, monkeypatch, valor, esperado):
        monkeypatch.setenv("INDEX_PURGE_ENABLED", valor)
        assert sz.purga_ligada() is esperado

    def test_a_sanitizacao_automatica_liga_por_omissao_fora_de_testes(self, monkeypatch):
        monkeypatch.delenv("INDEX_SANITIZE_ENABLED", raising=False)
        monkeypatch.setenv("TESTING", "false")
        assert sz.sanitizacao_automatica_ligada() is True
        monkeypatch.setenv("TESTING", "true")
        assert sz.sanitizacao_automatica_ligada() is False
        monkeypatch.setenv("INDEX_SANITIZE_ENABLED", "false")
        monkeypatch.setenv("TESTING", "false")
        assert sz.sanitizacao_automatica_ligada() is False


# ====================================================================
# 4. SANITIZAR UM PROCESSO (com um S3 falso e a base de dados falsa)
# ====================================================================
class S3Falso:
    """Armazenamento em memória com a MESMA interface de estado de quatro valores das primitivas reais."""

    def __init__(self):
        self.objectos: dict[str, bytes] = {}
        self.head_erro = False
        self.put_falha = False
        self.corromper_leitura = False
        self.leitura_erro = False
        self.apagados: list[str] = []
        self.apagar_falha = False

    def head_object_metadata(self, chave):
        if self.head_erro:
            return "erro", None
        return ("ok", {"tamanho": len(self.objectos[chave])}) if chave in self.objectos else ("ausente", None)

    def put_object_exact(self, chave, dados, content_type="application/pdf"):
        if self.put_falha:
            return False
        self.objectos[chave] = bytes(dados)
        return True

    def get_object_exact(self, chave, max_bytes):
        if self.leitura_erro:
            return "erro", None
        if chave not in self.objectos:
            return "ausente", None
        dados = self.objectos[chave]
        return "ok", (dados + b"\x00corrompido" if self.corromper_leitura else dados)

    def delete_file(self, chave):
        if self.apagar_falha:
            return False
        self.apagados.append(chave)
        return self.objectos.pop(chave, None) is not None or True


@pytest.fixture
def s3():
    falso = S3Falso()
    with patch.object(sz, "s3_service", falso):
        yield falso


@pytest.fixture
def ctx(fake_async_db, s3):
    """Base de dados falsa em todos os módulos que tocam nela + leitura do S3 falso."""
    from services import index_release

    # cada módulo importou `db` para si (a armadilha da ordem de import): patcha-se um a um
    patches = [patch.object(m, "db", fake_async_db) for m in (sz, st, ailog, index_release)]
    patches.append(patch("database.db", fake_async_db))
    from services import index_status as ist

    patches.append(patch.object(ist, "db", fake_async_db))
    for p in patches:
        p.start()

    async def ler(caminho):
        if caminho not in s3.objectos:
            return None, "ilegivel"
        return s3.objectos[caminho], None

    class C:
        db = fake_async_db
        fake_s3 = s3
        ler_ficheiro = staticmethod(ler)

        async def semear(self, docs, ficheiros):
            await fake_async_db.processes.insert_one({"id": PID, "network_id": "rede-A", "is_deleted": False})
            for d in docs:
                await fake_async_db.document_metadata.insert_one(dict(d))
            s3.objectos.update(ficheiros)

        async def correr(self, **k):
            return await sz.sanitizar_processo(PID, {"id": "u-idx", "role": "indexacao"}, agora=AGORA,
                                               ler_ficheiro=self.ler_ficheiro, **k)

        async def doc(self, id_):
            return await fake_async_db.document_metadata.find_one({"id": id_})

    yield C()
    for p in reversed(patches):
        p.stop()


def caminho(nome):
    return f"{PASTA}/{nome}"


class TestSanitizarUmProcesso:
    @pytest.mark.asyncio
    async def test_um_recibo_em_pdf_gera_um_pdf_limpo_ao_lado_do_original(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        r = await ctx.correr()
        assert r == {"candidatos": 1, "grupos": 1, "sanitizados": 1, "falhas": 0}
        limpo = caminho("recibo_limpo.pdf")
        assert limpo in ctx.fake_s3.objectos
        assert not tem_sentinela(ctx.fake_s3.objectos[limpo])
        # o original NÃO foi tocado
        assert tem_sentinela(ctx.fake_s3.objectos[caminho("recibo.pdf")])
        assert ctx.fake_s3.apagados == []

    @pytest.mark.asyncio
    async def test_o_original_fica_sanitizado_com_a_graca_de_30_dias(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        await ctx.correr()
        original = await ctx.doc("r1")
        assert original["file_state"] == "sanitizado"
        assert original["clean_pdf_path"] == caminho("recibo_limpo.pdf")
        assert original["clean_pdf_sha256"] == hashlib.sha256(ctx.fake_s3.objectos[caminho("recibo_limpo.pdf")]).hexdigest()
        assert original["purge_after"] == (AGORA + timedelta(days=30)).isoformat()
        assert original["s3_path"] == caminho("recibo.pdf")  # nada se repontou ainda

    @pytest.mark.asyncio
    async def test_o_pdf_limpo_tem_registo_proprio_que_nao_se_analisa(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        await ctx.correr()
        limpos = await ctx.db.document_metadata.find({"is_clean_pdf": True}).to_list(None)
        assert len(limpos) == 1
        assert limpos[0]["clean_of"] == ["r1"] and limpos[0]["uploaded_by_index"] is False
        assert limpos[0]["ai_category"] == "Rendimentos"
        assert limpos[0]["s3_path"] == caminho("recibo_limpo.pdf")

    @pytest.mark.asyncio
    async def test_so_o_que_o_index_carregou(self, ctx):
        do_cliente = recibo("r2", "do_cliente.pdf")
        do_cliente["uploaded_by_index"] = False
        sem_marca = recibo("r3", "sem_marca.pdf")
        del sem_marca["uploaded_by_index"]
        await ctx.semear([recibo("r1", "do_index.pdf"), do_cliente, sem_marca],
                         {caminho(n): pdf_sujo() for n in ("do_index.pdf", "do_cliente.pdf", "sem_marca.pdf")})
        r = await ctx.correr()
        assert r["candidatos"] == 1
        assert (await ctx.doc("r2")).get("file_state") is None and (await ctx.doc("r3")).get("file_state") is None

    @pytest.mark.asyncio
    async def test_so_formatos_que_se_convertem(self, ctx):
        await ctx.semear([doc("d1", "carta.docx", categoria="Outros"), recibo("r1", "r.pdf")],
                         {caminho("carta.docx"): b"x", caminho("r.pdf"): pdf_sujo()})
        assert (await ctx.correr())["candidatos"] == 1

    @pytest.mark.asyncio
    async def test_tres_fotos_do_mesmo_extrato_dao_um_so_pdf_de_tres_paginas(self, ctx):
        fotos = [extrato(f"e{i}", f"p{i}.jpg", criado=f"2026-10-01T10:0{i}:00") for i in (1, 2, 3)]
        await ctx.semear(fotos, {caminho(f"p{i}.jpg"): jpeg_com_exif() for i in (1, 2, 3)})
        r = await ctx.correr()
        assert r["grupos"] == 1 and r["sanitizados"] == 3
        limpo = caminho("extrato_bancario_2026-09_limpo.pdf")
        assert sz.verificar_pdf_limpo(ctx.fake_s3.objectos[limpo], 3)[0]
        for i in (1, 2, 3):
            assert (await ctx.doc(f"e{i}"))["clean_pdf_path"] == limpo
        assert len(await ctx.db.document_metadata.find({"is_clean_pdf": True}).to_list(None)) == 1

    @pytest.mark.asyncio
    async def test_dois_recibos_dao_dois_pdfs_e_nunca_um_recibos_pdf(self, ctx):
        await ctx.semear([recibo("r1", "set.jpg"), recibo("r2", "out.jpg")],
                         {caminho("set.jpg"): jpeg_com_exif(), caminho("out.jpg"): jpeg_com_exif("red")})
        await ctx.correr()
        novos = sorted(k for k in ctx.fake_s3.objectos if k.endswith("_limpo.pdf"))
        assert novos == [caminho("out_limpo.pdf"), caminho("set_limpo.pdf")]

    @pytest.mark.asyncio
    async def test_frente_e_verso_dao_um_pdf_de_duas_paginas(self, ctx):
        await ctx.semear([identificacao("i1", "f.jpg", "frente"), identificacao("i2", "v.jpg", "verso")],
                         {caminho("f.jpg"): jpeg_com_exif(), caminho("v.jpg"): jpeg_com_exif("gray")})
        await ctx.correr()
        assert sz.verificar_pdf_limpo(ctx.fake_s3.objectos[caminho("identificacao_cc_limpo.pdf")], 2)[0]

    @pytest.mark.asyncio
    async def test_e_idempotente(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        await ctx.correr()
        segunda = await ctx.correr()
        assert segunda["candidatos"] == 0
        assert len([k for k in ctx.fake_s3.objectos if k.endswith("_limpo.pdf")]) == 1

    @pytest.mark.asyncio
    async def test_nunca_sobrescreve_um_nome_que_ja_existe(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")],
                         {caminho("recibo.pdf"): pdf_sujo(), caminho("recibo_limpo.pdf"): b"de outro documento"})
        await ctx.correr()
        assert ctx.fake_s3.objectos[caminho("recibo_limpo.pdf")] == b"de outro documento"
        assert (await ctx.doc("r1"))["clean_pdf_path"] == caminho("recibo_limpo_2.pdf")

    @pytest.mark.asyncio
    async def test_um_processo_inexistente_ou_eliminado_nao_faz_nada(self, ctx):
        r = await sz.sanitizar_processo("nao-existe", None, agora=AGORA, ler_ficheiro=ctx.ler_ficheiro)
        assert r["candidatos"] == 0


class TestAVerificacaoAntesDeGravar:
    @pytest.mark.asyncio
    async def test_um_pdf_que_a_conversao_deixou_sujo_nem_se_grava(self, ctx):
        """Se a conversão falhasse a limpar, a verificação é a última barreira ANTES de gravar."""
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        with patch.object(sz, "construir_pdf_limpo", return_value=(pdf_sujo(), 1)):
            r = await ctx.correr()
        assert r["falhas"] == 1 and r["sanitizados"] == 0
        assert caminho("recibo_limpo.pdf") not in ctx.fake_s3.objectos
        assert (await ctx.doc("r1")).get("file_state") in (None, "original")
        linhas = await ctx.db.process_ai_log.find({"accao": "sanitizar"}).to_list(None)
        assert linhas[0]["motivo"] == "pdf_limpo_invalido"


class TestSanitizarFalhaSemEstragar:
    """Em CADA falha: os originais ficam intactos, nada muda de estado, e há um alerta."""

    async def _intacto(self, ctx, id_="r1"):
        d = await ctx.doc(id_)
        assert d.get("file_state") in (None, "original")
        assert not d.get("clean_pdf_path") and not d.get("purge_after")
        assert await ctx.db.document_metadata.find_one({"is_clean_pdf": True}) is None
        assert ctx.fake_s3.apagados == [] or all(not a.endswith(".pdf") or "_limpo" in a for a in ctx.fake_s3.apagados)

    async def _alerta(self, ctx):
        alertas = await ctx.db.process_index_alerts.find({"process_id": PID}).to_list(None)
        assert [a["code"] for a in alertas] == ["sanitizacao_falhou"]
        assert alertas[0]["severity"] == "aviso"

    @pytest.mark.asyncio
    async def test_a_leitura_de_volta_diferente_apaga_a_copia_e_nao_muda_nada(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        ctx.fake_s3.corromper_leitura = True
        r = await ctx.correr()
        assert r["sanitizados"] == 0 and r["falhas"] == 1
        await self._intacto(ctx)
        await self._alerta(ctx)
        assert caminho("recibo_limpo.pdf") not in ctx.fake_s3.objectos  # a cópia má não fica
        assert tem_sentinela(ctx.fake_s3.objectos[caminho("recibo.pdf")])

    @pytest.mark.asyncio
    async def test_a_gravacao_a_falhar(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        ctx.fake_s3.put_falha = True
        assert (await ctx.correr())["falhas"] == 1
        await self._intacto(ctx)
        await self._alerta(ctx)

    @pytest.mark.asyncio
    async def test_o_armazenamento_a_nao_responder_a_escolha_do_nome(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        ctx.fake_s3.head_erro = True
        assert (await ctx.correr())["falhas"] == 1
        await self._intacto(ctx)

    @pytest.mark.asyncio
    async def test_a_leitura_de_volta_a_dar_erro(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        ctx.fake_s3.leitura_erro = True
        assert (await ctx.correr())["falhas"] == 1
        await self._intacto(ctx)

    @pytest.mark.asyncio
    async def test_um_pdf_corrompido_fica_e_nao_impede_os_outros(self, ctx):
        await ctx.semear([recibo("r1", "mau.pdf"), recibo("r2", "bom.pdf", criado="2026-10-01T11:00:00")],
                         {caminho("mau.pdf"): b"%PDF-1.4 truncado", caminho("bom.pdf"): pdf_sujo()})
        r = await ctx.correr()
        assert r["sanitizados"] == 1 and r["falhas"] == 1
        assert (await ctx.doc("r2"))["file_state"] == "sanitizado"
        assert (await ctx.doc("r1")).get("file_state") in (None, "original")

    @pytest.mark.asyncio
    async def test_um_original_que_nao_se_le_fica(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {})  # o S3 não o tem
        assert (await ctx.correr())["falhas"] == 1
        await self._intacto(ctx)

    @pytest.mark.asyncio
    async def test_a_falha_fica_no_log_da_ia_com_um_codigo_nunca_com_texto(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        ctx.fake_s3.put_falha = True
        await ctx.correr()
        linhas = await ctx.db.process_ai_log.find({"process_id": PID, "accao": "sanitizar"}).to_list(None)
        assert len(linhas) == 1 and linhas[0]["estado"] == "falha"
        assert linhas[0]["motivo"] in ailog.MOTIVOS

    @pytest.mark.asyncio
    async def test_o_alerta_e_um_aviso_nunca_bloqueia(self, ctx):
        from models.index_module import ALERTAS

        assert ALERTAS["sanitizacao_falhou"][0] == "aviso"

    @pytest.mark.asyncio
    async def test_uma_excepcao_inesperada_na_conversao_nao_rebenta_o_job(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        with patch.object(sz, "construir_pdf_limpo", side_effect=RuntimeError("boom")):
            r = await ctx.correr()
        assert r["falhas"] == 1
        await self._intacto(ctx)

    @pytest.mark.asyncio
    async def test_o_alerta_nao_se_duplica_em_corridas_repetidas(self, ctx):
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        ctx.fake_s3.put_falha = True
        await ctx.correr()
        await ctx.correr()
        assert len(await ctx.db.process_index_alerts.find({"process_id": PID}).to_list(None)) == 1


class TestFechoChamaASanitizacao:
    @pytest.mark.asyncio
    async def test_sem_o_interruptor_nao_faz_nada(self, monkeypatch):
        monkeypatch.setenv("INDEX_SANITIZE_ENABLED", "false")
        with patch.object(sz, "sanitizar_processo", AsyncMock()) as corre:
            assert await sz.sanitizar_do_fecho({"id": PID}, None) == {}
        corre.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_com_o_interruptor_corre_e_resume(self, monkeypatch):
        monkeypatch.setenv("INDEX_SANITIZE_ENABLED", "true")
        with patch.object(sz, "sanitizar_processo", AsyncMock(return_value={"sanitizados": 2, "falhas": 1})):
            assert await sz.sanitizar_do_fecho({"id": PID}, None) == {"sanitizados": 2, "sanitizacao_falhas": 1}

    def test_o_fecho_importa_e_chama_o_modulo(self):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
        from services import index_finalize as fin

        fonte = codigo_da_funcao_sem_comentarios(fin._sanitizar_sem_falhar)
        assert "sanitizar_do_fecho" in fonte and "ImportError" in fonte


# ====================================================================
# 5. A PURGA
# ====================================================================
async def preparar_sanitizado(ctx, *, fotos=1):
    """Sanitiza de verdade e devolve ids; a purga parte do estado REAL que a sanitização deixa."""
    if fotos == 1:
        await ctx.semear([recibo("r1", "recibo.pdf")], {caminho("recibo.pdf"): pdf_sujo()})
        ids_ = ["r1"]
    else:
        docs = [extrato(f"e{i}", f"p{i}.jpg", criado=f"2026-10-01T10:0{i}:00") for i in range(1, fotos + 1)]
        await ctx.semear(docs, {caminho(f"p{i}.jpg"): jpeg_com_exif() for i in range(1, fotos + 1)})
        ids_ = [d["id"] for d in docs]
    await ctx.correr()
    return ids_


DEPOIS_DA_GRACA = AGORA + timedelta(days=31)


@pytest.fixture
def purga_ligada(monkeypatch):
    monkeypatch.setenv("INDEX_PURGE_ENABLED", "true")


class TestPurga:
    @pytest.mark.asyncio
    async def test_desligada_nao_apaga_nada_mesmo_vencida(self, ctx, monkeypatch):
        monkeypatch.delenv("INDEX_PURGE_ENABLED", raising=False)
        await preparar_sanitizado(ctx)
        r = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r["ligada"] is False and r["purgados"] == 0
        assert caminho("recibo.pdf") in ctx.fake_s3.objectos and ctx.fake_s3.apagados == []

    @pytest.mark.asyncio
    async def test_dentro_da_graca_nao_apaga(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx)
        r = await sz.purgar_originais_vencidos(AGORA + timedelta(days=29, hours=23))
        assert r["purgados"] == 0 and ctx.fake_s3.apagados == []
        assert caminho("recibo.pdf") in ctx.fake_s3.objectos

    @pytest.mark.asyncio
    async def test_passada_a_graca_apaga_o_original_e_repoe_as_referencias(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx)
        limpo = caminho("recibo_limpo.pdf")
        await ctx.db.documents.insert_one({"id": "pedido-1", "process_id": PID, "s3_path": caminho("recibo.pdf"),
                                           "attached_files": [{"s3_path": caminho("recibo.pdf"), "filename": "recibo.pdf"}]})
        r = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r["purgados"] == 1
        assert caminho("recibo.pdf") not in ctx.fake_s3.objectos and limpo in ctx.fake_s3.objectos
        original = await ctx.doc("r1")
        assert original["file_state"] == "purgado" and original["s3_path"] == limpo
        assert original["s3_path_original"] == caminho("recibo.pdf") and original["original_deleted"] is True
        pedido = await ctx.db.documents.find_one({"id": "pedido-1"})
        assert pedido["s3_path"] == limpo and pedido["attached_files"][0]["s3_path"] == limpo

    @pytest.mark.asyncio
    async def test_a_copia_limpa_corrompida_adia_e_o_original_fica(self, ctx, purga_ligada):
        """A mutação que remove a verificação da cópia limpa tem de morrer AQUI."""
        await preparar_sanitizado(ctx)
        ctx.fake_s3.objectos[caminho("recibo_limpo.pdf")] = b"%PDF-1.4 outra coisa qualquer"
        r = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r["purgados"] == 0 and r["adiados"] == 1
        assert caminho("recibo.pdf") in ctx.fake_s3.objectos and ctx.fake_s3.apagados == []
        assert (await ctx.doc("r1"))["file_state"] == "sanitizado"

    @pytest.mark.asyncio
    async def test_a_copia_limpa_desaparecida_adia(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx)
        del ctx.fake_s3.objectos[caminho("recibo_limpo.pdf")]
        assert (await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA))["purgados"] == 0
        assert caminho("recibo.pdf") in ctx.fake_s3.objectos

    @pytest.mark.asyncio
    async def test_a_copia_limpa_com_o_hash_trocado_adia(self, ctx, purga_ligada):
        """Um PDF limpo VÁLIDO mas diferente do que se gravou (alguém o substituiu) não serve de prova."""
        await preparar_sanitizado(ctx)
        outro, _ = sz.construir_pdf_limpo([("x.pdf", pdf_sujo("Outro documento"))])
        ctx.fake_s3.objectos[caminho("recibo_limpo.pdf")] = outro
        assert (await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA))["purgados"] == 0
        assert caminho("recibo.pdf") in ctx.fake_s3.objectos

    @pytest.mark.asyncio
    async def test_a_falha_de_verificacao_fica_no_log_da_ia(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx)
        del ctx.fake_s3.objectos[caminho("recibo_limpo.pdf")]
        await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        linhas = await ctx.db.process_ai_log.find({"accao": "purgar"}).to_list(None)
        assert [(l["estado"], l["motivo"]) for l in linhas] == [("falha", "purga_adiada")]

    @pytest.mark.asyncio
    async def test_um_grupo_so_se_purga_inteiro(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx, fotos=3)
        # uma das partes tem uma graça que ainda não acabou
        futuro = (DEPOIS_DA_GRACA + timedelta(days=10)).isoformat()
        await ctx.db.document_metadata.update_one({"id": "e3"}, {"$set": {"purge_after": futuro}})
        r = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r["purgados"] == 0 and ctx.fake_s3.apagados == []
        assert all(caminho(f"p{i}.jpg") in ctx.fake_s3.objectos for i in (1, 2, 3))

    @pytest.mark.asyncio
    async def test_grupo_vencido_apaga_todas_as_partes_e_o_portal_fica_sem_duplicados(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx, fotos=3)
        limpo = caminho("extrato_bancario_2026-09_limpo.pdf")
        await ctx.db.documents.insert_one({"id": "pedido-1", "process_id": PID, "attached_files": [
            {"s3_path": caminho(f"p{i}.jpg"), "filename": f"p{i}.jpg"} for i in (1, 2, 3)]})
        r = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r["purgados"] == 3
        assert sorted(ctx.fake_s3.apagados) == [caminho(f"p{i}.jpg") for i in (1, 2, 3)]
        assert limpo in ctx.fake_s3.objectos
        pedido = await ctx.db.documents.find_one({"id": "pedido-1"})
        assert [a["s3_path"] for a in pedido["attached_files"]] == [limpo]

    @pytest.mark.asyncio
    async def test_nunca_apaga_a_chave_do_pdf_limpo(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx)
        limpo = caminho("recibo_limpo.pdf")
        await ctx.db.document_metadata.update_one({"id": "r1"}, {"$set": {"s3_path": limpo}})  # dados corrompidos
        await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert limpo in ctx.fake_s3.objectos and limpo not in ctx.fake_s3.apagados

    @pytest.mark.asyncio
    async def test_o_que_nao_e_do_index_nunca_se_apaga(self, ctx, purga_ligada):
        """Só entra na purga o que a sanitização marcou: um registo sem `sanitizado` não é tocado."""
        await ctx.semear([recibo("r1", "do_cliente.pdf")], {caminho("do_cliente.pdf"): pdf_sujo()})
        await ctx.db.document_metadata.update_one({"id": "r1"}, {"$set": {"uploaded_by_index": False}})
        await ctx.correr()
        assert (await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA))["purgados"] == 0
        assert caminho("do_cliente.pdf") in ctx.fake_s3.objectos

    @pytest.mark.asyncio
    async def test_apagar_do_s3_a_falhar_regista_e_volta_a_tentar_depois(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx)
        ctx.fake_s3.apagar_falha = True
        r1 = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r1["purgados"] == 1 and caminho("recibo.pdf") in ctx.fake_s3.objectos
        assert (await ctx.doc("r1"))["original_deleted"] is False
        ctx.fake_s3.apagar_falha = False
        r2 = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r2["reapagados"] == 1 and caminho("recibo.pdf") not in ctx.fake_s3.objectos
        assert (await ctx.doc("r1"))["original_deleted"] is True

    @pytest.mark.asyncio
    async def test_um_original_fora_da_raiz_documental_nunca_se_apaga(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx)
        ctx.fake_s3.objectos["backups/dump.zip"] = b"zip"
        await ctx.db.document_metadata.update_one(
            {"id": "r1"}, {"$set": {"file_state": "purgado", "original_deleted": False,
                                    "s3_path_original": "backups/dump.zip", "s3_path": "x"}})
        await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert "backups/dump.zip" in ctx.fake_s3.objectos

    @pytest.mark.asyncio
    async def test_os_dados_do_original_purgado_continuam_a_contar(self, ctx, purga_ligada):
        """Eliminar os bytes não torna falso o que se leu: os `index_facts` do original ficam."""
        await preparar_sanitizado(ctx)
        await ctx.db.document_metadata.update_one({"id": "r1"}, {"$set": {"index_job": {"x": 1}}})
        await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        d = await ctx.doc("r1")
        assert d["index_facts"]["tipo"] == "recibo_vencimento" and d["index_job"] == {"x": 1}

    @pytest.mark.asyncio
    async def test_nunca_levanta(self, ctx, purga_ligada):
        with patch.object(sz.db.document_metadata, "find", side_effect=RuntimeError("bd em baixo")):
            r = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r["purgados"] == 0

    @pytest.mark.asyncio
    async def test_e_idempotente(self, ctx, purga_ligada):
        await preparar_sanitizado(ctx)
        await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        r = await sz.purgar_originais_vencidos(DEPOIS_DA_GRACA)
        assert r["purgados"] == 0 and r["adiados"] == 0


# ====================================================================
# 6. O JOB MANUAL E AS LIGAÇÕES
# ====================================================================
class TestJobManual:
    @pytest.mark.asyncio
    async def test_devolve_ja_e_nao_cria_dois(self):
        from services import index_jobs as jobs

        spawn = MagicMock()
        with patch.object(jobs, "reivindicar_job", AsyncMock(side_effect=[("t-1", None), (None, "t-1")])), \
                patch("services.background_tasks.spawn_background_task", spawn), \
                patch.object(sz, "correr_sanitizacao", MagicMock(return_value="coro")):
            a = await sz.iniciar_sanitizacao(PID, {"id": "u"})
            b = await sz.iniciar_sanitizacao(PID, {"id": "u"})
        assert a == {"task_id": "t-1", "iniciado": True} and b == {"task_id": "t-1", "iniciado": False}
        assert spawn.call_count == 1

    @pytest.mark.asyncio
    async def test_termina_sempre_o_tasklog_e_liberta_a_chave(self, ctx):
        from services import index_jobs as jobs
        from services.task_log_service import TaskLogService

        actualizar = AsyncMock()
        with patch.object(TaskLogService, "update_task", actualizar), \
                patch.object(sz, "sanitizar_processo", AsyncMock(side_effect=RuntimeError("x"))), \
                patch.object(jobs, "libertar_job", AsyncMock()) as liberta:
            await sz.correr_sanitizacao("t-1", PID, {"id": "u"})
        from models.task_log import TaskStatus

        assert TaskStatus.FAILED in [c.kwargs.get("status") for c in actualizar.await_args_list]
        liberta.assert_awaited_once_with("t-1")

    def test_a_purga_esta_ligada_ao_agendador(self):
        from services import scheduled_tasks
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(scheduled_tasks.ScheduledTasksService.run_all_tasks) \
            if hasattr(scheduled_tasks, "ScheduledTasksService") else ""
        if not fonte:
            import inspect

            classe = next(c for _, c in inspect.getmembers(scheduled_tasks, inspect.isclass) if hasattr(c, "purge_index_originals"))
            fonte = codigo_da_funcao_sem_comentarios(classe.run_all_tasks)
        assert "purge_index_originals" in fonte

    def test_o_motor_financeiro_ignora_o_pdf_limpo(self):
        import inspect

        from services import financial_engine
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        assert "is_clean_pdf" in codigo_da_funcao_sem_comentarios(financial_engine.collect_financial_documents)

    @pytest.mark.asyncio
    async def test_o_motor_financeiro_nao_conta_duas_vezes(self, fake_async_db):
        from services import financial_engine as fe

        await fake_async_db.document_metadata.insert_many([
            {"id": "o", "process_id": PID, "ai_category": "Financeiros", "ai_subcategory": "Recibo de Vencimento",
             "filename": "recibo_vencimento.pdf"},
            {"id": "l", "process_id": PID, "ai_category": "Financeiros", "ai_subcategory": "Recibo de Vencimento",
             "filename": "recibo_vencimento_limpo.pdf", "is_clean_pdf": True},
        ])
        with patch.object(fe, "db", fake_async_db):
            docs = await fe.collect_financial_documents(PID)
        assert [d["id"] for d in docs] == ["o"]
