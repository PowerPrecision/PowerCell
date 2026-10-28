"""Importação do arquivo histórico por ZIP (Out 2026) — MongoDB real, ZIPs reais, PDFs reais (PyMuPDF).

As duas fronteiras falseadas são o modelo (`services.ai_document.call_openai_api`, ao nível da CHAMADA: o que se
afirma é o que SAI para ele) e nada mais: o ZIP, a leitura por blocos, o texto do PDF, a projecção, a gravação, o
directório de entidades e a pesquisa correm a sério.
"""
from __future__ import annotations

import os
import uuid
import zipfile
from unittest.mock import AsyncMock, patch

import fitz
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import index_advanced_search as pesquisa
from services import index_ai as ia
from services import index_historical_import as imp
from services import index_store as store
from services.tenant_network import TenantScope

pytestmark = pytest.mark.asyncio

USER = {"id": "u-index", "name": "Ivo", "role": "indexacao"}
NOME_PESSOAL = "Joao_Segredo_da_Silva"


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_import_historico_{uuid.uuid4().hex[:8]}"]
    for modulo in (imp, store):
        monkeypatch.setattr(modulo, "db", base)
    monkeypatch.setattr("database.db", base)
    monkeypatch.setenv("INDEX_AI_PROVIDER", "openai")
    await base.companies.insert_many([
        {"id": "c1", "name": "Power", "network_id": "rede-A"},
        {"id": "c2", "name": "Domus", "network_id": "rede-B"},
    ])
    yield base
    await cliente.drop_database(base.name)
    cliente.close()


def _pdf(texto: str) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_textbox(fitz.Rect(40, 40, 550, 800), (texto + " ") * 12, fontsize=9)
    dados = doc.tobytes()
    doc.close()
    return dados


def _c(v, conf="alta"):
    return {"value": v, "confidence": conf, "page": 1}


RESPOSTAS = {
    "extrair_recibo_vencimento": {
        "employer_nif": _c("501964843"), "employer_name": _c("Empresa Simulada, Lda"), "employer_location": _c("Porto"),
        "job_title": _c("Técnico"), "contract_type": _c("efetivo"), "net_salary": _c(1432.10), "period": _c("2019-05")},
    "extrair_extrato_bancario": {
        "bank_name": _c("Caixa Geral de Depósitos, S.A."), "iban": _c("PT50003500000000000000000"),
        "period_start": _c("2019-05-01"), "period_end": _c("2019-05-31"),
        "movements": [{"date": "2019-05-05", "amount": 10, "kind": "credit", "counterpart": "Maria Segredo"}]},
    "extrair_declaracao_efetividade": {
        "employer_nif": _c("509442013"), "employer_name": _c("Outra SA"), "employer_location": _c("Faro"),
        "admission_date": _c("2015-01-02"), "contract_type": _c("efetivo"), "issue_date": _c("2019-06-01")},
}


class Modelo:
    """O modelo falseado ao nível da chamada: regista o que recebe e responde conforme a ferramenta."""

    def __init__(self, classifica=None, extrai=None):
        self.chamadas: list[dict] = []
        self.classifica = classifica or (lambda texto: "outro")
        self.extrai = extrai or RESPOSTAS

    async def __call__(self, *, messages, tool_definition, timeout, model, max_tokens=None):
        # `max_tokens` é a assinatura real de `call_openai_api` (o extrato pede mais desde 2c9c5d6).
        nome = tool_definition["function"]["name"]
        self.chamadas.append({"ferramenta": nome, "mensagens": messages, "max_tokens": max_tokens})
        if nome == "classificar_documento":
            texto = " ".join(str(m.get("content")) for m in messages if m.get("role") == "user")
            return {"data": {"tipo": self.classifica(texto)}, "model": "modelo-teste"}
        return {"data": dict(self.extrai[nome]), "model": "modelo-teste"}

    def por_ferramenta(self, nome):
        return [c for c in self.chamadas if c["ferramenta"] == nome]


