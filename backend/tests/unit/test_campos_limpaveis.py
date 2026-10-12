"""Apagar um campo opcional persiste: o módulo `campos_limpaveis` e as suas ligações (QA, Out 2026).

O fluxo completo contra um MongoDB real está em
`tests/integration/test_apagar_campos_mongo.py`. Aqui ficam as regras puras e as
ligações que não precisam de Mongo (corre no job `backend-fast`).

REGRA DE FUNDO: chave presente e vazia (`""`, `null`, espaços) = «apaga»; chave
ausente = «não alterei».
"""
from __future__ import annotations

import ast
import inspect

import pytest
from fastapi import HTTPException

import services.campos_limpaveis as cl
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios


# ═════════════════════════════════════════════════════════════════════
# Campos pessoais limpos
# ═════════════════════════════════════════════════════════════════════


class TestCamposPessoaisLimpos:
    def test_vazio_none_e_espacos_sao_limpezas_e_normalizam_para_vazio(self):
        dados = {"nif": "", "morada_fiscal": None, "naturalidade": "   "}
        assert cl.campos_pessoais_limpos(dados) == ["nif", "morada_fiscal", "naturalidade"]
        assert dados == {"nif": "", "morada_fiscal": "", "naturalidade": ""}

    def test_um_valor_nao_e_tocado(self):
        dados = {"nif": "123456789", "morada_fiscal": "Rua A"}
        assert cl.campos_pessoais_limpos(dados) == []
        assert dados == {"nif": "123456789", "morada_fiscal": "Rua A"}

    def test_a_chave_ausente_nao_conta(self):
        assert cl.campos_pessoais_limpos({"naturalidade": "Porto"}) == []

    def test_zero_e_false_sao_valores(self):
        dados = {"altura": 0, "menor_35_anos": False}
        assert cl.campos_pessoais_limpos(dados) == []

    @pytest.mark.parametrize("campo", ["nome", "name", "nome_completo", "email", "telefone", "phone"])
    def test_nome_e_contactos_ficam_de_fora(self, campo):
        """O nome é obrigatório; os contactos têm o seu próprio caminho."""
        dados = {campo: ""}
        assert cl.campos_pessoais_limpos(dados) == []

    def test_indices_cegos_ficam_de_fora(self):
        dados = {"nif_hash": "", "email_hash": None}
        assert cl.campos_pessoais_limpos(dados) == []

    def test_campos_que_nao_sao_texto_ficam_como_estao(self):
        """`menor_35_anos` é booleano: `None` é o seu «sem valor», `""` seria um tipo errado."""
        dados = {"menor_35_anos": None}
        assert cl.campos_pessoais_limpos(dados) == []
        assert dados == {"menor_35_anos": None}

    def test_tipos_estranhos_nao_rebentam(self):
        assert cl.campos_pessoais_limpos(None) == []
        assert cl.campos_pessoais_limpos("x") == []

    def test_na_forma_de_chaves_pontuadas_do_put_do_processo(self):
        updates = {
            "dados_pessoais.nif": "", "dados_pessoais.nif_hash": "",
            "dados_pessoais.morada_fiscal": "Rua A", "dados_pessoais.naturalidade": None,
            "contacto.email": "", "nome": "", "titular2_data": {},
        }
        assert cl.campos_pessoais_limpos_em_updates(updates) == ["nif", "naturalidade"]
        # Não altera o que recebe.
        assert updates["dados_pessoais.naturalidade"] is None

    def test_pontuadas_ignora_sub_chaves_mais_fundas(self):
        assert cl.campos_pessoais_limpos_em_updates({"dados_pessoais.a.b": ""}) == []


# ═════════════════════════════════════════════════════════════════════
# Espelhos no processo
# ═════════════════════════════════════════════════════════════════════


