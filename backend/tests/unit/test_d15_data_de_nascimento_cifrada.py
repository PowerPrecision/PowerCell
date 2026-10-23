"""D-15 — a data de nascimento vive cifrada e o ANO fica ao lado, em claro.

Tudo corre sobre as funções de PRODUÇÃO (as quatro que cifram, a regra Sub35 e
os escritores pontuados): nenhum duplo reimplementa a cifra nem a idade.
"""
from __future__ import annotations

import copy
import inspect
from datetime import date, datetime

import pytest

from services import campos_limpaveis, nascimento_protegido as np_
from services import portal_profile_sections, process_ai_conflict, sub35
from services import encryption as enc
from services.birthdate_migration import planear
from services.encryption import (
    CAMPOS_DE_NASCIMENTO_CIFRADOS,
    CLIENT_SENSITIVE_FIELDS,
    SENSITIVE_FIELDS,
    decrypt_client_data,
    encrypt_client_data,
    encryption_service,
    is_encrypted,
)
from services.process_service import decrypt_sensitive_data, encrypt_sensitive_data

from .helpers_fonte import codigo_da_funcao_sem_comentarios

HOJE = date(2026, 10, 2)


def _processo(**pessoa):
    return {
        "id": "p1",
        "personal_data": dict(pessoa),
        "titular2_data": {"name": "", "nif": "", "birth_date": "", "data_nascimento": ""},
        "co_buyers": [{"nome": "Ana", "birth_date": "2001-07-01", "data_nascimento": "2001-07-01"}],
        "birth_date": "1980-05-05",
    }


def _encrypt_process_do_servico(doc):
    return encryption_service.encrypt_process(doc)


ESCRITORES_DE_PROCESSO = [
    pytest.param(encrypt_sensitive_data, id="process_service.encrypt_sensitive_data"),
    pytest.param(_encrypt_process_do_servico, id="EncryptionService.encrypt_process"),
]


class TestAsListasConcordam:
    def test_os_dois_nomes_sao_um_so_objecto(self):
        # `sub35` decide a idade, `encryption` cifra: duas listas à mão divergiriam.
        assert sub35.CAMPOS_DE_NASCIMENTO is CAMPOS_DE_NASCIMENTO_CIFRADOS
        assert set(CAMPOS_DE_NASCIMENTO_CIFRADOS) == {"birth_date", "data_nascimento"}

    @pytest.mark.parametrize("seccao", ["personal_data", "titular2_data", "co_buyers", "co_applicants", "root"])
    def test_as_listas_de_processo_cifram_os_dois_nomes(self, seccao):
        assert set(CAMPOS_DE_NASCIMENTO_CIFRADOS) <= set(SENSITIVE_FIELDS[seccao])

    @pytest.mark.parametrize("seccao", ["dados_pessoais", "titular2_data"])
    def test_as_listas_de_cliente_cifram_os_dois_nomes(self, seccao):
        assert set(CAMPOS_DE_NASCIMENTO_CIFRADOS) <= set(CLIENT_SENSITIVE_FIELDS[seccao])


