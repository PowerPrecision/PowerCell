"""A medição do custo de cortar o recurso por nome (D-19).

O que estes testes protegem é a ARITMÉTICA do relatório. Um relatório que
anuncia um custo errado é pior do que não medir: se inflaciona, o corte
nunca se faz; se subestima, o corte apaga documentos de clientes reais.

Dois testes valem mais do que os outros:
  * `test_a_regra_de_medicao_e_a_MESMA_do_codigo_de_producao` — medir com
    uma regra diferente da que o `list_files` usa é medir outra coisa;
  * `test_a_colisao_so_se_ve_no_CONJUNTO` — classificar ficha a ficha dá
    `depende_do_nome` às duas e o pior caso fica invisível.
"""
from __future__ import annotations

import pytest

from services.s3_document_root import RAIZ
from services.s3_name_fallback_audit import (
    InventarioIndisponivel,
    VEREDICTO_COLISAO,
    VEREDICTO_DEPENDE_DO_NOME,
    VEREDICTO_MAPEADO,
    VEREDICTO_MAPEADO_QUEBRADO,
    VEREDICTO_SEM_PASTA,
    Ficha,
    Pasta,
    auditar,
    conta_ficheiros_uteis,
    nomes_de_pasta_candidatos,
    para_religar,
    resumir,
)


def _processo(id_, nome, **kw):
    return Ficha(tipo="processo", id=id_, nome=nome, **kw)


class TestOVeredicto:
    def test_com_s3_folder_que_existe_o_corte_nao_lhe_toca(self):
        fichas = [_processo("p1", "Ana Costa", s3_folder=f"{RAIZ}cliente-uuid")]
        pastas = [Pasta(nome="cliente-uuid", ficheiros=4)]
        [resultado] = auditar(fichas, pastas)
        assert resultado.veredicto == VEREDICTO_MAPEADO
        assert resultado.ficheiros == 0, (
            "um mapeado não entra na conta de ficheiros em risco"
        )

    def test_com_s3_folder_que_NAO_existe_e_mapeado_quebrado(self):
        fichas = [_processo("p1", "Ana Costa", s3_folder=f"{RAIZ}pasta que foi apagada")]
        [resultado] = auditar(fichas, [Pasta(nome="outra", ficheiros=2)])
        assert resultado.veredicto == VEREDICTO_MAPEADO_QUEBRADO

    def test_um_s3_folder_de_PROCESSO_valida_a_pasta_do_CLIENTE(self):
        """`{cid}/processos/{pid}` existe se a pasta de topo `{cid}` existir.

        O bucket é listado com `Delimiter="/"`, logo o inventário só tem
        pastas de TOPO. Comparar o caminho inteiro faria todo o mapeamento
        aninhado do Lote 6 aparecer como quebrado — centenas de falsos
        positivos a tapar os casos verdadeiros.
        """
        fichas = [_processo(
            "p1", "Ana Costa",
            s3_folder=f"{RAIZ}cliente-uuid/processos/processo-uuid",
        )]
        [resultado] = auditar(fichas, [Pasta(nome="cliente-uuid", ficheiros=3)])
        assert resultado.veredicto == VEREDICTO_MAPEADO

    @pytest.mark.parametrize("gravado", ["", None, "   ", "undefined", "null", "none"])
    def test_os_valores_de_lixo_contam_como_SEM_mapeamento(self, gravado):
        """O `ensure_client_folder_mapping` descarta exactamente estes.

        Tratá-los como mapeamento faria o relatório dizer que a ficha está
        segura quando na verdade ela depende do nome — subestimar o custo
        é o erro que apaga documentos.
        """
        fichas = [_processo("p1", "Ana Costa", s3_folder=gravado)]
        [resultado] = auditar(fichas, [Pasta(nome="Ana Costa", ficheiros=5)])
        assert resultado.veredicto == VEREDICTO_DEPENDE_DO_NOME

    def test_sem_mapeamento_e_sem_pasta_o_corte_nao_tira_nada(self):
        fichas = [_processo("p1", "Ana Costa")]
        [resultado] = auditar(fichas, [Pasta(nome="Rui Pereira", ficheiros=9)])
        assert resultado.veredicto == VEREDICTO_SEM_PASTA
        assert resultado.ficheiros == 0

    def test_uma_pasta_VAZIA_resolvida_pelo_nome_nao_e_um_custo(self):
        """Resolver não é perder: sem ficheiros não há documento a esconder."""
        fichas = [_processo("p1", "Ana Costa")]
        [resultado] = auditar(fichas, [Pasta(nome="Ana Costa", ficheiros=0)])
        assert resultado.veredicto == VEREDICTO_SEM_PASTA

    def test_sem_mapeamento_com_pasta_do_nome_e_ficheiros_PERDE_documentos(self):
        fichas = [_processo("p1", "Ana Costa")]
        [resultado] = auditar(fichas, [Pasta(nome="Ana Costa", ficheiros=7)])
        assert resultado.veredicto == VEREDICTO_DEPENDE_DO_NOME
        assert resultado.pasta == f"{RAIZ}Ana Costa"
        assert resultado.ficheiros == 7

    def test_a_grafia_sanitizada_tambem_resolve(self):
        """Houve dois escritores: com espaços e com underscores."""
        fichas = [_processo("p1", "Ana Costa")]
        [resultado] = auditar(fichas, [Pasta(nome="Ana_Costa", ficheiros=2)])
        assert resultado.veredicto == VEREDICTO_DEPENDE_DO_NOME

    def test_o_segundo_titular_entra_no_nome_da_pasta(self):
        fichas = [_processo("p1", "Ana Costa", segundo_nome="Rui Pereira")]
        [resultado] = auditar(fichas, [Pasta(nome="Ana Costa e Rui Pereira", ficheiros=3)])
        assert resultado.veredicto == VEREDICTO_DEPENDE_DO_NOME

    def test_o_match_e_EXACTO_e_nao_por_semelhanca(self):
        """A aritmética do 0.867 não volta a entrar — nem na medição.

        "Carolina Agostinho da Silva" contra a pasta "Carolina Silva" dava
        0.867 no código antigo. Se a medição usasse o score, o relatório
        prometia religar uma ficha para uma pasta que não é dela.
        """
        fichas = [_processo("p1", "Carolina Agostinho da Silva")]
        [resultado] = auditar(fichas, [Pasta(nome="Carolina Silva", ficheiros=12)])
        assert resultado.veredicto == VEREDICTO_SEM_PASTA


