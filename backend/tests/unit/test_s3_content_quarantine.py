"""
Testes unitários — Quarentena de conteúdo do Portal (magic bytes pós-upload).

O upload do Portal é pré-assinado: os bytes vão do browser para o S3 sem
passar pelo backend, pelo que a parede de `file_validation` não pode ser
chamada no ponto de entrada. É chamada DEPOIS do facto, com um `HEAD` (tamanho
e tipo reais) e um `GET` de 2 KB (assinatura), e o registo na base de dados só
nasce se os bytes forem o que dizem ser.

Este ficheiro cobre a camada de DECISÃO (pura) e a de I/O (com o S3
falseado). O caminho ponta a ponta pelo `confirm-upload` está em
`test_portal_upload_path_traversal.py`, junto às guardas de posse.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services import s3_content_quarantine as q


# ── AMOSTRAS REAIS ────────────────────────────────────────────────────────
# Construídas para o `libmagic` as reconhecer de facto. Uma assinatura
# truncada não serve: um `b"\x89PNG..."` seguido de lixo é detectado como
# `application/octet-stream`, e um teste escrito sobre isso provaria que o
# genérico é rejeitado — não que um PNG é aceite.
import struct as _struct
import zlib as _zlib


def _pedaco_png(tipo: bytes, dados: bytes) -> bytes:
    return (
        _struct.pack(">I", len(dados)) + tipo + dados
        + _struct.pack(">I", _zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    )


PDF = b"%PDF-1.7\n" + b"0" * 200

PNG = (
    b"\x89PNG\r\n\x1a\n"
    + _pedaco_png(b"IHDR", _struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    + _pedaco_png(b"IDAT", _zlib.compress(b"\x00\x00\x00\x00"))
    + _pedaco_png(b"IEND", b"")
)

JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\xff\xd9"
)

# ZIP — e é o limite conhecido do método: um `.docx` É um ZIP, pelo que um ZIP
# renomeado passa como documento Office.
ZIP_DOCX = b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 200

# Executável ELF64 com cabeçalho COMPLETO → `application/x-executable`, que
# está na lista de MIME perigosos e dispara o log crítico.
ELF = (
    b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    + _struct.pack(
        "<HHIQQQIHHHHHH",
        2, 0x3E, 1, 0x401000, 64, 0, 0, 64, 56, 1, 64, 0, 0,
    )
    + b"\x00" * 128
)

# Executável Windows → `application/x-dosexec`, que **não** está na lista de
# perigosos; é a WHITELIST que o recusa. Ver
# `TestQualParedeApanhaOQue` — a diferença importa.
EXE_DOS = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 200

# HTML com script: o clássico do XSS armazenado.
HTML = b"<!DOCTYPE html>\n<html><script>alert(1)</script></html>" + b" " * 200

# SVG com script — uma "imagem" que o browser executa.
SVG = (
    b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg">'
    b'<script>alert(1)</script></svg>'
)

# Script de shell.
SHELL = b"#!/bin/sh\nrm -rf /\n" + b" " * 100

UM_MB = 1024 * 1024


# ====================================================================
# A DECISÃO, PURA
# ====================================================================

class TestOQuePassa:
    """A contraprova: sem isto, uma parede de cimento passaria tudo o resto."""

    @pytest.mark.parametrize("amostra,esperado", [
        (PDF, "application/pdf"),
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
    ])
    def test_os_formatos_da_whitelist_sao_aprovados(self, amostra, esperado):
        v = q.avaliar_amostra(
            amostra, filename="documento.pdf", tamanho_real=UM_MB
        )
        assert v.aprovado is True
        assert v.tipo_detectado == esperado
        assert v.codigo_http == 200

    def test_o_tipo_devolvido_e_o_DETECTADO_nao_o_declarado(self):
        """Um PNG enviado com o nome `.pdf` é gravado como PNG.

        É o ponto todo: o `content_type` que vai para a base de dados sai dos
        BYTES, não do que o cliente escreveu no corpo do pedido.
        """
        v = q.avaliar_amostra(PNG, filename="fatura.pdf", tamanho_real=UM_MB)
        assert v.aprovado is True
        assert v.tipo_detectado == "image/png"


class TestOExecutavelDisfarcado:
    """O caso que motivou a parede."""

    @pytest.mark.parametrize("amostra", [ELF, EXE_DOS])
    def test_um_executavel_com_nome_de_pdf_e_reprovado(self, amostra):
        v = q.avaliar_amostra(
            amostra, filename="IRS_2025.pdf", tamanho_real=UM_MB
        )
        assert v.aprovado is False
        assert v.motivo == q.MOTIVO_CONTEUDO
        assert v.codigo_http == 400

    def test_html_com_script_e_reprovado(self):
        v = q.avaliar_amostra(
            HTML, filename="recibo.pdf", tamanho_real=UM_MB
        )
        assert v.aprovado is False
        assert v.motivo == q.MOTIVO_CONTEUDO

    def test_a_reprovacao_de_conteudo_NAO_e_transitoria(self):
        """E é isto que autoriza apagar o objecto.

        Se `transitorio` viesse `True` por engano, o ficheiro mau ficava no
        bucket — e os prefixos deste bucket são servidos por URL pré-assinado.
        """
        v = q.avaliar_amostra(ELF, filename="x.pdf", tamanho_real=UM_MB)
        assert v.transitorio is False

    def test_a_mensagem_para_o_cliente_vem_da_parede_do_CRM(self):
        """O cliente do Portal lê o MESMO texto que um utilizador do CRM leria.

        Duplicar as mensagens aqui era garantir que divergiriam da whitelist
        que as gera.
        """
        from services.file_validation import validate_file_content

        v = q.avaliar_amostra(ELF, filename="x.pdf", tamanho_real=UM_MB)

        try:
            validate_file_content(ELF, "x.pdf")
            pytest.fail("a parede do CRM tinha de recusar este ficheiro")
        except HTTPException as recusa:
            assert v.detalhe == str(recusa.detail)

    @pytest.mark.parametrize("amostra,nome", [
        (HTML, "html"), (SVG, "svg com script"), (SHELL, "script de shell"),
    ])
    def test_outros_conteudos_executaveis_sao_reprovados(self, amostra, nome):
        v = q.avaliar_amostra(amostra, filename="recibo.pdf", tamanho_real=UM_MB)
        assert v.aprovado is False, nome
        assert v.motivo == q.MOTIVO_CONTEUDO


class TestOTamanhoVemDoHeadNuncaDaAmostra:
    """A armadilha que quase transformou esta parede num placebo.

    O `validate_file_content` TAMBÉM verifica tamanho — mas a partir do
    `len()` do que lhe dermos, e nós damos-lhe 2 KB. Essa verificação é, no
    nosso caso, vácua: passa sempre. Se confiássemos nela, tínhamos uma parede
    que valida o tipo e carimba QUALQUER tamanho.
    """

    def test_um_pdf_de_500MB_e_reprovado_apesar_da_amostra_ter_2KB(self):
        v = q.avaliar_amostra(
            PDF, filename="enorme.pdf", tamanho_real=500 * UM_MB
        )
        assert v.aprovado is False
        assert v.motivo == q.MOTIVO_GRANDE
        assert "500" in v.detalhe

    def test_a_amostra_sozinha_NAO_reprovaria(self):
        """A contraprova directa da armadilha.

        A parede do CRM, olhando só para os 2 KB que lhe passamos, aprova —
        e é por isso que o tamanho tem de ser verificado noutro sítio.
        """
        from services.file_validation import validate_file_content

        valido, _, _ = validate_file_content(PDF, "enorme.pdf")
        assert valido is True, (
            "a amostra passa na parede do CRM: o tamanho real TEM de ser "
            "verificado contra o HEAD, não contra a amostra"
        )

    def test_o_limite_e_o_do_TIPO_detectado(self):
        """Um PNG tem 20 MB de limite; um PDF tem 50 MB. 30 MB separa-os."""
        png = q.avaliar_amostra(PNG, filename="foto.png", tamanho_real=30 * UM_MB)
        pdf = q.avaliar_amostra(PDF, filename="doc.pdf", tamanho_real=30 * UM_MB)

        assert png.aprovado is False and png.motivo == q.MOTIVO_GRANDE
        assert pdf.aprovado is True

    def test_os_limites_saem_da_whitelist_do_CRM(self):
        """Uma tabela de limites própria divergiria da do CRM em seis meses."""
        from services.file_validation import ALLOWED_MIME_TYPES

        assert q.limite_em_bytes("image/png") == (
            ALLOWED_MIME_TYPES["image/png"]["max_size_mb"] * UM_MB
        )
        assert q.limite_em_bytes("application/pdf") == (
            ALLOWED_MIME_TYPES["application/pdf"]["max_size_mb"] * UM_MB
        )

    def test_tipo_sem_limite_declarado_cai_no_tecto_absoluto(self):
        """Nunca "sem limite" — o desconhecido é o caso a proteger."""
        assert q.limite_em_bytes("tipo/inventado") == q.TAMANHO_MAXIMO_MB * UM_MB
        assert q.limite_em_bytes(None) == q.TAMANHO_MAXIMO_MB * UM_MB


class TestVazioEIlegivel:
    def test_ficheiro_vazio_e_reprovado_e_nao_e_transitorio(self):
        v = q.avaliar_amostra(b"", filename="vazio.pdf", tamanho_real=0)
        assert v.aprovado is False
        assert v.motivo == q.MOTIVO_VAZIO
        assert v.transitorio is False

    def test_amostra_None_e_TRANSITORIA_e_nao_reprovacao(self):
        """`None` = não conseguimos LER. Não sabemos o que lá está.

        Tratar isto como reprovação de conteúdo apagaria o upload legítimo de
        um cliente por causa de um soluço do S3. É a decisão mais importante
        deste módulo.
        """
        v = q.avaliar_amostra(None, filename="x.pdf", tamanho_real=UM_MB)
        assert v.aprovado is False
        assert v.motivo == q.MOTIVO_ILEGIVEL
        assert v.transitorio is True
        assert v.codigo_http == 503

    def test_um_libmagic_em_falta_e_transitorio_e_nao_culpa_do_ficheiro(self):
        """Uma dependência NOSSA em falta não apaga o ficheiro do cliente."""
        with patch.object(
            q, "validate_file_content", side_effect=OSError("libmagic ausente")
        ):
            v = q.avaliar_amostra(PDF, filename="x.pdf", tamanho_real=UM_MB)

        assert v.transitorio is True
        assert v.codigo_http == 503


# ====================================================================
# O I/O — S3 falseado, tudo o resto real
# ====================================================================

class S3Falso:
    """S3 com um objecto por chave e contabilidade do que foi pedido."""

    def __init__(self, objectos: dict[str, bytes] | None = None):
        self.objectos = dict(objectos or {})
        self.heads: list[str] = []
        self.intervalos: list[tuple[str, int]] = []
        self.apagados: list[str] = []
        self.estado_forcado: str | None = None
        self.prefixo_ilegivel = False
        self.apagar_falha = False

    def is_configured(self) -> bool:
        return True

    def head_object_metadata(self, object_name: str):
        self.heads.append(object_name)
        if self.estado_forcado:
            return self.estado_forcado, None
        if object_name not in self.objectos:
            return "ausente", None
        corpo = self.objectos[object_name]
        return "ok", {
            "tamanho": len(corpo),
            "tipo": "application/pdf",
            "etag": "abc",
        }

    def get_object_prefix(self, object_name: str, num_bytes: int):
        self.intervalos.append((object_name, num_bytes))
        if self.prefixo_ilegivel:
            return None
        return self.objectos.get(object_name, b"")[:num_bytes]

    def delete_file(self, object_name: str) -> bool:
        if self.apagar_falha:
            return False
        self.apagados.append(object_name)
        self.objectos.pop(object_name, None)
        return True


CHAVE = "Documentação Clientes/Ana/Index/doc.pdf"


@pytest.fixture
def s3(request):
    return S3Falso()


def _com(s3_falso):
    return patch.object(q, "s3_service", s3_falso)


class TestInspeccionar:
    @pytest.mark.asyncio
    async def test_le_apenas_os_primeiros_2KB(self, s3):
        s3.objectos[CHAVE] = PDF + b"X" * (10 * UM_MB)
        with _com(s3):
            v = await q.inspeccionar(CHAVE, filename="doc.pdf")

        assert v.aprovado is True
        assert s3.intervalos == [(CHAVE, q.BYTES_DE_INSPECCAO)], (
            "um ficheiro de 10 MB não pode ser descarregado inteiro para se "
            "lerem os primeiros bytes"
        )

    @pytest.mark.asyncio
    async def test_a_chave_inspeccionada_e_exactamente_a_pedida(self, s3):
        """Sem variações de caminho.

        O `get_file_content` tenta variantes (underscore <-> espaço) para
        sobreviver a dados legados. Numa parede de segurança isso inspeccionaria
        os bytes de UMA chave e gravaria OUTRA no registo.
        """
        s3.objectos[CHAVE] = PDF
        with _com(s3):
            await q.inspeccionar(CHAVE, filename="doc.pdf")

        assert s3.heads == [CHAVE]
        assert [chave for chave, _ in s3.intervalos] == [CHAVE]

    @pytest.mark.asyncio
    async def test_objecto_ausente_da_motivo_ausente_e_nao_le_bytes(self, s3):
        with _com(s3):
            v = await q.inspeccionar("nao/existe.pdf", filename="x.pdf")

        assert v.motivo == q.MOTIVO_AUSENTE
        assert v.transitorio is False
        assert s3.intervalos == [], "não se leem bytes de um objecto que não existe"

    @pytest.mark.asyncio
    async def test_erro_no_head_e_transitorio(self, s3):
        s3.estado_forcado = "erro"
        with _com(s3):
            v = await q.inspeccionar(CHAVE, filename="x.pdf")

        assert v.transitorio is True
        assert v.codigo_http == 503

    @pytest.mark.asyncio
    async def test_objecto_gigante_e_reprovado_SEM_se_lerem_bytes(self, s3):
        """O tamanho já o condena; ler 2 KB para chegar à mesma conclusão é
        trabalho a mais — e é um `GET` a mais contra o S3 por cada ataque."""
        s3.objectos[CHAVE] = b"P" * ((q.TAMANHO_MAXIMO_MB + 1) * UM_MB)
        with _com(s3):
            v = await q.inspeccionar(CHAVE, filename="x.pdf")

        assert v.motivo == q.MOTIVO_GRANDE
        assert s3.intervalos == []

    @pytest.mark.asyncio
    async def test_objecto_de_zero_bytes_e_reprovado_sem_ler(self, s3):
        s3.objectos[CHAVE] = b""
        with _com(s3):
            v = await q.inspeccionar(CHAVE, filename="x.pdf")

        assert v.motivo == q.MOTIVO_VAZIO
        assert s3.intervalos == []

    @pytest.mark.asyncio
    async def test_prefixo_ilegivel_e_transitorio(self, s3):
        s3.objectos[CHAVE] = PDF
        s3.prefixo_ilegivel = True
        with _com(s3):
            v = await q.inspeccionar(CHAVE, filename="x.pdf")

        assert v.transitorio is True


class TestExigirConteudoValido:
    """O ponto único que um `confirm-upload` chama."""

    @pytest.mark.asyncio
    async def test_aprovado_devolve_o_veredicto_e_nao_apaga(self, s3):
        s3.objectos[CHAVE] = PDF
        with _com(s3):
            v = await q.exigir_conteudo_valido(CHAVE, filename="doc.pdf")

        assert v.aprovado is True
        assert s3.apagados == []
        assert CHAVE in s3.objectos

    @pytest.mark.asyncio
    async def test_executavel_disfarcado_apaga_o_objecto_e_levanta_400(self, s3):
        s3.objectos[CHAVE] = ELF
        with _com(s3), pytest.raises(HTTPException) as erro:
            await q.exigir_conteudo_valido(CHAVE, filename="IRS.pdf")

        assert erro.value.status_code == 400
        assert s3.apagados == [CHAVE]
        assert CHAVE not in s3.objectos, "o ficheiro mau não pode ficar no bucket"

    @pytest.mark.asyncio
    async def test_falha_transitoria_levanta_503_e_NAO_apaga(self, s3):
        """A decisão que protege o cliente de um soluço do S3."""
        s3.objectos[CHAVE] = PDF
        s3.prefixo_ilegivel = True

        with _com(s3), pytest.raises(HTTPException) as erro:
            await q.exigir_conteudo_valido(CHAVE, filename="doc.pdf")

        assert erro.value.status_code == 503
        assert s3.apagados == [], (
            "não se apaga o upload de um cliente por não se conseguir ler"
        )
        assert CHAVE in s3.objectos

    @pytest.mark.asyncio
    async def test_objecto_ausente_levanta_400_e_nao_tenta_apagar(self, s3):
        with _com(s3), pytest.raises(HTTPException) as erro:
            await q.exigir_conteudo_valido("nao/existe.pdf", filename="x.pdf")

        assert erro.value.status_code == 400
        assert s3.apagados == []

    @pytest.mark.asyncio
    async def test_falhar_a_apagar_nao_muda_a_resposta_ao_cliente(self, s3):
        """A recusa mantém-se; fica um órfão no bucket e um log a `error`.

        Transformar isto noutro erro diria ao cliente que o problema é outro —
        e o problema dele continua a ser o ficheiro que enviou.
        """
        s3.objectos[CHAVE] = ELF
        s3.apagar_falha = True

        with _com(s3), pytest.raises(HTTPException) as erro:
            await q.exigir_conteudo_valido(CHAVE, filename="x.pdf")

        assert erro.value.status_code == 400
        assert s3.apagados == []


class TestForaDoEventLoop:
    """O `boto3` é síncrono; chamá-lo de uma corotina pára o worker INTEIRO.

    É a família de defeito do `smtplib` no `send_email` (incidente CI
    2026-09-21), e num upload de cliente o tempo de rede não é pequeno. Guarda
    sobre o código-fonte porque num teste o S3 falseado responde
    instantaneamente e uma chamada bloqueante é indistinguível de uma que não
    o é.
    """

    CHAMADAS_DE_REDE = ("head_object_metadata", "get_object_prefix", "delete_file")

    def test_todas_as_chamadas_ao_s3_vao_por_to_thread(self):
        import ast
        import inspect

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(inspect.getsource(q))
        arvore = ast.parse(fonte)

        directas: list[str] = []
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            alvo = ast.unparse(no.func)
            if not alvo.startswith("s3_service."):
                continue
            metodo = alvo.split(".", 1)[1]
            if metodo in self.CHAMADAS_DE_REDE:
                # Chamada DIRECTA (com parênteses) a um método de rede: é o
                # defeito. Por `to_thread` o método é passado como REFERÊNCIA,
                # sem parênteses, pelo que não aparece como `ast.Call`.
                directas.append(metodo)

        assert directas == [], (
            f"chamadas síncronas ao S3 dentro de corotinas: {directas} — "
            "passar por `asyncio.to_thread`"
        )

    def test_a_contraprova_as_referencias_existem_mesmo(self):
        """Sem isto, apagar as chamadas todas satisfaria o guarda acima."""
        import inspect

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(inspect.getsource(q))
        for metodo in self.CHAMADAS_DE_REDE:
            assert f"s3_service.{metodo}" in fonte, (
                f"o módulo deixou de usar `{metodo}` — o guarda acima passaria "
                "a ser decorativo"
            )
            assert "asyncio.to_thread" in fonte


class TestQualParedeApanhaOQue:
    """Duas listas recusam, e não é a mesma a recusar cada coisa.

    O `file_validation` tem uma BLACKLIST (`DANGEROUS_MIME_TYPES`, log
    `critical`) e uma WHITELIST (`ALLOWED_MIME_TYPES`, log `warning`). Saber
    qual apanha o quê importa por duas razões: o alerta que se vê nos logs é
    diferente, e a blacklist é mais estreita do que o nome sugere.

    **Achado:** um executável de Windows é detectado como
    `application/x-dosexec`, que NÃO está na blacklist (ela tem
    `application/x-msdos-program` e `application/x-msdownload`). É a whitelist
    que o recusa. O resultado para o cliente é o mesmo 400 — a arquitectura
    é fail-closed e é isso que a salva —, mas quem contar com a blacklist para
    ALERTAR sobre executáveis de Windows não vai ver nada nos logs.
    """

    def test_um_elf_completo_bate_na_blacklist(self):
        import magic
        from services.file_validation import DANGEROUS_MIME_TYPES

        assert magic.from_buffer(ELF, mime=True) in DANGEROUS_MIME_TYPES

    def test_um_exe_de_windows_NAO_bate_na_blacklist(self):
        """O achado, fixado num teste para não se perder.

        Se alguém acrescentar `application/x-dosexec` à blacklist, este teste
        fica vermelho — e a correcção é apagá-lo com a explicação, não o
        contrário.
        """
        import magic
        from services.file_validation import (
            ALLOWED_MIME_TYPES,
            DANGEROUS_MIME_TYPES,
        )

        detectado = magic.from_buffer(EXE_DOS, mime=True)
        assert detectado == "application/x-dosexec"
        assert detectado not in DANGEROUS_MIME_TYPES, (
            "se isto mudou, actualizar o comentário desta classe"
        )
        assert detectado not in ALLOWED_MIME_TYPES, (
            "e é a whitelist que o recusa — é ela que torna o defeito acima "
            "inofensivo"
        )

    def test_e_por_isso_que_a_arquitectura_e_whitelist_e_nao_blacklist(self):
        """A prova de que o fail-closed é o que protege, não a lista negra.

        Um tipo inventado, que nenhuma blacklist poderia prever, é recusado.
        """
        v = q.avaliar_amostra(
            b"\x00\x01\x02\x03formato que ninguem previu" + b"\x00" * 200,
            filename="documento.pdf",
            tamanho_real=UM_MB,
        )
        assert v.aprovado is False
        assert v.motivo == q.MOTIVO_CONTEUDO


class TestOQueEstaParedeNaoFaz:
    """Honestidade sobre o alcance: magic bytes provam formato, não inocência.

    Sem estes testes, alguém lê "parede de magic bytes" e conclui que o bucket
    está limpo. Estão aqui para dizer, em código, exactamente onde a parede
    acaba — e para que a conversa sobre antivírus/sandbox seja tida com os
    factos à frente.
    """

    def test_um_zip_renomeado_passa_como_documento_office(self):
        """`.docx`/`.xlsx` SÃO ZIPs; `application/zip` está na whitelist.

        Não é defeito desta implementação — é o limite do método. Para
        distinguir um `.docx` de um ZIP qualquer seria preciso abrir o arquivo
        e procurar o `[Content_Types].xml`, o que exige o ficheiro INTEIRO e
        não os primeiros 2 KB.
        """
        v = q.avaliar_amostra(
            ZIP_DOCX, filename="contrato.docx", tamanho_real=UM_MB
        )
        assert v.aprovado is True
        assert v.tipo_detectado == "application/zip"

    def test_um_pdf_valido_e_aceite_seja_o_que_for_que_tenha_dentro(self):
        """Um PDF com JavaScript dentro é um PDF. A parede não o abre."""
        pdf_com_js = (
            b"%PDF-1.7\n"
            b"1 0 obj<</Type/Catalog/OpenAction<</S/JavaScript/JS(app.alert(1))>>>>"
            + b"0" * 200
        )
        v = q.avaliar_amostra(
            pdf_com_js, filename="proposta.pdf", tamanho_real=UM_MB
        )
        assert v.aprovado is True


# ====================================================================
# AS PRIMITIVAS REAIS DO S3 — apanhadas por mutação
# ====================================================================
# Duas mutações sobreviveram à primeira ronda e nenhuma era mutante
# equivalente: apagar o cabeçalho `Range` do `get_object_prefix` (passando a
# descarregar o objecto INTEIRO) e confundir "ausente" com "erro" no
# `head_object_metadata` (passando a apagar ficheiros legítimos). Sobreviveram
# porque TODOS os testes acima usam um S3 falseado que implementa ele próprio
# o corte dos bytes e a lógica dos três estados — o falso escondia a única
# coisa que estas funções fazem.
#
# É a lição do AGENTS.md outra vez: um duplo de teste demasiado esperto valida
# o duplo, não o código. Estes testes falam com um cliente `boto3` falseado ao
# nível da CHAMADA, para as asserções serem sobre os PARÂMETROS que saem.

class ClienteBoto3Falso:
    """Cliente `boto3` ao nível da chamada: guarda argumentos, devolve o que lhe dizem."""

    def __init__(self):
        self.chamadas_head: list[dict] = []
        self.chamadas_get: list[dict] = []
        self.resposta_head: dict = {
            "ContentLength": 1234,
            "ContentType": "application/pdf",
            "ETag": '"abc123"',
        }
        self.corpo = b"%PDF-1.7 conteudo"
        self.erro_head: Exception | None = None
        self.erro_get: Exception | None = None

    def head_object(self, **kwargs):
        self.chamadas_head.append(kwargs)
        if self.erro_head:
            raise self.erro_head
        return self.resposta_head

    def get_object(self, **kwargs):
        self.chamadas_get.append(kwargs)
        if self.erro_get:
            raise self.erro_get

        class _Corpo:
            def __init__(self, dados):
                self._dados = dados

            def read(self):
                return self._dados

        return {"Body": _Corpo(self.corpo)}


def _erro_cliente(codigo: str):
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": codigo, "Message": codigo}}, "HeadObject")


@pytest.fixture
def s3_real():
    """O `S3Service` verdadeiro com um cliente `boto3` falseado por baixo."""
    from services.s3_storage import s3_service as servico

    cliente = ClienteBoto3Falso()
    with patch.object(servico, "s3_client", cliente), \
         patch.object(servico, "bucket_name", "bucket-de-teste"):
        yield servico, cliente


class TestGetObjectPrefix:
    def test_pede_um_RANGE_e_nao_o_objecto_inteiro(self, s3_real):
        """A mutação que sobreviveu: sem `Range`, um upload de 5 GB entra na RAM.

        A asserção é sobre o parâmetro que sai para o `boto3`, porque é a
        única coisa que distingue as duas implementações.
        """
        servico, cliente = s3_real

        servico.get_object_prefix("chave/x.pdf", 2048)

        assert len(cliente.chamadas_get) == 1
        chamada = cliente.chamadas_get[0]
        assert chamada["Range"] == "bytes=0-2047", (
            "sem o cabeçalho Range o S3 devolve o objecto completo"
        )
        assert chamada["Key"] == "chave/x.pdf"
        assert chamada["Bucket"] == "bucket-de-teste"

    def test_a_chave_vai_EXACTA_sem_variacoes(self, s3_real):
        """O `get_file_content` tenta underscore <-> espaço; esta não pode.

        Inspeccionar os bytes de uma chave e gravar outra no registo é a
        forma mais discreta de a parede não valer nada.
        """
        servico, cliente = s3_real
        chave = "Documentação Clientes/Ana Maria/Index/recibo 01.pdf"

        servico.get_object_prefix(chave, 2048)

        assert [c["Key"] for c in cliente.chamadas_get] == [chave]

    def test_objecto_vazio_416_devolve_bytes_vazios_e_nao_None(self, s3_real):
        """416 é "não há bytes nesse intervalo" — um ficheiro vazio, não uma
        falha de leitura. Devolver `None` aqui dava 503 (transitório) a um
        ficheiro que está mesmo vazio, e o cliente ficava a tentar para sempre."""
        servico, cliente = s3_real
        cliente.erro_get = _erro_cliente("InvalidRange")

        assert servico.get_object_prefix("chave/vazio.pdf", 2048) == b""

    def test_erro_de_rede_devolve_None(self, s3_real):
        servico, cliente = s3_real
        cliente.erro_get = _erro_cliente("InternalError")

        assert servico.get_object_prefix("chave/x.pdf", 2048) is None

    def test_sem_s3_configurado_devolve_None(self):
        from services.s3_storage import s3_service as servico

        with patch.object(servico, "s3_client", None):
            assert servico.get_object_prefix("x", 2048) is None

    def test_num_bytes_nao_positivo_nao_chega_a_chamar_o_s3(self, s3_real):
        servico, cliente = s3_real

        assert servico.get_object_prefix("x", 0) is None
        assert cliente.chamadas_get == []


class TestHeadObjectMetadata:
    def test_devolve_o_tamanho_e_o_tipo_REAIS(self, s3_real):
        servico, cliente = s3_real
        cliente.resposta_head = {
            "ContentLength": 987654,
            "ContentType": "image/png",
            "ETag": '"deadbeef"',
        }

        estado, meta = servico.head_object_metadata("chave/x.png")

        assert estado == "ok"
        assert meta["tamanho"] == 987654
        assert meta["tipo"] == "image/png"
        assert meta["etag"] == "deadbeef", "as aspas do ETag têm de sair"

    @pytest.mark.parametrize("codigo", ["404", "NoSuchKey", "NotFound"])
    def test_objecto_inexistente_e_AUSENTE(self, s3_real, codigo):
        """A mutação que sobreviveu: devolver "erro" aqui tornava um upload
        falhado numa falha transitória — 503 em vez de 400, e o cliente sem
        saber que tem de reenviar o ficheiro."""
        servico, cliente = s3_real
        cliente.erro_head = _erro_cliente(codigo)

        assert servico.head_object_metadata("nao/existe.pdf") == ("ausente", None)

    @pytest.mark.parametrize("codigo", ["500", "InternalError", "AccessDenied", "SlowDown"])
    def test_falha_de_infraestrutura_e_ERRO_e_nao_ausente(self, s3_real, codigo):
        """A metade oposta, e a mais importante das duas.

        "ausente" faz o chamador dizer ao cliente que o upload falhou;
        "erro" faz o chamador **não apagar nada** e devolver 503. Confundi-los
        ao contrário — dizer "ausente" a um `AccessDenied` — fazia a quarentena
        recusar um ficheiro que está lá e está bom.
        """
        servico, cliente = s3_real
        cliente.erro_head = _erro_cliente(codigo)

        assert servico.head_object_metadata("chave/x.pdf") == ("erro", None)

    def test_excepcao_inesperada_e_ERRO(self, s3_real):
        servico, cliente = s3_real
        cliente.erro_head = RuntimeError("boto3 explodiu")

        assert servico.head_object_metadata("chave/x.pdf") == ("erro", None)

    def test_sem_s3_configurado_e_ERRO_e_nao_ausente(self):
        """S3 desligado não é "o ficheiro não existe".

        Em dev o S3 está desligado; responder "ausente" diria a toda a gente
        que os uploads falharam, quando o que falta é configuração.
        """
        from services.s3_storage import s3_service as servico

        with patch.object(servico, "s3_client", None):
            assert servico.head_object_metadata("x") == ("erro", None)

    def test_a_chave_vai_EXACTA(self, s3_real):
        servico, cliente = s3_real
        chave = "Documentação Clientes/José Sá/Index/IRS 2025.pdf"

        servico.head_object_metadata(chave)

        assert [c["Key"] for c in cliente.chamadas_head] == [chave]