class TestACifraCentral:
    @pytest.mark.parametrize("cifrar", ESCRITORES_DE_PROCESSO)
    def test_o_processo_sai_cifrado_com_o_ano_ao_lado(self, cifrar):
        saida = cifrar(copy.deepcopy(_processo(birth_date="1995-03-15", data_nascimento="1995-03-15")))
        pd = saida["personal_data"]
        for campo in CAMPOS_DE_NASCIMENTO_CIFRADOS:
            assert is_encrypted(pd[campo]), campo
            assert "1995" not in pd[campo]
        assert pd["birth_year"] == 1995
        assert is_encrypted(saida["birth_date"]) and saida["birth_year"] == 1980   # a raiz (processos antigos)
        (comprador,) = saida["co_buyers"]
        assert is_encrypted(comprador["birth_date"]) and comprador["birth_year"] == 2001

    @pytest.mark.parametrize("cifrar", ESCRITORES_DE_PROCESSO)
    def test_o_ano_e_um_inteiro_e_so_o_ano_esta_em_claro(self, cifrar):
        saida = cifrar(copy.deepcopy(_processo(birth_date="1995-03-15")))
        assert type(saida["personal_data"]["birth_year"]) is int
        assert "1995-03-15" not in repr(saida)
        assert "2001-07-01" not in repr(saida)

    def test_o_segundo_titular_e_o_cliente_tambem(self):
        proc = encrypt_sensitive_data({"titular2_data": {"nif": "x", "data_nascimento": "1990-01-02"}})
        assert is_encrypted(proc["titular2_data"]["data_nascimento"]) and proc["titular2_data"]["birth_year"] == 1990
        cli = encrypt_client_data({
            "dados_pessoais": {"data_nascimento": "1999-12-31"},
            "titular2_data": {"birth_date": "1988-08-08"},
        })
        assert is_encrypted(cli["dados_pessoais"]["data_nascimento"]) and cli["dados_pessoais"]["birth_year"] == 1999
        assert is_encrypted(cli["titular2_data"]["birth_date"]) and cli["titular2_data"]["birth_year"] == 1988

    def test_a_ida_e_volta_devolve_a_data_original(self):
        original = _processo(birth_date="1995-03-15", data_nascimento="1995-03-15")
        volta = decrypt_sensitive_data(encrypt_sensitive_data(copy.deepcopy(original)))
        assert volta["personal_data"]["birth_date"] == "1995-03-15"
        assert volta["co_buyers"][0]["data_nascimento"] == "2001-07-01"
        assert volta["birth_date"] == "1980-05-05"
        cli = decrypt_client_data(encrypt_client_data({"dados_pessoais": {"data_nascimento": "1999-12-31"}}))
        assert cli["dados_pessoais"]["data_nascimento"] == "1999-12-31"

    def test_um_datetime_do_bson_cifra_a_data_e_nao_a_hora(self):
        saida = encrypt_sensitive_data({"personal_data": {"birth_date": datetime(1992, 2, 2, 0, 0)}})
        assert saida["personal_data"]["birth_year"] == 1992
        assert decrypt_sensitive_data(saida)["personal_data"]["birth_date"].startswith("1992-02-02")

    def test_e_idempotente(self):
        uma = encrypt_sensitive_data(copy.deepcopy(_processo(birth_date="1995-03-15")))
        duas = encrypt_sensitive_data(copy.deepcopy(uma))
        assert duas["personal_data"]["birth_date"] == uma["personal_data"]["birth_date"]
        assert duas["personal_data"]["birth_year"] == 1995

    def test_uma_data_apagada_apaga_o_ano(self):
        saida = encrypt_sensitive_data({"personal_data": {"birth_date": "", "data_nascimento": "", "birth_year": 1995}})
        assert saida["personal_data"]["birth_year"] is None

    def test_uma_actualizacao_sem_data_nao_toca_no_ano(self):
        saida = encrypt_sensitive_data({"personal_data": {"nif": "501964842", "birth_year": 1995}})
        assert saida["personal_data"]["birth_year"] == 1995

    def test_um_texto_que_nao_e_data_cifra_se_e_nao_tem_ano(self):
        saida = encrypt_sensitive_data({"personal_data": {"data_nascimento": "15/03/1988"}})
        assert is_encrypted(saida["personal_data"]["data_nascimento"])
        assert saida["personal_data"]["birth_year"] is None

    def test_o_nif_continua_a_cifrar_se_ao_lado(self):
        # contraprova: a lista nova não substituiu a antiga
        saida = encrypt_sensitive_data(_processo(nif="501964842", birth_date="1995-03-15"))
        assert is_encrypted(saida["personal_data"]["nif"])


# ── A idade continua a poder calcular-se ───────────────────────────────────────

def _cifrado(**pessoa):
    return encrypt_sensitive_data({"personal_data": dict(pessoa)})