class TestAColisao:
    def test_a_colisao_so_se_ve_no_CONJUNTO(self):
        """Duas fichas, um nome, uma pasta — é a D-19 em estado puro."""
        fichas = [
            _processo("p1", "Ana Costa"),
            _processo("p2", "Ana Costa"),
        ]
        resultados = auditar(fichas, [Pasta(nome="Ana Costa", ficheiros=6)])
        assert {r.veredicto for r in resultados} == {VEREDICTO_COLISAO}
        assert resultados[0].partilhada_com == ["processo:p2"]
        assert resultados[1].partilhada_com == ["processo:p1"]

    def test_uma_ficha_sozinha_NUNCA_e_colisao(self):
        """Contraprova: sem ela, marcar tudo como colisão passava."""
        resultados = auditar(
            [_processo("p1", "Ana Costa")],
            [Pasta(nome="Ana Costa", ficheiros=6)],
        )
        assert resultados[0].veredicto == VEREDICTO_DEPENDE_DO_NOME
        assert resultados[0].partilhada_com == []

    def test_um_processo_e_um_cliente_na_mesma_pasta_colidem(self):
        """A colisão atravessa as colecções — é por isso que se audita as duas."""
        fichas = [
            _processo("p1", "Ana Costa"),
            Ficha(tipo="cliente", id="c1", nome="Ana Costa"),
        ]
        resultados = auditar(fichas, [Pasta(nome="Ana Costa", ficheiros=6)])
        assert {r.veredicto for r in resultados} == {VEREDICTO_COLISAO}
        assert resultados[0].partilhada_com == ["cliente:c1"]

    def test_duas_fichas_MAPEADAS_a_mesma_pasta_nao_sao_esta_colisao(self):
        """Essa é a colisão do Explorador, que já tem crachá próprio.

        Aqui mede-se só o custo de cortar o RECURSO POR NOME, e um
        mapeamento gravado não passa por ele. Misturar as duas inflacionava
        o custo do corte com casos que o corte não afecta.
        """
        fichas = [
            _processo("p1", "Ana Costa", s3_folder=f"{RAIZ}partilhada"),
            _processo("p2", "Rui Pereira", s3_folder=f"{RAIZ}partilhada"),
        ]
        resultados = auditar(fichas, [Pasta(nome="partilhada", ficheiros=6)])
        assert {r.veredicto for r in resultados} == {VEREDICTO_MAPEADO}


