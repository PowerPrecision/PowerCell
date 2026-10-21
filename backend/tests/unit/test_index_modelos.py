"""Modelos do módulo Index (Lote 12, Fase 1): campos revisáveis, NIF, alertas, entidades."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from models.index_module import (
    ALERTAS,
    CATEGORIA_IDENTIFICACAO,
    AlertaDaMatriz,
    CampoRevisavel,
    Entidade,
    EstadoDoFicheiro,
    ProfessionalMetadata,
    TrabalhoProfissional,
    decimal_do_valor,
    nif_e_valido,
    normalizar_nif,
)

NIF_OK = "501964843"
NIF_MAL = "518789370"  # dígito de controlo errado


class TestCampoRevisavel:
    def test_sem_valor_e_sempre_a_rever(self):
        assert CampoRevisavel[str](value=None, needs_review=False).needs_review is True
        assert CampoRevisavel[str]().needs_review is True

    @pytest.mark.parametrize("vazio", ["", "   ", "\n"])
    def test_texto_vazio_e_nada(self, vazio):
        c = CampoRevisavel[str](value=vazio)
        assert c.value is None and c.needs_review is True

    def test_valor_presente_nao_e_a_rever_por_omissao(self):
        c = CampoRevisavel[str](value="Acme", confidence="alta")
        assert c.needs_review is False

    def test_valor_presente_pode_vir_marcado_a_rever(self):
        assert CampoRevisavel[str](value="Acme", needs_review=True).needs_review is True

    def test_vazio_de_proposito_por_uma_pessoa_ja_foi_revisto(self):
        # uma pessoa limpou o campo: não volta a ser «a rever» por estar vazio
        c = CampoRevisavel[str](value=None, edited_by_human=True)
        assert c.needs_review is False

    def test_o_zero_e_um_valor(self):
        c = CampoRevisavel[Decimal](value=Decimal("0"))
        assert c.value == 0 and c.needs_review is False

    def test_nao_aceita_campos_extra(self):
        with pytest.raises(ValidationError):
            CampoRevisavel[str](value="x", texto_lido="NUNCA se guarda o texto do documento")

    def test_a_fonte_so_leva_documento_e_pagina(self):
        with pytest.raises(ValidationError):
            CampoRevisavel[str](value="x", source={"document_id": "d", "page": 1, "text": "lixo"})
        with pytest.raises(ValidationError):
            CampoRevisavel[str](value="x", source={"document_id": "d", "page": 0})


class TestNif:
    def test_normalizar(self):
        assert normalizar_nif("PT 501 964 843") == "501964843"
        assert normalizar_nif("abc") is None and normalizar_nif(None) is None

    def test_validar_o_digito_de_controlo(self):
        assert nif_e_valido(NIF_OK) and not nif_e_valido(NIF_MAL)
        assert not nif_e_valido("12345") and not nif_e_valido(None) and not nif_e_valido("")

    def test_a_regra_e_a_do_projecto(self):
        # contraprova de que não há uma segunda implementação: concorda com `utils.validation`
        from utils.validation import validate_nif

        for n in (NIF_OK, NIF_MAL, "123456789", "000000000", "999999990"):
            assert nif_e_valido(n) is validate_nif(n)[0]

    def test_o_codigo_reforca_a_ia_nif_invalido_vai_a_rever(self):
        # a IA diz que está seguro; o dígito de controlo diz que não
        t = TrabalhoProfissional(
            job_id="j1", employer_nif=CampoRevisavel[str](value=NIF_MAL, confidence="alta", needs_review=False)
        )
        assert t.employer_nif.needs_review is True
        assert t.employer_nif.value == NIF_MAL  # o valor não se apaga: a pessoa vê o que a IA leu

    def test_nif_valido_nao_e_a_rever(self):
        t = TrabalhoProfissional(job_id="j1", employer_nif=CampoRevisavel[str](value="PT501 964 843"))
        assert t.employer_nif.value == NIF_OK and t.employer_nif.needs_review is False

    def test_texto_sem_digitos_vai_a_nulo_e_a_rever(self):
        t = TrabalhoProfissional(job_id="j1", employer_nif=CampoRevisavel[str](value="sem nif"))
        assert t.employer_nif.value is None and t.employer_nif.needs_review is True

    def test_nif_corrigido_por_pessoa_invalido_continua_a_rever(self):
        # o código reforça sempre — `edited_by_human` blinda contra a IA, não contra o dígito de controlo
        t = TrabalhoProfissional(
            job_id="j", employer_nif=CampoRevisavel[str](value=NIF_MAL, edited_by_human=True)
        )
        assert t.employer_nif.needs_review is True


class TestTrabalhoEMetadados:
    def test_um_trabalho_vazio_tem_tudo_a_rever(self):
        t = TrabalhoProfissional(job_id="j1")
        assert set(t.campos_a_rever()) == {
            "employer_nif", "employer_name", "job_title", "net_salary", "contract_type",
        }

    def test_ordenado_em_decimal_nunca_float(self):
        t = TrabalhoProfissional(job_id="j1", net_salary=CampoRevisavel[Decimal](value="1234.56"))
        assert isinstance(t.net_salary.value, Decimal) and t.net_salary.value == Decimal("1234.56")

    def test_tipo_de_contrato_fechado(self):
        with pytest.raises(ValidationError):
            TrabalhoProfissional(job_id="j", contract_type=CampoRevisavel(value="vitalício"))
        t = TrabalhoProfissional(job_id="j", contract_type=CampoRevisavel(value="efetivo"))
        assert t.contract_type.value == "efetivo"

    @pytest.mark.parametrize("p", ["2026-13", "26-10", "2026/10", "outubro"])
    def test_periodo_invalido(self, p):
        with pytest.raises(ValidationError):
            TrabalhoProfissional(job_id="j", period=p)

    def test_periodo_valido(self):
        assert TrabalhoProfissional(job_id="j", period="2026-10").period == "2026-10"

    def test_has_pending_review_deriva_dos_campos(self):
        completo = TrabalhoProfissional(
            job_id="j1",
            employer_nif=CampoRevisavel[str](value=NIF_OK),
            employer_name=CampoRevisavel[str](value="Acme, Lda"),
            job_title=CampoRevisavel[str](value="Técnico"),
            net_salary=CampoRevisavel[Decimal](value="1000"),
            contract_type=CampoRevisavel(value="efetivo"),
        )
        assert completo.campos_a_rever() == []
        limpo = ProfessionalMetadata(process_id="p", jobs=[completo])
        assert limpo.has_pending_review is False
        sujo = ProfessionalMetadata(process_id="p", jobs=[completo, TrabalhoProfissional(job_id="j2")])
        assert sujo.has_pending_review is True

    def test_has_pending_review_nao_se_declara_a_mao(self):
        # um valor passado à mão é recalculado: uma flag declarada diverge dos campos
        m = ProfessionalMetadata(process_id="p", jobs=[TrabalhoProfissional(job_id="j")], has_pending_review=False)
        assert m.has_pending_review is True

    def test_sem_trabalhos_nao_ha_nada_a_rever(self):
        assert ProfessionalMetadata(process_id="p").has_pending_review is False

    def test_nao_aceita_campos_pessoais_extra(self):
        with pytest.raises(ValidationError):
            ProfessionalMetadata(process_id="p", client_name="Ana")
        with pytest.raises(ValidationError):
            TrabalhoProfissional(job_id="j", nif_do_cliente="123")


class TestDecimalDoValor:
    @pytest.mark.parametrize(
        "bruto, esperado",
        [
            (1234.5, Decimal("1234.5")),
            ("1234.56", Decimal("1234.56")),
            ("1.234,56", Decimal("1234.56")),
            ("1,234.56", Decimal("1234.56")),
            ("1234,56 €", Decimal("1234.56")),
            ("€ 950", Decimal("950")),
            (0, Decimal("0")),
            (Decimal("10"), Decimal("10")),
        ],
    )
    def test_valores(self, bruto, esperado):
        assert decimal_do_valor(bruto) == esperado

    @pytest.mark.parametrize("bruto", [None, True, "", "abc", "—", float("nan"), float("inf"), "1.2.3.4"])
    def test_o_que_nao_e_numero_e_nulo(self, bruto):
        assert decimal_do_valor(bruto) is None


class TestEntidade:
    def test_valida_e_normaliza(self):
        e = Entidade(nif="PT 501 964 843", name="  Acme   Lda ")
        assert e.nif == NIF_OK and e.name == "Acme Lda"

    def test_recusa_nif_invalido_e_nome_vazio(self):
        with pytest.raises(ValidationError):
            Entidade(nif=NIF_MAL, name="Acme")
        with pytest.raises(ValidationError):
            Entidade(nif=NIF_OK, name="   ")

    def test_sem_referencias_a_clientes_ou_processos(self):
        for campo in ("process_id", "client_id", "network_id", "salary"):
            with pytest.raises(ValidationError):
                Entidade(nif=NIF_OK, name="Acme", **{campo: "x"})


class TestAlertas:
    def test_codigo_fora_da_tabela_nao_existe(self):
        with pytest.raises(ValidationError):
            AlertaDaMatriz(id="a", process_id="p", code="inventado", run_id="r")

    def test_severidade_e_mensagem_vem_da_tabela_nunca_do_pedido(self):
        a = AlertaDaMatriz(
            id="a", process_id="p", code="nif_invalido", run_id="r",
            severity="info", message="o cliente é um burlão",
        )
        assert a.severity == ALERTAS["nif_invalido"][0] == "alerta"
        assert a.message == ALERTAS["nif_invalido"][1]
        assert "burlão" not in a.message

    def test_nenhum_alerta_diz_bloquear(self):
        # o princípio 1 («zero bloqueios») é uma propriedade da tabela
        for codigo, (sev, msg) in ALERTAS.items():
            assert sev in {"info", "aviso", "alerta"}, codigo
            assert not any(p in msg.lower() for p in ("bloque", "impede", "não pode ser indexado")), codigo

    def test_mensagens_nao_levam_dados_pessoais(self):
        for codigo, (_, msg) in ALERTAS.items():
            assert "{" not in msg and "%" not in msg, codigo  # sem espaços para interpolar valores

    def test_tabela_cobre_o_que_a_arquitectura_promete(self):
        prometidos = {
            "recibo_sem_credito", "contas_nao_batem", "nif_invalido", "nif_entidade_incoerente",
            "movimento_estranho", "recibo_irreal", "identificacao_expirada", "identificacao_ilegivel",
            "sanitizacao_falhou",
        }
        assert prometidos <= set(ALERTAS)


class TestEstadoDoFicheiro:
    def test_subtipo_de_identificacao_forca_a_categoria_unica(self):
        for sub in ("cc", "bi", "passaporte", "titulo_residencia"):
            e = EstadoDoFicheiro(ai_subtype=sub, ai_category="Outros")
            assert e.ai_category == CATEGORIA_IDENTIFICACAO == "Identificação"

    def test_subtipo_desconhecido_recusado(self):
        with pytest.raises(ValidationError):
            EstadoDoFicheiro(ai_subtype="carta_conducao")

    def test_estado_por_omissao_e_original(self):
        e = EstadoDoFicheiro()
        assert e.file_state == "original" and e.clean_pdf_path is None

    def test_estados_fechados(self):
        with pytest.raises(ValidationError):
            EstadoDoFicheiro(file_state="apagado")