PROCESSO = {
    "id": "p1", "client_nif": "ENC:x",
    "personal_data": {
        "nif": "ENC:x", "nif_hash": "h", "morada_fiscal": "Rua A", "morada": "Rua A",
        "address": "Rua A", "naturalidade": "Porto", "data_nascimento": "1990-01-01",
        "birth_date": "1990-01-01",
    },
}


class TestEspelhosNoProcesso:
    def test_o_nif_leva_o_indice_cego_e_a_copia_da_raiz(self):
        assert cl.espelhos_no_processo(PROCESSO, ["nif"]) == {
            "personal_data.nif": "", "personal_data.nif_hash": "", "client_nif": "",
        }

    def test_a_morada_leva_os_nomes_alternativos(self):
        assert cl.espelhos_no_processo(PROCESSO, ["morada_fiscal"]) == {
            "personal_data.morada_fiscal": "", "personal_data.morada": "",
            "personal_data.address": "",
        }

    def test_a_data_de_nascimento_e_simetrica(self):
        esperado = {"personal_data.data_nascimento": "", "personal_data.birth_date": ""}
        assert cl.espelhos_no_processo(PROCESSO, ["data_nascimento"]) == esperado
        assert cl.espelhos_no_processo(PROCESSO, ["birth_date"]) == esperado

    def test_so_o_que_o_processo_tem(self):
        """Nunca cria chaves que o processo não tinha."""
        assert cl.espelhos_no_processo({"id": "p"}, ["nif", "morada_fiscal"]) == {}
        assert cl.espelhos_no_processo({"personal_data": {"nif": "x"}}, ["nif"]) == {
            "personal_data.nif": "",
        }

    def test_um_espelho_ja_vazio_nao_gera_escrita(self):
        assert cl.espelhos_no_processo({"client_nif": "", "personal_data": {"nif": None}}, ["nif"]) == {}

    def test_campos_sem_espelho_conhecido_so_limpam_o_proprio_nome(self):
        assert cl.espelhos_no_processo(PROCESSO, ["naturalidade"]) == {"personal_data.naturalidade": ""}

    def test_sem_campos_nao_faz_nada(self):
        assert cl.espelhos_no_processo(PROCESSO, []) == {}

    def test_personal_data_que_nao_e_dict_nao_rebenta(self):
        assert cl.espelhos_no_processo({"personal_data": "x", "client_nif": "9"}, ["nif"]) == {
            "client_nif": "",
        }

    def test_aliases_no_cliente_so_os_que_existem(self):
        existentes = {"morada_fiscal": "x", "address": "Rua A", "morada": ""}
        assert cl.aliases_a_limpar_no_cliente(existentes, ["morada_fiscal"]) == {"address": ""}
        assert cl.aliases_a_limpar_no_cliente(None, ["morada_fiscal"]) == {}


# ═════════════════════════════════════════════════════════════════════
# Financeiro: o canónico vai com os alternativos
# ═════════════════════════════════════════════════════════════════════