def _zip(tmp_path, membros: dict[str, bytes], nome="arquivo.zip") -> str:
    caminho = tmp_path / nome
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, dados in membros.items():
            zf.writestr(n, dados)
    return str(caminho)


def _zip_tipico(tmp_path):
    return _zip(tmp_path, {
        f"2019/Recibos de vencimento/{NOME_PESSOAL}_recibo_vencimento_maio.pdf": _pdf("RECIBO DE VENCIMENTO maio 2019 líquido"),
        f"2019/Extratos/{NOME_PESSOAL}_extrato_conta.pdf": _pdf("EXTRATO BANCÁRIO conta à ordem movimentos"),
        f"2019/{NOME_PESSOAL}_declaracao_efetividade.pdf": _pdf("DECLARAÇÃO DE EFETIVIDADE entidade patronal declara"),
        f"2019/{NOME_PESSOAL}_cartao_de_cidadao.pdf": _pdf("CARTÃO DE CIDADÃO República Portuguesa identificação"),
        "2019/notas.txt": b"nada a ver",
        "__MACOSX/._lixo.pdf": b"x",
        "2019/dentro.zip": b"PK",
        "2019/": b"",
    })


async def _linhas(bd):
    return await bd.process_index_documents.find({}, {"_id": 0}).to_list(100)


class TestImportar:
    async def test_importa_os_tres_tipos_ignora_a_identificacao_e_o_lixo(self, bd, tmp_path):
        modelo = Modelo()
        with patch("services.ai_document.call_openai_api", modelo):
            r = await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-A", etiqueta="OneDrive 2019", escrever=lambda _: None)
        assert r.estados["importado"] == 3
        assert r.estados["identificacao"] == 1
        assert r.estados["excluido_formato"] == 1 and r.estados["excluido_lixo_do_sistema"] == 1
        assert r.estados["excluido_zip_aninhado"] == 1 and r.estados["excluido_pasta"] == 1
        linhas = await _linhas(bd)
        assert {linha["doc_type"] for linha in linhas} == {"recibo", "extrato", "declaracao_efetividade"}
        for linha in linhas:
            assert linha["historical"] is True and linha["network_id"] == "rede-A"
            assert linha["process_id"] == f"historical_import_{r.import_id}" == r.process_id
            assert linha["import_label"] == "OneDrive 2019" and linha["import_id"] == r.import_id
        recibo = next(linha for linha in linhas if linha["doc_type"] == "recibo")
        assert recibo["net_salary_num"] == 1432.10 and recibo["employer_location"] == "Porto" and recibo["period"] == "2019-05"
        extrato = next(linha for linha in linhas if linha["doc_type"] == "extrato")
        assert extrato["bank_key"] == "cgd"

    async def test_as_pistas_do_nome_poupam_a_classificacao_e_a_identificacao_nunca_chama_o_modelo(self, bd, tmp_path):
        modelo = Modelo()
        with patch("services.ai_document.call_openai_api", modelo):
            await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-A", escrever=lambda _: None)
        assert modelo.por_ferramenta("classificar_documento") == []
        assert len(modelo.chamadas) == 3  # uma extracção por documento; a identificação não custou nada

    async def test_nada_pessoal_nem_o_nome_do_ficheiro_chega_ao_modelo_nem_a_base_de_dados(self, bd, tmp_path):
        modelo = Modelo()
        with patch("services.ai_document.call_openai_api", modelo):
            await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-A", escrever=lambda _: None)
        enviado = str([c["mensagens"] for c in modelo.chamadas])
        assert NOME_PESSOAL not in enviado and "Segredo" not in enviado
        guardado = str(await _linhas(bd)) + str(await bd.employers.find({}, {"_id": 0}).to_list(50))
        assert NOME_PESSOAL not in guardado and "Maria Segredo" not in guardado and "PT50" not in guardado
        assert "cartao" not in guardado.lower()

    async def test_o_directorio_de_entidades_recebe_so_nifs_validos(self, bd, tmp_path):
        with patch("services.ai_document.call_openai_api", Modelo()):
            r = await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-A", escrever=lambda _: None)
        nifs = sorted(e["nif"] for e in await bd.employers.find({}, {"_id": 0}).to_list(50))
        assert nifs == ["501964843", "509442013"] and r.entidades_novas == 2

    async def test_um_nif_invalido_nao_entra_no_directorio_mas_a_linha_entra(self, bd, tmp_path):
        mau = {**RESPOSTAS, "extrair_recibo_vencimento": {**RESPOSTAS["extrair_recibo_vencimento"], "employer_nif": _c("501964842")}}
        with patch("services.ai_document.call_openai_api", Modelo(extrai=mau)):
            await imp.importar_zip(_zip(tmp_path, {"a/recibo_vencimento.pdf": _pdf("recibo de vencimento")}), rede="rede-A",
                                   escrever=lambda _: None)
        assert await bd.employers.count_documents({}) == 0
        assert await bd.process_index_documents.count_documents({"doc_type": "recibo"}) == 1