class TestAAritmeticaDoRelatorio:
    def test_a_colisao_conta_a_pasta_UMA_vez(self):
        """Duas fichas na mesma pasta não duplicam os ficheiros em risco."""
        fichas = [_processo("p1", "Ana Costa"), _processo("p2", "Ana Costa")]
        resumo = resumir(auditar(fichas, [Pasta(nome="Ana Costa", ficheiros=6)]))
        assert resumo["fichas_em_risco"] == 2
        assert resumo["pastas_em_risco"] == 1
        assert resumo["ficheiros_em_risco"] == 6, (
            "somar por ficha anunciaria 12 documentos onde existem 6"
        )

    def test_os_veredictos_que_nao_custam_ficam_fora_do_risco(self):
        fichas = [
            _processo("p1", "Ana Costa", s3_folder=f"{RAIZ}uuid-a"),
            _processo("p2", "Rui Pereira"),
            _processo("p3", "Maria Lopes"),
        ]
        pastas = [Pasta(nome="uuid-a", ficheiros=3), Pasta(nome="Maria Lopes", ficheiros=5)]
        resumo = resumir(auditar(fichas, pastas))
        assert resumo["total"] == 3
        assert resumo["por_veredicto"][VEREDICTO_MAPEADO] == 1
        assert resumo["por_veredicto"][VEREDICTO_SEM_PASTA] == 1
        assert resumo["fichas_em_risco"] == 1
        assert resumo["ficheiros_em_risco"] == 5

    def test_sem_fichas_o_resumo_e_zero_e_nao_rebenta(self):
        # Com bucket: zero fichas é um resultado. Sem bucket é uma falha de
        # leitura e `auditar` recusa-se (ver TestAMedicaoQueNaoAconteceu).
        assert resumir(auditar([], [Pasta(nome="x", ficheiros=1)])) == {
            "total": 0,
            "por_veredicto": {},
            "fichas_em_risco": 0,
            "pastas_em_risco": 0,
            "ficheiros_em_risco": 0,
        }


class TestAListaAccionavel:
    def test_a_colisao_vem_primeiro_mesmo_com_menos_ficheiros(self):
        """Partilhar documentação é um risco de RGPD; perder vista é um incómodo."""
        fichas = [
            _processo("p9", "Maria Lopes"),
            _processo("p1", "Ana Costa"),
            _processo("p2", "Ana Costa"),
        ]
        pastas = [Pasta(nome="Ana Costa", ficheiros=2), Pasta(nome="Maria Lopes", ficheiros=99)]
        linhas = para_religar(auditar(fichas, pastas))
        assert [linha["veredicto"] for linha in linhas] == [
            VEREDICTO_COLISAO, VEREDICTO_COLISAO, VEREDICTO_DEPENDE_DO_NOME,
        ]
        assert linhas[-1]["ficheiros"] == 99

    def test_cada_linha_leva_a_pasta_a_gravar_no_painel(self):
        linhas = para_religar(auditar(
            [_processo("p1", "Ana Costa", etiqueta="PROC-012")],
            [Pasta(nome="Ana Costa", ficheiros=4)],
        ))
        assert linhas == [{
            "tipo": "processo",
            "id": "p1",
            "nome": "Ana Costa",
            "etiqueta": "PROC-012",
            "veredicto": VEREDICTO_DEPENDE_DO_NOME,
            "s3_folder_sugerido": f"{RAIZ}Ana Costa",
            "ficheiros": 4,
            "partilhada_com": [],
        }]

    def test_quem_nao_custa_nao_entra_na_lista(self):
        linhas = para_religar(auditar(
            [_processo("p1", "Ana Costa", s3_folder=f"{RAIZ}uuid")],
            [Pasta(nome="uuid", ficheiros=4)],
        ))
        assert linhas == []