class TestAliasesFinanceiros:
    def test_canonico_limpo_leva_os_alternativos(self):
        assert cl.aliases_financeiros_a_remover({"monthly_income": None}) == {
            "rendimento_mensal", "salario_liquido",
        }
        assert cl.aliases_financeiros_a_remover({"employer_name": ""}) == {"empresa", "entidade_patronal"}

    def test_canonico_com_valor_nao_retira_nada(self):
        assert cl.aliases_financeiros_a_remover({"monthly_income": 2000}) == set()

    def test_zero_nao_e_vazio(self):
        assert cl.aliases_financeiros_a_remover({"nr_dependentes": 0}) == set()

    def test_alternativo_escrito_no_mesmo_pedido_nao_se_retira(self):
        out = cl.aliases_financeiros_a_remover({"monthly_income": None, "salario_liquido": 1500})
        assert out == {"rendimento_mensal"}

    def test_chave_ausente_nao_retira_nada(self):
        assert cl.aliases_financeiros_a_remover({"capital_proprio": 1}) == set()
        assert cl.aliases_financeiros_a_remover(None) == set()

    def test_as_tabelas_sao_as_mesmas_do_frontend(self):
        """A tabela vive nos dois lados (o ecrã promove, o servidor apaga): se divergirem,
        o valor «volta» — que é exactamente o defeito que isto corrige."""
        import re
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[3] / "frontend/src/utils/camposLimpos.js").read_text()

        def tabela(nome):
            bloco = re.search(rf"export const {nome} = Object\.freeze\(\{{(.*?)\}}\);", fonte, re.S).group(1)
            return {
                chave: tuple(re.findall(r'"([^"]+)"', valores))
                for chave, valores in re.findall(r"(\w+):\s*\[(.*?)\]", bloco)
            }

        assert tabela("ALIASES_FINANCEIROS") == cl.ALIASES_FINANCEIROS
        assert tabela("ALIASES_PESSOAIS") == cl.ALIASES_PESSOAIS

    def test_o_leitor_das_tabelas_le_mesmo_o_ficheiro(self):
        """Contraprova do teste acima: um leitor que devolvesse pouco passava sempre."""
        import re
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[3] / "frontend/src/utils/camposLimpos.js").read_text()
        assert len(re.findall(r"(\w+):\s*\[", fonte)) >= len(cl.ALIASES_FINANCEIROS) + len(cl.ALIASES_PESSOAIS)

    def test_a_hidratacao_do_ecra_usa_as_tabelas(self):
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[3] / "frontend/src/pages/processDetails/processDetailsHydration.js").read_text()
        assert "preencherCanonicosComAliases(personal, ALIASES_PESSOAIS)" in fonte
        assert "preencherCanonicosComAliases(financial, ALIASES_FINANCEIROS)" in fonte


# ═════════════════════════════════════════════════════════════════════
# O nome não se apaga
# ═════════════════════════════════════════════════════════════════════


class TestNomeObrigatorio:
    @pytest.mark.parametrize("vazio", ["", "   ", None])
    def test_nome_enviado_vazio_e_400(self, vazio):
        with pytest.raises(HTTPException) as exc:
            cl.exigir_nome({"nome"}, vazio)
        assert exc.value.status_code == 400
        assert "nome" in exc.value.detail.lower()

    def test_nome_nao_enviado_passa(self):
        cl.exigir_nome({"contacto"}, None)

    def test_nome_com_valor_passa(self):
        cl.exigir_nome({"nome"}, "Ana")


# ═════════════════════════════════════════════════════════════════════
# O PUT do processo: o corpo → pedido de limpeza
# ═════════════════════════════════════════════════════════════════════


class TestExtrairDoCorpoDoPutDoProcesso:
    @staticmethod
    def _extrair(corpo):
        from services.process_service import extract_client_updates_from_body

        return extract_client_updates_from_body(corpo)

    @pytest.mark.parametrize("vazio", ["", None, "   "])
    def test_campo_vazio_ou_null_pede_para_apagar(self, vazio):
        out = self._extrair({"personal_data": {"nif": vazio, "morada_fiscal": vazio}})
        assert out["dados_pessoais.nif"] == ""
        assert out["dados_pessoais.morada_fiscal"] == ""

    def test_chave_ausente_nao_pede_nada(self):
        out = self._extrair({"personal_data": {"naturalidade": "Porto"}})
        assert out == {"dados_pessoais.naturalidade": "Porto"}

    def test_um_valor_passa_tal_e_qual(self):
        assert self._extrair({"personal_data": {"nif": "123456789"}}) == {
            "dados_pessoais.nif": "123456789",
        }

    def test_o_espelho_do_telefone_vazio_nao_e_um_pedido(self):
        """`personal_data.telefone` é um espelho do contacto: o pedido explícito é `client_phone`."""
        out = self._extrair({"personal_data": {"telefone": None, "phone": None}})
        assert "dados_pessoais.telefone" not in out

    def test_o_nome_vazio_no_corpo_nao_vira_pedido(self):
        out = self._extrair({"personal_data": {"nome": "", "name": None}})
        assert "nome" not in out and "dados_pessoais.nome_completo" not in out