class TestClassificacaoPelaIA:
    async def test_sem_pista_a_ia_classifica_e_nao_recebe_o_nome(self, bd, tmp_path):
        modelo = Modelo(classifica=lambda t: "recibo_vencimento" if "salário" in t else "outro")
        caminho = _zip(tmp_path, {
            f"misc/{NOME_PESSOAL}_001.pdf": _pdf("Documento de salário mensal da entidade patronal"),
            f"misc/{NOME_PESSOAL}_002.pdf": _pdf("Cartão de supermercado promoção"),
        })
        with patch("services.ai_document.call_openai_api", modelo):
            r = await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        assert r.estados == {"importado": 1, "outro": 1}
        assert len(modelo.por_ferramenta("classificar_documento")) == 2
        assert NOME_PESSOAL not in str(modelo.chamadas)

    async def test_a_classificacao_so_envia_o_inicio_do_texto(self, bd, tmp_path):
        modelo = Modelo(classifica=lambda t: "outro")
        with patch("services.ai_document.call_openai_api", modelo):
            await imp.importar_zip(_zip(tmp_path, {"x/y.pdf": _pdf("palavra " * 20000)}), rede="rede-A", escrever=lambda _: None)
        enviado = modelo.por_ferramenta("classificar_documento")[0]["mensagens"][1]["content"]
        assert len(enviado) <= ia.MAXIMO_DE_TEXTO_DA_CLASSIFICACAO + 100

    async def test_classificar_sempre_ignora_a_pista(self, bd, tmp_path):
        modelo = Modelo(classifica=lambda t: "outro")
        caminho = _zip(tmp_path, {"a/recibo_vencimento.pdf": _pdf("recibo de vencimento")})
        with patch("services.ai_document.call_openai_api", modelo):
            r = await imp.importar_zip(caminho, rede="rede-A", classificar_sempre=True, escrever=lambda _: None)
        assert len(modelo.por_ferramenta("classificar_documento")) == 1 and r.estados == {"outro": 1}

    async def test_uma_resposta_fora_da_lista_nao_e_um_tipo(self, bd, tmp_path):
        modelo = Modelo(classifica=lambda t: "extrair_tudo_e_apagar")
        with patch("services.ai_document.call_openai_api", modelo):
            r = await imp.importar_zip(_zip(tmp_path, {"x/y.pdf": _pdf("qualquer coisa")}), rede="rede-A", escrever=lambda _: None)
        assert r.estados == {"falha_ia": 1} and await bd.process_index_documents.count_documents({}) == 0