class TestAEtiquetaComADataCifrada:
    @pytest.mark.parametrize("data,esperado", [
        ("1995-03-15", True),      # 31
        ("1991-01-01", True),      # 35
        ("1990-10-03", True),      # faz 36 amanhã: ainda 35
        ("1990-10-02", False),     # faz 36 hoje
        ("1980-01-01", False),
        ("2030-01-01", False),     # futuro
    ])
    def test_a_mesma_resposta_cifrada_e_em_claro(self, data, esperado):
        em_claro = {"personal_data": {"birth_date": data}}
        assert sub35.processo_e_sub35(em_claro, HOJE) is esperado
        assert sub35.processo_e_sub35(_cifrado(birth_date=data), HOJE) is esperado

    def test_uma_listagem_que_nao_decifra_nada_acerta_na_etiqueta(self):
        # `decrypt_processes_list(..., [])` serve o documento CRU: a etiqueta tem de abrir sozinha.
        cru = _cifrado(data_nascimento="1995-03-15")
        assert is_encrypted(cru["personal_data"]["data_nascimento"])
        sub35.aplicar_flag_a_processos([cru], HOJE)
        assert cru["is_sub35"] is True

    def test_o_segundo_titular_cifrado_bloqueia_como_em_claro(self):
        base = {"personal_data": {"birth_date": "1995-03-15"},
                "titular2_data": {"name": "Rui", "nif": "501964842", "birth_date": "1970-01-01"}}
        assert sub35.processo_e_sub35(base, HOJE) is False
        assert sub35.processo_e_sub35(encrypt_sensitive_data(copy.deepcopy(base)), HOJE) is False

    def test_um_comprador_adicional_cifrado_bloqueia_como_em_claro(self):
        base = {"personal_data": {"birth_date": "1995-03-15"},
                "co_buyers": [{"nome": "Ana", "birth_date": "1970-01-01"}]}
        assert sub35.processo_e_sub35(base, HOJE) is False
        assert sub35.processo_e_sub35(encrypt_sensitive_data(copy.deepcopy(base)), HOJE) is False

    def test_uma_cifra_que_nao_abre_e_data_desconhecida_e_falha_fechada(self):
        assert sub35.processo_e_sub35({"personal_data": {"birth_date": "ENC:isto-nao-abre"}}, HOJE) is False

    def test_o_cliente_da_pool(self):
        cli = encrypt_client_data({"dados_pessoais": {"data_nascimento": "1999-12-31"}})
        assert sub35.cliente_e_sub35(cli, HOJE) is True


# ── O filtro do Mongo usa o ano e é estrito ────────────────────────────────────

class TestOFiltroPorAno:
    def test_o_intervalo_de_anos(self):
        assert sub35.intervalo_de_anos(HOJE) == (1991, 2025)

    def test_o_ano_da_margem_fica_de_fora(self):
        lo, hi = sub35.intervalo_de_anos(HOJE)
        assert lo == HOJE.year - 35 and 1990 < lo   # 1990 = hoje.year - 36
        assert hi < HOJE.year                        # o ano corrente também (futuro indistinguível)

    def _ramos(self, condicao):
        def andar(no):
            if isinstance(no, dict):
                for chave, valor in no.items():
                    if chave.endswith("birth_year") and isinstance(valor, dict):
                        yield chave, valor
                    else:
                        yield from andar(valor)
            elif isinstance(no, list):
                for item in no:
                    yield from andar(item)
        return list(andar(condicao))

    def test_o_filtro_olha_para_o_ano_de_todas_as_pessoas(self):
        caminhos = {c for c, _ in self._ramos(sub35.condicao_sub35(HOJE))}
        assert {"personal_data.birth_year", "titular2_data.birth_year", "birth_year"} <= caminhos

    def test_todos_os_ramos_do_ano_usam_o_mesmo_intervalo(self):
        for _, intervalo in self._ramos(sub35.condicao_sub35(HOJE)):
            assert intervalo == {"$gte": 1991, "$lte": 2025}

    def test_a_condicao_do_cliente_usa_dados_pessoais(self):
        cond = sub35.condicao_sub35(HOJE, seccoes=sub35.SECCOES_DO_CLIENTE)
        assert "dados_pessoais.birth_year" in {c for c, _ in self._ramos(cond)}

    def test_os_ramos_de_data_em_claro_continuam_para_os_documentos_por_migrar(self):
        texto = repr(sub35.condicao_sub35(HOJE))
        assert "personal_data.birth_date" in texto and "personal_data.data_nascimento" in texto


# ── Escritores pontuados ───────────────────────────────────────────────────────