class TestSeedDoProcessoLimpaAsCopias:
    def test_o_seed_leva_as_copias_do_nif(self):
        from services.process_update import seed_update_data

        seed = seed_update_data(
            process=PROCESSO, client_id_before="c", new_client_id=None,
            raw_client_email=None, raw_client_phone=None, campos_pessoais_limpos=["nif"],
        )
        assert seed["client_nif"] == "" and seed["personal_data.nif"] == ""
        assert seed["personal_data.nif_hash"] == ""
        assert "personal_data.morada_fiscal" not in seed

    def test_sem_campos_limpos_o_seed_nao_toca_nas_copias(self):
        from services.process_update import seed_update_data

        seed = seed_update_data(
            process=PROCESSO, client_id_before="c", new_client_id=None,
            raw_client_email=None, raw_client_phone=None,
        )
        assert not any(k.startswith("personal_data") or k == "client_nif" for k in seed)


class TestEspelhoDoSegundoTitular:
    BODY = {"titular2_data": {"name": "Rui", "nif": "987654321", "nif_hash": "h"}}

    def test_o_pedido_que_edita_o_titular2_escreve_a_copia_do_processo(self):
        from services.process_update import espelho_do_titular2

        out = espelho_do_titular2({"id": "p"}, "cli-1", self.BODY)
        assert out == {"name": "Rui", "nif": "987654321"}, "sem o índice cego do cliente"

    def test_substitui_em_vez_de_fundir(self):
        """O que o formulário não envia deixa de existir — é assim que um campo apagado desaparece."""
        from services.process_update import espelho_do_titular2

        assert espelho_do_titular2({}, "c", {"titular2_data": {"name": "Rui"}}) == {"name": "Rui"}

    def test_um_titular2_vazio_limpa_a_copia(self):
        from services.process_update import espelho_do_titular2

        assert espelho_do_titular2({}, "c", {"titular2_data": {}}) == {}

    @pytest.mark.parametrize("processo,cliente,corpo", [
        ({"second_client_id": "cli-2"}, "cli-1", BODY),   # recomposto a partir do outro cliente
        ({}, None, BODY),                                  # sem ficha onde escrever
        ({}, "cli-1", {}),                                 # o pedido não fala do 2.º titular
        ({}, "cli-1", {"titular2_data": "x"}),             # tipo errado
    ])
    def test_nos_restantes_casos_nao_escreve(self, processo, cliente, corpo):
        from services.process_update import espelho_do_titular2

        assert espelho_do_titular2(processo, cliente, corpo) is None


# ═════════════════════════════════════════════════════════════════════
# Limpar nos outros processos (duplo de Mongo)
# ═════════════════════════════════════════════════════════════════════