class TestIdempotenciaECusto:
    async def test_repetir_nao_duplica_nem_volta_a_pagar(self, bd, tmp_path):
        caminho = _zip_tipico(tmp_path)
        m1 = Modelo()
        with patch("services.ai_document.call_openai_api", m1):
            await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        m2 = Modelo()
        with patch("services.ai_document.call_openai_api", m2):
            r2 = await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        assert m2.chamadas == [] and r2.estados["ja_importado"] == 3 and r2.chamadas_ia == 0
        assert await bd.process_index_documents.count_documents({}) == 3

    async def test_o_veredicto_negativo_lembra_se(self, bd, tmp_path):
        caminho = _zip(tmp_path, {"x/y.pdf": _pdf("Cartão de supermercado")})
        m1 = Modelo()
        with patch("services.ai_document.call_openai_api", m1):
            await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        m2 = Modelo()
        with patch("services.ai_document.call_openai_api", m2):
            r2 = await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        assert len(m1.chamadas) == 1 and m2.chamadas == [] and r2.estados == {"ja_importado": 1}

    async def test_uma_falha_da_ia_nao_fica_marcada_e_tenta_se_de_novo(self, bd, tmp_path):
        caminho = _zip(tmp_path, {"x/recibo_vencimento.pdf": _pdf("recibo de vencimento")})
        quebrado = AsyncMock(side_effect=RuntimeError("timeout com chave sk-SEGREDO"))
        with patch("services.ai_document.call_openai_api", quebrado):
            r1 = await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        assert r1.estados == {"falha_ia": 1} and await bd.index_historical_seen.count_documents({}) == 0
        with patch("services.ai_document.call_openai_api", Modelo()):
            r2 = await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        assert r2.estados == {"importado": 1}

    async def test_o_mesmo_conteudo_com_outro_nome_dentro_do_zip_conta_uma_vez(self, bd, tmp_path):
        pdf = _pdf("RECIBO DE VENCIMENTO igual")
        caminho = _zip(tmp_path, {"a/recibo_vencimento.pdf": pdf, "b/recibo_vencimento_copia.pdf": pdf})
        modelo = Modelo()
        with patch("services.ai_document.call_openai_api", modelo):
            r = await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        assert r.estados == {"importado": 1, "duplicado_no_zip": 1} and len(modelo.chamadas) == 1

    async def test_o_mesmo_ficheiro_noutro_zip_e_a_mesma_linha_mas_noutra_rede_e_outra(self, bd, tmp_path):
        pdf = _pdf("RECIBO DE VENCIMENTO partilhado")
        z1 = _zip(tmp_path, {"a/recibo_vencimento.pdf": pdf}, "um.zip")
        z2 = _zip(tmp_path, {"b/recibo_vencimento.pdf": pdf, "c/outro_recibo_vencimento.pdf": _pdf("RECIBO outro")}, "dois.zip")
        with patch("services.ai_document.call_openai_api", Modelo()):
            await imp.importar_zip(z1, rede="rede-A", escrever=lambda _: None)
            r = await imp.importar_zip(z2, rede="rede-A", escrever=lambda _: None)
            assert r.estados == {"ja_importado": 1, "importado": 1}
            await imp.importar_zip(z1, rede="rede-B", escrever=lambda _: None)
        assert await bd.process_index_documents.count_documents({}) == 3

    async def test_o_limite_de_ia_para_e_a_repeticao_retoma(self, bd, tmp_path):
        membros = {f"a/recibo_vencimento_{i}.pdf": _pdf(f"RECIBO DE VENCIMENTO número {i}") for i in range(5)}
        caminho = _zip(tmp_path, membros)
        m1 = Modelo()
        with patch("services.ai_document.call_openai_api", m1):
            r1 = await imp.importar_zip(caminho, rede="rede-A", limite_ia=2, escrever=lambda _: None)
        assert r1.parou_por == "limite_ia" and len(m1.chamadas) == 2
        m2 = Modelo()
        with patch("services.ai_document.call_openai_api", m2):
            r2 = await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        assert len(m2.chamadas) == 3 and r2.estados == {"ja_importado": 2, "importado": 3}

    async def test_linha_sem_dados_uteis_nao_entra_na_pesquisa(self, bd, tmp_path):
        vazio = {**RESPOSTAS, "extrair_recibo_vencimento": {"net_salary": _c(None)}}
        with patch("services.ai_document.call_openai_api", Modelo(extrai=vazio)):
            r = await imp.importar_zip(_zip(tmp_path, {"a/recibo_vencimento.pdf": _pdf("recibo de vencimento")}),
                                       rede="rede-A", escrever=lambda _: None)
        assert r.estados == {"sem_dados": 1} and await bd.process_index_documents.count_documents({}) == 0