class TestOsFicheirosUteis:
    def test_os_marcadores_de_pasta_nao_sao_documentos(self):
        """Uma pasta recém-criada tem seis `.keep` e zero documentos."""
        chaves = [
            f"{RAIZ}x/Pessoais/.keep",
            f"{RAIZ}x/Financeiros/.keep",
            f"{RAIZ}x/Pessoais/cc.pdf",
        ]
        assert conta_ficheiros_uteis(chaves) == 1

    def test_uma_lista_vazia_conta_zero(self):
        assert conta_ficheiros_uteis([]) == 0


class TestAConcordanciaComProducao:
    def test_a_regra_de_medicao_e_a_MESMA_do_codigo_de_producao(self):
        """Medir com outra regra é medir outra coisa.

        O `_nomes_de_pasta_candidatos` do `s3_storage` é o que decide, em
        produção, se o recurso por nome encontra a pasta. Se a medição for
        mais LARGA, o relatório promete religamentos que o código nunca
        faria; se for mais ESTREITA, esconde custo. Por isso o oráculo é o
        método real, nunca uma terceira cópia da lista.
        """
        from services.s3_storage import S3Service

        servico = S3Service.__new__(S3Service)
        casos = [
            ("Ana Costa", None),
            ("Ana Costa", "Rui Pereira"),
            ("José Múrias da Silva", None),
            ("  Ana  Costa  ", None),
        ]
        for nome, segundo in casos:
            producao = servico._nomes_de_pasta_candidatos(nome, segundo)
            assert nomes_de_pasta_candidatos(nome, segundo) == producao, (
                f"divergência para {nome!r}/{segundo!r}"
            )

    def test_um_nome_vazio_nao_resolve_para_pasta_nenhuma(self):
        """Senão `""` casaria com a primeira pasta e o relatório inventava custo."""
        assert nomes_de_pasta_candidatos("") == []
        assert nomes_de_pasta_candidatos(None) == []
        resultados = auditar(
            [_processo("p1", "")], [Pasta(nome="Ana Costa", ficheiros=3)],
        )
        assert resultados[0].veredicto == VEREDICTO_SEM_PASTA


class TestOsLeitoresDoScript:
    """Contraprova de que o script LÊ mesmo o que diz ler.

    Sem isto, a aritmética ficava provada sobre fichas escritas à mão e o
    relatório podia correr contra produção a medir um conjunto vazio — que
    é a forma mais discreta de "podemos apagar, não custa nada".
    """

    @pytest.mark.asyncio
    async def test_le_processos_E_clientes_e_salta_os_eliminados(
        self, fake_async_db, monkeypatch,
    ):
        import importlib.util

        caminho = (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "scripts" / "diagnose_s3_name_fallback.py"
        )
        spec = importlib.util.spec_from_file_location("diag_d19", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        await fake_async_db.processes.insert_one({
            "id": "p1", "client_name": "Ana Costa", "process_number": "PROC-001",
            "titular2_data": {"nome": "Rui Pereira"},
        })
        await fake_async_db.processes.insert_one({
            "id": "p2", "client_name": "Eliminado", "is_deleted": True,
        })
        await fake_async_db.clients.insert_one({"id": "c1", "nome": "Maria Lopes"})

        import database
        monkeypatch.setattr(database, "db", fake_async_db)

        fichas = await modulo._carregar_fichas(incluir_eliminados=False)
        por_id = {f.id: f for f in fichas}

        assert set(por_id) == {"p1", "c1"}, (
            "o eliminado não tem separador de documentos para esvaziar"
        )
        assert por_id["p1"].tipo == "processo"
        assert por_id["p1"].segundo_nome == "Rui Pereira", (
            "sem o 2.º titular a pasta «A e B» nunca resolve"
        )
        assert por_id["p1"].etiqueta == "PROC-001"
        assert por_id["c1"].tipo == "cliente"
        assert por_id["c1"].nome == "Maria Lopes"

        todas = await modulo._carregar_fichas(incluir_eliminados=True)
        assert {f.id for f in todas} == {"p1", "p2", "c1"}

    def test_conta_os_ficheiros_por_pasta_de_TOPO_sem_os_marcadores(self, monkeypatch):
        """O inventário agrega pelo primeiro segmento, não pela chave inteira."""
        import importlib.util

        caminho = (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "scripts" / "diagnose_s3_name_fallback.py"
        )
        spec = importlib.util.spec_from_file_location("diag_d19b", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        chaves = [
            f"{RAIZ}Ana Costa/Pessoais/cc.pdf",
            f"{RAIZ}Ana Costa/Financeiros/irs.pdf",
            f"{RAIZ}Ana Costa/Pessoais/.keep",
            f"{RAIZ}uuid-b/processos/uuid-p/contrato.pdf",
            f"{RAIZ}",  # o próprio prefixo, sem pasta nenhuma
        ]

        class _Paginator:
            def paginate(self, **_kw):
                return [{"Contents": [{"Key": k} for k in chaves]}]

        class _Cliente:
            def get_paginator(self, _nome):
                return _Paginator()

        from services import s3_storage
        monkeypatch.setattr(s3_storage.s3_service, "is_configured", lambda: True)
        monkeypatch.setattr(s3_storage.s3_service, "s3_client", _Cliente())
        monkeypatch.setattr(s3_storage.s3_service, "bucket_name", "bucket-de-teste")

        pastas = {p.nome: p.ficheiros for p in modulo._carregar_pastas()}
        assert pastas == {"Ana Costa": 2, "uuid-b": 1}

    def test_o_script_NAO_tem_caminho_de_escrita(self):
        """A medição é só de leitura — e isso tem de se provar na fonte.

        O script corre contra produção de propósito; uma escrita acidental
        num `s3_folder` é permanente e move a fronteira de posse (é o que a
        guarda do `assert_s3_file_belongs_to_process` passa a autorizar).
        O religamento é uma decisão humana, no painel.
        """
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "scripts" / "diagnose_s3_name_fallback.py"
        )
        fonte = codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))
        for proibido in (
            "update_one", "update_many", "insert_one", "delete_one",
            "bulk_write", "replace_one", "$set",
        ):
            assert proibido not in fonte, (
                f"o diagnóstico da D-19 passou a escrever ({proibido})"
            )
        # Contraprova: a leitura das duas colecções continua lá — sem isto,
        # apagar o script satisfazia o guarda acima.
        assert "db.processes.find" in fonte
        assert "db.clients.find" in fonte