class TestProtegerCaminhos:
    def test_cifra_a_data_e_acrescenta_o_ano_no_mesmo_prefixo(self):
        saida = np_.proteger_caminhos({"personal_data.data_nascimento": "1995-03-15", "updated_at": "x"})
        assert is_encrypted(saida["personal_data.data_nascimento"])
        assert saida["personal_data.birth_year"] == 1995
        assert saida["updated_at"] == "x"

    def test_a_raiz_e_o_titular2(self):
        saida = np_.proteger_caminhos({"birth_date": "1980-05-05", "titular2_data.birth_date": "1990-01-02"})
        assert saida["birth_year"] == 1980 and saida["titular2_data.birth_year"] == 1990
        assert is_encrypted(saida["birth_date"]) and is_encrypted(saida["titular2_data.birth_date"])

    def test_devolve_uma_copia(self):
        original = {"personal_data.birth_date": "1995-03-15"}
        np_.proteger_caminhos(original)
        assert original == {"personal_data.birth_date": "1995-03-15"}

    def test_apagar_a_data_apaga_o_ano(self):
        saida = np_.proteger_caminhos({"personal_data.birth_date": ""})
        assert saida["personal_data.birth_year"] is None and saida["personal_data.birth_date"] == ""

    def test_e_idempotente(self):
        uma = np_.proteger_caminhos({"personal_data.birth_date": "1995-03-15"})
        duas = np_.proteger_caminhos(uma)
        assert duas == uma

    def test_nao_toca_noutros_campos(self):
        entrada = {"personal_data.nif": "501964842", "personal_data.nome": "Ana"}
        assert np_.proteger_caminhos(entrada) == entrada


class TestProtegerDocumento:
    def test_as_seccoes_inteiras_de_uma_actualizacao(self):
        # a forma que a análise de documentos da IA devolve
        update = {"personal_data": {"data_nascimento": "1995-03-15", "nif": "501964842"}, "updated_at": "x"}
        np_.proteger_documento(update)
        assert is_encrypted(update["personal_data"]["data_nascimento"])
        assert update["personal_data"]["birth_year"] == 1995
        assert update["personal_data"]["nif"] == "501964842"     # o NIF não é deste módulo

    def test_listas_e_idempotencia(self):
        update = {"co_applicants": [{"nome": "x", "data_nascimento": "1990-01-02"}]}
        np_.proteger_documento(update)
        primeira = update["co_applicants"][0]["data_nascimento"]
        np_.proteger_documento(update)
        assert update["co_applicants"][0]["data_nascimento"] == primeira
        assert update["co_applicants"][0]["birth_year"] == 1990


class TestOsEscritoresPontuadosReais:
    def test_aceitar_uma_sugestao_da_ia_grava_cifrado(self):
        suggestions = [{"field": "birth_date", "field_path": "personal_data.data_nascimento",
                        "suggested": "1995-03-15", "id": "s1", "current": ""}]
        update, _, valor = process_ai_conflict.apply_ai_conflict_choice(
            ai_suggestions=suggestions, field="birth_date", choice="ai",
            suggestion_id="s1", now="2026-10-23T00:00:00+00:00",
        )
        assert valor == "1995-03-15"
        assert is_encrypted(update["personal_data.data_nascimento"])
        assert update["personal_data.birth_year"] == 1995
        assert "1995-03-15" not in repr(update)

    def test_manter_o_valor_actual_nao_escreve_data(self):
        suggestions = [{"field": "birth_date", "suggested": "1995-03-15", "id": "s1"}]
        update, _, _ = process_ai_conflict.apply_ai_conflict_choice(
            ai_suggestions=suggestions, field="birth_date", choice="current",
            suggestion_id="s1", now="x",
        )
        assert not any("birth" in k or "nascimento" in k for k in update)

    @pytest.mark.asyncio
    async def test_o_espelho_do_segundo_titular_no_processo_vai_cifrado(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "p1", "titular2_data": {"nif": "x"}})
        await portal_profile_sections.espelhar_nos_processos(
            fake_async_db, ["p1"], {"titular2_data": {"birth_date": "1990-01-02"}},
        )
        gravado = await fake_async_db.processes.find_one({"id": "p1"})
        assert is_encrypted(gravado["titular2_data"]["birth_date"])
        assert gravado["titular2_data"]["birth_year"] == 1990

    @pytest.mark.asyncio
    async def test_o_espelho_cria_o_grupo_inteiro_cifrado(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "p1", "titular2_data": None})
        await portal_profile_sections.espelhar_nos_processos(
            fake_async_db, ["p1"], {"titular2_data": {"birth_date": "1990-01-02"}},
        )
        gravado = await fake_async_db.processes.find_one({"id": "p1"})
        assert is_encrypted(gravado["titular2_data"]["birth_date"])
        assert gravado["titular2_data"]["birth_year"] == 1990

    def test_apagar_a_data_nos_processos_apaga_o_ano(self):
        processo = {"personal_data": {"data_nascimento": "ENC:x", "birth_year": 1995}}
        sets = campos_limpaveis.espelhos_no_processo(processo, ["data_nascimento"])
        assert sets["personal_data.data_nascimento"] == ""
        assert sets["personal_data.birth_year"] is None

    def test_apagar_outro_campo_nao_toca_no_ano(self):
        processo = {"personal_data": {"morada_fiscal": "x", "birth_year": 1995}}
        assert "personal_data.birth_year" not in campos_limpaveis.espelhos_no_processo(processo, ["morada_fiscal"])