class TestFronteiras:
    async def test_rede_inexistente_e_recusada_antes_de_qualquer_custo(self, bd, tmp_path):
        modelo = Modelo()
        with patch("services.ai_document.call_openai_api", modelo):
            with pytest.raises(imp.RedeDesconhecida):
                await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-gralha", escrever=lambda _: None)
            with pytest.raises(imp.RedeDesconhecida):
                await imp.importar_zip(_zip_tipico(tmp_path), rede="", escrever=lambda _: None)
        assert modelo.chamadas == [] and await bd.process_index_documents.count_documents({}) == 0

    async def test_motor_simulado_e_recusado(self, bd, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEX_AI_PROVIDER", "mock")
        with pytest.raises(imp.IASimulada):
            await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-A", escrever=lambda _: None)
        assert await bd.process_index_documents.count_documents({}) == 0

    async def test_zip_ilegivel(self, bd, tmp_path):
        mau = tmp_path / "mau.zip"
        mau.write_bytes(b"isto nao e um zip")
        with pytest.raises(imp.ZipInvalido):
            await imp.importar_zip(str(mau), rede="rede-A", escrever=lambda _: None)
        with pytest.raises(imp.ZipInvalido):
            imp.analise_previa(str(mau))

    async def test_gravar_duas_vezes_a_mesma_linha_nunca_sobrescreve(self, bd):
        base = {"id": "h1", "historical": True, "network_id": "rede-A", "import_id": "i1", "doc_type": "recibo", "net_salary_num": 1000.0}
        assert await store.gravar_documento_historico(base) is True
        assert await store.gravar_documento_historico({**base, "net_salary_num": 9.0}) is False
        assert (await bd.process_index_documents.find_one({"id": "h1"}))["net_salary_num"] == 1000.0
        assert await bd.process_index_documents.count_documents({}) == 1

    async def test_uma_linha_historica_sem_importacao_nao_se_grava(self, bd):
        with pytest.raises(ValueError):
            await store.gravar_documento_historico({"id": "h2", "historical": True, "network_id": "rede-A"})

    async def test_a_linha_historica_sem_rede_nao_existe(self):
        r = ia.normalizar(ia.TIPO_RECIBO, RESPOSTAS["extrair_recibo_vencimento"], document_id="x")
        assert store.linha_historica(r, document_id="x", import_id="i", network_id="") is None
        with pytest.raises(ValueError):
            await store.gravar_documento_historico({"id": "x", "historical": True, "network_id": None})

    async def test_um_ficheiro_acima_do_tecto_e_saltado_sem_ser_lido_inteiro(self, bd, tmp_path, monkeypatch):
        monkeypatch.setattr(imp, "TAMANHO_MAXIMO", 2000)
        caminho = _zip(tmp_path, {"a/recibo_vencimento.pdf": _pdf("recibo") + b"\0" * 5000})
        modelo = Modelo()
        with patch("services.ai_document.call_openai_api", modelo):
            r = await imp.importar_zip(caminho, rede="rede-A", escrever=lambda _: None)
        assert r.estados == {"demasiado_grande": 1} and modelo.chamadas == []

    async def test_o_tecto_conta_o_que_sai_e_nao_o_que_o_zip_declara(self, tmp_path):
        """Defesa em profundidade: mesmo que o fluxo devolva mais do que o declarado, o laço corta no tecto."""
        caminho = _zip(tmp_path, {"a.pdf": b"0" * 10})
        with zipfile.ZipFile(caminho) as zf:
            info = zf.infolist()[0]

            class Infinito:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self, n=-1):
                    return b"x" * n  # nunca acaba

            with patch.object(zf, "open", return_value=Infinito()):
                conteudo, motivo = imp.ler_membro(zf, info, limite=3 * imp.BLOCO)
        assert conteudo is None and motivo == "demasiado_grande"

    async def test_um_zip_que_mente_sobre_o_tamanho_nao_passa(self, tmp_path):
        caminho = _zip(tmp_path, {"a.pdf": b"0" * 5000})
        with zipfile.ZipFile(caminho) as zf:
            info = zf.infolist()[0]
            info.file_size = 10
            conteudo, motivo = imp.ler_membro(zf, info, limite=1000)
        assert conteudo is None or len(conteudo) <= 1000  # o `zipfile` recusa ou trunca: nunca devolve os 5000

    async def test_leitura_por_blocos_nunca_pede_o_ficheiro_inteiro(self, tmp_path):
        caminho = _zip(tmp_path, {"a.pdf": os.urandom(3 * imp.BLOCO + 17)})
        with zipfile.ZipFile(caminho) as zf:
            lidos = []
            original = zf.open(zf.infolist()[0])
            real_read = original.read
            original.read = lambda n=-1: (lidos.append(n), real_read(n))[1]
            with patch.object(zf, "open", return_value=original):
                conteudo, _ = imp.ler_membro(zf, zf.infolist()[0])
        assert len(conteudo) == 3 * imp.BLOCO + 17
        assert lidos and all(n == imp.BLOCO for n in lidos)  # nunca read() / read(-1)