class TestAMedicaoQueNaoAconteceu:
    """Sem inventário não há conclusão — o defeito que a 1.ª execução revelou.

    Corri o script em dev, onde o S3 não está configurado. O inventário
    saiu vazio, todas as fichas caíram em `sem_pasta` e o relatório
    imprimiu «o recurso por nome pode ser apagado sem esconder documento
    nenhum». A medição não aconteceu e a conclusão era a mais perigosa de
    todas — exactamente a forma de defeito desta casa: o degradado que não
    dá erro e parece uma resposta.
    """

    @pytest.mark.parametrize("pastas", [None, []])
    def test_sem_inventario_RECUSA_em_vez_de_dizer_que_nao_custa(self, pastas):
        with pytest.raises(InventarioIndisponivel):
            auditar([_processo("p1", "Ana Costa")], pastas)

    def test_com_inventario_classifica_normalmente(self):
        """Contraprova: recusar sempre também passaria o teste acima."""
        resultados = auditar(
            [_processo("p1", "Ana Costa")], [Pasta(nome="Ana Costa", ficheiros=3)],
        )
        assert resultados[0].veredicto == VEREDICTO_DEPENDE_DO_NOME

    def test_sem_fichas_mas_COM_bucket_e_uma_medicao_valida(self):
        """Zero fichas é um resultado; zero pastas é uma falha de leitura."""
        assert resumir(auditar([], [Pasta(nome="x", ficheiros=1)]))["total"] == 0

    def test_o_script_sai_com_codigo_2_quando_nao_ha_bucket(self, monkeypatch):
        """Um 0 fazia um laço de CI tratar a não-medição como sucesso."""
        import asyncio
        import importlib.util

        caminho = (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "scripts" / "diagnose_s3_name_fallback.py"
        )
        spec = importlib.util.spec_from_file_location("diag_d19c", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        monkeypatch.setattr(modulo, "_carregar_pastas", lambda: None)

        async def _sem_fichas(incluir_eliminados):
            return []

        monkeypatch.setattr(modulo, "_carregar_fichas", _sem_fichas)
        monkeypatch.setattr(
            modulo, "_argumentos",
            lambda: __import__("argparse").Namespace(
                limite_exemplos=5, csv=None, incluir_eliminados=False,
            ),
        )
        assert asyncio.run(modulo.principal()) == 2