class TestALigacaoDosEscritores:
    """Apagar a chamada não parte nenhum teste de comportamento — parte estes."""

    @pytest.mark.parametrize("modulo,funcao,chamada", [
        ("services.client_crud", "run_update_client", "proteger_caminhos(process_sync)"),
        ("services.portal_profile", "run_update_client_profile", "proteger_caminhos(mongo_update)"),
        ("services.ai_bulk_helpers", "update_client_data", "proteger_documento(update_data)"),
        ("services.admin_proc_migration_helpers", "run_migration_task", "proteger_documento(new_client)"),
        ("services.process_ai_conflict", "apply_ai_conflict_choice", "proteger_caminhos("),
        ("services.portal_profile_sections", "espelhar_nos_processos", "proteger_caminhos("),
    ])
    def test_o_escritor_protege_a_data(self, modulo, funcao, chamada):
        import importlib
        alvo = getattr(importlib.import_module(modulo), funcao)
        assert chamada in codigo_da_funcao_sem_comentarios(alvo).replace("\n", "").replace("  ", "")


# ── O plano da migração ────────────────────────────────────────────────────────

class TestOPlanoDaMigracao:
    def test_em_claro_cifra_e_carimba(self):
        plano = planear({"personal_data": {"data_nascimento": "1995-03-15"}})
        assert is_encrypted(plano.definir["personal_data.data_nascimento"])
        assert plano.definir["personal_data.birth_year"] == 1995

    def test_ja_migrado_nao_tem_nada_a_fazer(self):
        migrado = encrypt_sensitive_data({"personal_data": {"data_nascimento": "1995-03-15"}})
        assert planear(migrado).vazio

    def test_cifrado_sem_ano_so_acrescenta_o_ano(self):
        doc = {"personal_data": {"data_nascimento": encryption_service.encrypt("1990-01-02")}}
        plano = planear(doc)
        assert list(plano.definir) == ["personal_data.birth_year"]
        assert plano.definir["personal_data.birth_year"] == 1990

    def test_data_vazia_com_ano_orfao_limpa_o_ano(self):
        plano = planear({"personal_data": {"data_nascimento": "", "birth_year": 1999}})
        assert plano.definir == {"personal_data.birth_year": None}

    def test_uma_cifra_ilegivel_nao_se_toca(self):
        doc = {"personal_data": {"data_nascimento": "ENC:nao-abre", "birth_year": 1990}}
        plano = planear(doc)
        assert plano.vazio and plano.contagem["ilegiveis"] == 1

    def test_os_elementos_das_listas_levam_o_indice(self):
        plano = planear({"co_buyers": [{"nome": "a"}, {"data_nascimento": "2001-07-01"}]})
        assert "co_buyers.1.data_nascimento" in plano.definir
        assert plano.definir["co_buyers.1.birth_year"] == 2001

    def test_os_dois_nomes_da_mesma_pessoa_partilham_o_ano(self):
        plano = planear({"personal_data": {"birth_date": "1995-03-15", "data_nascimento": "1995-03-15"}})
        assert plano.definir["personal_data.birth_year"] == 1995
        assert is_encrypted(plano.definir["personal_data.birth_date"])
        assert is_encrypted(plano.definir["personal_data.data_nascimento"])

    def test_o_filtro_de_escrita_leva_o_valor_lido(self):
        doc = {"_id": 1, "personal_data": {"data_nascimento": "1995-03-15"}}
        plano = planear(doc)
        from services.birthdate_migration import filtro_de_escrita
        filtro = filtro_de_escrita(1, plano)
        assert filtro["personal_data.data_nascimento"] == "1995-03-15"
        assert filtro["personal_data.birth_year"] is None