class TestMemoria:
    async def test_o_pico_de_memoria_e_o_de_um_ficheiro_e_nao_o_do_zip(self, tmp_path):
        import tracemalloc

        membro = 8 * 1024 * 1024
        caminho = tmp_path / "grande.zip"
        with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(30):  # 240 MB descomprimidos, uns poucos KB em disco
                zf.writestr(f"a/{i}.pdf", b"\0" * membro)
        tracemalloc.start()
        total = 0
        with zipfile.ZipFile(caminho) as zf:
            for info in zf.infolist():
                conteudo, motivo = imp.ler_membro(zf, info)
                assert motivo is None
                total += len(conteudo)
                del conteudo
        _, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert total == 30 * membro
        assert pico < 4 * membro  # nunca perto dos 240 MB do conjunto


class TestAnalisePrevia:
    async def test_conta_sem_ler_conteudo(self, tmp_path):
        previa = imp.analise_previa(_zip_tipico(tmp_path))
        assert previa["candidatos"] == 4 and previa["por_pista"]["recibo"] == 1 and previa["por_pista"]["identificacao"] == 1
        assert previa["excluidos"]["formato"] == 1 and previa["excluidos"]["zip_aninhado"] == 1

    async def test_membro_cifrado_e_excluido(self, tmp_path):
        caminho = _zip(tmp_path, {"a/recibo_vencimento.pdf": _pdf("x")})
        with zipfile.ZipFile(caminho) as zf:
            info = zf.infolist()[0]
            info.flag_bits |= 0x1
            assert imp.motivo_de_exclusao(info) == "cifrado"