class TestLimparEspelhosNosProcessos:
    @pytest.mark.asyncio
    async def test_encontra_por_process_ids_e_por_client_id(self, fake_async_db):
        fake_async_db.processes.docs.extend([
            {"id": "p1", "client_id": "c1", "client_nif": "9", "personal_data": {"nif": "9", "nif_hash": "h"}},
            {"id": "p2", "client_id": "outro", "client_nif": "9", "personal_data": {"nif": "9"}},
            {"id": "p3", "client_id": "c1", "client_nif": "9", "personal_data": {"nif": "9"}},
            {"id": "p4", "client_id": "x", "client_nif": "7", "personal_data": {"nif": "7"}},
        ])
        # p2 só está na lista da ficha; p3 só pelo client_id; p4 não é deste cliente.
        n = await cl.limpar_espelhos_nos_processos(fake_async_db, "c1", ["p1", "p2"], ["nif"])
        assert n == 3
        por_id = {d["id"]: d for d in fake_async_db.processes.docs}
        for pid in ("p1", "p2", "p3"):
            assert por_id[pid]["client_nif"] == "" and por_id[pid]["personal_data"]["nif"] == ""
        assert por_id["p1"]["personal_data"]["nif_hash"] == ""
        assert por_id["p4"]["client_nif"] == "7"

    @pytest.mark.asyncio
    async def test_exclui_o_processo_ja_tratado(self, fake_async_db):
        fake_async_db.processes.docs.append({"id": "p1", "client_id": "c1", "client_nif": "9"})
        assert await cl.limpar_espelhos_nos_processos(fake_async_db, "c1", ["p1"], ["nif"], excluir=["p1"]) == 0
        assert fake_async_db.processes.docs[0]["client_nif"] == "9"

    @pytest.mark.asyncio
    async def test_sem_campos_ou_sem_alvo_nao_consulta_nada(self, fake_async_db):
        fake_async_db.processes.docs.append({"id": "p1", "client_id": "c1", "client_nif": "9"})
        assert await cl.limpar_espelhos_nos_processos(fake_async_db, "c1", ["p1"], []) == 0
        assert await cl.limpar_espelhos_nos_processos(fake_async_db, None, None, ["nif"]) == 0
        assert fake_async_db.processes.docs[0]["client_nif"] == "9"


# ═════════════════════════════════════════════════════════════════════
# Guardas de LIGAÇÃO (apagar a chamada não parte nenhum outro teste)
# ═════════════════════════════════════════════════════════════════════


def _codigo(modulo, funcao: str) -> str:
    return codigo_da_funcao_sem_comentarios(getattr(modulo, funcao))


def _chama(modulo, funcao: str, nome: str) -> bool:
    codigo = _codigo(modulo, funcao)
    return any(
        isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) == nome or getattr(n.func, "attr", None) == nome)
        for n in ast.walk(ast.parse(codigo))
    )


class TestLigacoes:
    def test_run_update_client_exige_o_nome_antes_de_gravar(self):
        import services.client_crud as cc

        assert _chama(cc, "run_update_client", "exigir_nome")
        fonte = _codigo(cc, "run_update_client")
        assert fonte.index("exigir_nome") < fonte.index("update_one"), (
            "a recusa do nome tem de vir ANTES de qualquer escrita"
        )

    def test_run_update_client_limpa_os_espelhos_nos_processos(self):
        import services.client_crud as cc

        for nome in ("campos_pessoais_limpos", "aliases_a_limpar_no_cliente", "limpar_espelhos_nos_processos"):
            assert _chama(cc, "run_update_client", nome), nome

    def test_o_put_do_processo_passa_os_campos_limpos_ao_seed_e_ao_cascade(self):
        import services.process_update as pu

        assert _chama(pu, "run_update_process", "campos_pessoais_limpos_em_updates")
        fonte = _codigo(pu, "run_update_process")
        assert "campos_pessoais_limpos=pessoais_limpos" in fonte.replace(" ", "")
        assert _chama(pu, "apply_client_personal_updates_from_process_put", "limpar_espelhos_nos_processos")

    def test_o_financeiro_retira_os_alternativos(self):
        import services.process_update as pu

        assert _chama(pu, "apply_staff_business_updates", "aliases_financeiros_a_remover")

    def test_o_put_do_processo_escreve_a_copia_do_segundo_titular(self):
        import services.process_update as pu

        assert _chama(pu, "run_update_process", "espelho_do_titular2")

    def test_o_modulo_e_puro(self):
        """Sem I/O: quem escreve na base é o chamador (o `db` entra por argumento)."""
        importados = set()
        for no in ast.walk(ast.parse(inspect.getsource(cl))):
            if isinstance(no, ast.ImportFrom):
                importados.add(no.module)
            elif isinstance(no, ast.Import):
                importados.update(a.name for a in no.names)
        assert "database" not in importados