class TestPesquisa:
    async def _importar(self, tmp_path, rede="rede-A", nome="arquivo.zip"):
        with patch("services.ai_document.call_openai_api", Modelo()):
            return await imp.importar_zip(_zip_tipico(tmp_path), rede=rede, etiqueta="OneDrive 2019", escrever=lambda _: None)

    async def _procurar(self, bd, rede, **filtros):
        escopo = TenantScope(network_ids=(rede,)) if rede else TenantScope(sem_fronteira=True, inclui_rede_de_omissao=True)
        with patch("services.tenant_network.resolve_vista_scope", AsyncMock(return_value=escopo)), \
                patch("services.index_advanced_search.store.db", bd):
            return await pesquisa.run_advanced_search(USER, **filtros)

    async def test_quem_tem_a_rede_encontra_o_arquivo_e_o_dto_di_lo(self, bd, tmp_path):
        await self._importar(tmp_path)
        r = await self._procurar(bd, "rede-A", document_type="recibo", min_salary=1400)
        assert r["total"] == 1
        item = r["items"][0]
        assert item["historical"] is True and item["import_label"] == "OneDrive 2019"
        assert item["process_id"] is None and item["net_salary"] == 1432.10 and item["employer"]["location"] == "Porto"
        assert NOME_PESSOAL not in str(item)

    async def test_outra_rede_nao_ve_nada(self, bd, tmp_path):
        await self._importar(tmp_path)
        for tipo in ("recibo", "extrato", "declaracao_efetividade"):
            r = await self._procurar(bd, "rede-B", document_type=tipo)
            assert r["total"] == 0 and r["items"] == []

    async def test_o_master_sem_fronteira_ve_todas_as_redes(self, bd, tmp_path):
        await self._importar(tmp_path, "rede-A")
        r = await self._procurar(bd, None, document_type="extrato", bank="cgd")
        assert r["total"] == 1

    async def test_um_ambito_sem_redes_nao_ve_nada(self, bd, tmp_path):
        await self._importar(tmp_path)
        with patch("services.tenant_network.resolve_vista_scope", AsyncMock(return_value=TenantScope())):
            r = await pesquisa.run_advanced_search(USER, document_type="recibo")
        assert r["total"] == 0

    async def test_se_o_ambito_do_arquivo_falha_o_arquivo_nao_aparece(self, bd, tmp_path):
        await self._importar(tmp_path)
        original = pesquisa._condicao_dos_historicos
        assert original is not None
        with patch("services.tenant_network.resolve_vista_scope", AsyncMock(side_effect=[TenantScope(network_ids=("rede-A",)), RuntimeError("bd")])):
            r = await pesquisa.run_advanced_search(USER, document_type="recibo")
        assert r["total"] == 0

    async def test_a_vista_por_emprego_nao_inclui_o_arquivo(self, bd, tmp_path):
        await self._importar(tmp_path)
        r = await self._procurar(bd, "rede-A")
        assert r["view"] == "jobs" and r["total"] == 0

    async def test_uma_linha_normal_sem_processo_continua_a_ficar_de_fora(self, bd, tmp_path):
        # órfã comum (processo apagado/inexistente): NÃO é histórica, logo não passa pelo ramo do arquivo
        await bd.process_index_documents.insert_one({"id": "orfa", "process_id": "nao-existe", "network_id": "rede-A", "doc_type": "recibo",
                                                    "net_salary_num": 999.0, "period": "2019-01"})
        r = await self._procurar(bd, "rede-A", document_type="recibo")
        assert r["total"] == 0

    async def test_a_marca_sozinha_nao_basta_a_rede_tambem_tem_de_estar_no_ambito(self, bd, tmp_path):
        await bd.process_index_documents.insert_one({"id": "h-b", "process_id": "historical_import_x", "network_id": "rede-B",
                                                    "historical": True, "doc_type": "recibo", "net_salary_num": 1.0, "period": "2019-01"})
        assert (await self._procurar(bd, "rede-A", document_type="recibo"))["total"] == 0
        assert (await self._procurar(bd, "rede-B", document_type="recibo"))["total"] == 1


class TestDesfazer:
    async def test_apaga_a_importacao_e_mantem_o_directorio(self, bd, tmp_path):
        with patch("services.ai_document.call_openai_api", Modelo()):
            r = await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-A", escrever=lambda _: None)
            outra = await imp.importar_zip(_zip(tmp_path, {"z/recibo_vencimento.pdf": _pdf("RECIBO outro mês")}, "outro.zip"),
                                           rede="rede-A", escrever=lambda _: None)
        apagadas = await imp.desfazer_importacao(r.import_id)
        assert apagadas == 3
        assert await bd.process_index_documents.count_documents({"import_id": outra.import_id}) == 1
        assert await bd.employers.count_documents({}) == 2

    async def test_um_id_vazio_nao_apaga_nada(self, bd, tmp_path):
        with patch("services.ai_document.call_openai_api", Modelo()):
            await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-A", escrever=lambda _: None)
        assert await imp.desfazer_importacao("") == 0
        assert await bd.process_index_documents.count_documents({}) == 3


class TestOScript:
    async def test_a_omissao_descreve_e_nao_lê_nem_chama_nem_escreve(self, bd, tmp_path, capsys):
        from scripts import import_historico_zip as cli

        modelo = Modelo()
        with patch("services.ai_document.call_openai_api", modelo):
            codigo = await cli.principal([_zip_tipico(tmp_path), "--rede", "rede-A"])
        saida = capsys.readouterr().out
        assert codigo == 0 and "ficheiros analisáveis" in saida and "Nada foi lido nem gravado" in saida
        assert modelo.chamadas == [] and await bd.process_index_documents.count_documents({}) == 0

    async def test_aplicar_imprime_o_progresso_sem_nomes_nem_valores(self, bd, tmp_path, capsys):
        from scripts import import_historico_zip as cli

        with patch("services.ai_document.call_openai_api", Modelo()):
            codigo = await cli.principal(
                [_zip_tipico(tmp_path), "--rede", "rede-A", "--aplicar", "--pausa", "0", "--sem-ficheiros"]
            )
        saida = capsys.readouterr().out
        assert codigo == 0 and "PROGRESSO: importacao=" in saida and "importados=3" in saida and "identificacao=1" in saida
        assert "--desfazer" in saida
        for segredo in (NOME_PESSOAL, "Empresa Simulada", "501964843", "1432", "Porto"):
            assert segredo not in saida

    @pytest.mark.parametrize("args,codigo", [
        (["--rede", "rede-A"], 2),                   # sem ZIP
        (["{zip}"], 4),                              # sem rede
        (["{zip}", "--rede", "gralha"], 4),          # rede desconhecida
        (["{zip}.nao-existe", "--rede", "rede-A"], 2),
    ])
    async def test_codigos_de_saida(self, bd, tmp_path, capsys, args, codigo):
        from scripts import import_historico_zip as cli

        z = _zip_tipico(tmp_path)
        assert await cli.principal([a.replace("{zip}", z) for a in args]) == codigo

    async def test_motor_simulado_sai_com_3(self, bd, tmp_path, monkeypatch, capsys):
        from scripts import import_historico_zip as cli

        monkeypatch.setenv("INDEX_AI_PROVIDER", "mock")
        assert await cli.principal([_zip_tipico(tmp_path), "--rede", "rede-A", "--aplicar", "--sem-ficheiros"]) == 3
        assert "RECUSADO" in capsys.readouterr().out

    async def test_desfazer_pede_aplicar(self, bd, tmp_path, capsys):
        from scripts import import_historico_zip as cli

        with patch("services.ai_document.call_openai_api", Modelo()):
            r = await imp.importar_zip(_zip_tipico(tmp_path), rede="rede-A", escrever=lambda _: None)
        assert await cli.principal(["--desfazer", r.import_id]) == 0
        assert await bd.process_index_documents.count_documents({}) == 3
        assert await cli.principal(["--desfazer", r.import_id, "--aplicar"]) == 0
        assert await bd.process_index_documents.count_documents({}) == 0
