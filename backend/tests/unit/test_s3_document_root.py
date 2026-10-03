"""A raiz documental por ID — e a colisão de identidade que ela fecha.

O BUG RELATADO (Lote 6, ponto 1)
================================
Os documentos de uma cliente nova ("Carolina Agostinho da Silva") foram
mapeados para a pasta de uma cliente existente ("Carolina Silva").

A aritmética do `_find_client_folder_combined` explica-o inteiramente:
dois terços das palavras em comum (`da` é descartada como palavra comum)
mais 0.2 de bónus por o primeiro nome aparecer na pasta dá **0.867**,
contra um limiar de 0.7. A assinatura da colisão é **mesmo primeiro nome
+ um conjunto de nomes contido no outro** — que é mãe e filha, dois
irmãos, e sobretudo a MESMA pessoa inserida com nome curto e com nome
completo.

Estes testes afirmam as duas metades da correcção:
  1. a identidade da pasta deixa de sair de um nome (`TestAColisaoDeIdentidade`);
  2. a contenção compara por SEGMENTO, não por texto — a regra que o
     `s3_folder_relink.reescrever_prefixo` já tinha e que as guardas de
     posse nunca aprenderam (`TestAFronteiraDeSegmento`).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services import s3_document_root as raiz


# ────────────────────────────────────────────────────────────────────
# 1) A IDENTIDADE SAI DO ID, NUNCA DO NOME
# ────────────────────────────────────────────────────────────────────

CID_CAROLINA_1 = "11111111-1111-4111-8111-111111111111"
CID_CAROLINA_2 = "22222222-2222-4222-8222-222222222222"
PID = "33333333-3333-4333-8333-333333333333"


class TestAColisaoDeIdentidade:
    """Duas clientes de nome parecido NUNCA partilham pasta."""

    def test_nomes_que_colidiam_no_fuzzy_dao_pastas_DIFERENTES(self):
        # "Carolina Silva" e "Carolina Agostinho da Silva" davam 0.867.
        a = raiz.pasta_do_cliente(CID_CAROLINA_1)
        b = raiz.pasta_do_cliente(CID_CAROLINA_2)
        assert a != b
        # E nenhuma contém a outra — o caso que o `startswith` autorizava.
        assert not raiz.dentro_da_pasta(b, a)
        assert not raiz.dentro_da_pasta(a, b)

    def test_o_nome_do_cliente_NAO_entra_no_caminho(self):
        pasta = raiz.pasta_do_cliente(CID_CAROLINA_1)
        for pedaco in ("Carolina", "carolina", "Silva", "silva"):
            assert pedaco not in pasta

    def test_o_mesmo_id_da_sempre_a_mesma_pasta(self):
        assert raiz.pasta_do_cliente(CID_CAROLINA_1) == raiz.pasta_do_cliente(
            CID_CAROLINA_1
        )

    def test_a_pasta_do_cliente_vive_na_raiz_canonica(self):
        # A mesma raiz que `assert_path_within_document_root` exige e que o
        # Explorador usa: uma raiz nova obrigaria a alargar a guarda.
        assert raiz.pasta_do_cliente(CID_CAROLINA_1).startswith(raiz.RAIZ)


class TestAPastaDoProcesso:
    """Documentos do cliente na raiz, do processo na subpasta."""

    def test_o_processo_e_subpasta_do_cliente(self):
        pasta_cliente = raiz.pasta_do_cliente(CID_CAROLINA_1)
        pasta_processo = raiz.pasta_do_processo(PID, client_id=CID_CAROLINA_1)
        assert raiz.dentro_da_pasta(pasta_processo, pasta_cliente)
        assert pasta_processo == f"{pasta_cliente}/{raiz.SEGMENTO_DOS_PROCESSOS}/{PID}"

    def test_dois_processos_do_MESMO_cliente_nao_se_misturam(self):
        p1 = raiz.pasta_do_processo("aaaa-1111-2222-3333", client_id=CID_CAROLINA_1)
        p2 = raiz.pasta_do_processo("bbbb-1111-2222-3333", client_id=CID_CAROLINA_1)
        assert p1 != p2
        assert not raiz.dentro_da_pasta(p1, p2)

    def test_processo_SEM_cliente_cai_no_proprio_id(self):
        # Há processos criados sem `client_id` (fluxos antigos e a Sala de
        # Triagem). Sem identidade do cliente, a identidade é o processo —
        # nunca um nome, que é o que produzia a colisão.
        pasta = raiz.pasta_do_processo(PID, client_id=None)
        assert pasta == f"{raiz.RAIZ}{PID}"

    def test_a_subpasta_dos_processos_nao_colide_com_uma_categoria(self):
        from services.s3_storage import DEFAULT_CATEGORIES, sanitize_folder_name

        nomes = {sanitize_folder_name(c).lower() for c in DEFAULT_CATEGORIES}
        nomes |= {c.lower() for c in DEFAULT_CATEGORIES}
        assert raiz.SEGMENTO_DOS_PROCESSOS.lower() not in nomes


class TestIdsQueNaoServem:
    """Um id que não serve como segmento recusa-se — não se adivinha."""

    @pytest.mark.parametrize(
        "mau",
        [
            None, "", "   ", "ab",
            "../../backups", "a/b", "a\\b", "com espaco",
            ".oculto", "x" * 100,
        ],
    )
    def test_id_invalido_nao_da_pasta(self, mau):
        assert raiz.pasta_do_cliente(mau) is None
        assert raiz.pasta_do_processo(mau) is None

    def test_processo_valido_com_cliente_invalido_usa_o_processo(self):
        # Degradar para o id do PROCESSO é seguro; degradar para o nome
        # não é, e era isso que existia.
        assert raiz.pasta_do_processo(PID, client_id="../backups") == (
            f"{raiz.RAIZ}{PID}"
        )

    def test_uma_pasta_derivada_fica_SEMPRE_dentro_da_raiz(self):
        for cid in (CID_CAROLINA_1, PID, "a-b-c"):
            pasta = raiz.pasta_do_cliente(cid)
            assert pasta is not None
            assert pasta.startswith(raiz.RAIZ)
            assert ".." not in pasta


# ────────────────────────────────────────────────────────────────────
# 2) A FRONTEIRA DE SEGMENTO
# ────────────────────────────────────────────────────────────────────

class TestAFronteiraDeSegmento:
    """`Carolina Silva` NÃO contém `Carolina Silva Agostinho`.

    É a regra que o `reescrever_prefixo` do relink já aplicava («`Joao_Silva_2`
    começa pelo mesmo texto e é OUTRO cliente») e que as guardas de posse
    comparavam com um `startswith` cru.
    """

    @pytest.mark.parametrize(
        "caminho,pasta",
        [
            ("Documentação Clientes/Carolina Silva Agostinho/Financeiros/irs.pdf",
             "Documentação Clientes/Carolina Silva"),
            ("Documentação Clientes/Joao_Silva_2/RGPD/x.pdf",
             "Documentação Clientes/Joao_Silva"),
            ("Documentação Clientes/Ana Costa Lima/x.pdf",
             "Documentação Clientes/Ana Costa"),
        ],
    )
    def test_o_vizinho_de_nome_mais_longo_fica_FORA(self, caminho, pasta):
        assert raiz.dentro_da_pasta(caminho, pasta) is False

    @pytest.mark.parametrize(
        "caminho,pasta",
        [
            ("Documentação Clientes/Joao_Silva/RGPD/x.pdf",
             "Documentação Clientes/Joao_Silva"),
            ("Documentação Clientes/Joao_Silva/RGPD/x.pdf",
             "Documentação Clientes/Joao_Silva/"),
            ("Documentação Clientes/Joao_Silva", "Documentação Clientes/Joao_Silva"),
        ],
    )
    def test_o_proprio_e_o_que_esta_dentro_passam(self, caminho, pasta):
        assert raiz.dentro_da_pasta(caminho, pasta) is True

    def test_pasta_vazia_nao_autoriza_nada(self):
        # O degradado com nome vazio aceitava toda a raiz de documentos.
        assert raiz.dentro_da_pasta("Documentação Clientes/x/y.pdf", "") is False
        assert raiz.dentro_da_pasta("Documentação Clientes/x/y.pdf", None) is False


# ────────────────────────────────────────────────────────────────────
# 3) O QUE SE LÊ QUANDO SE ABRE UM PROCESSO
# ────────────────────────────────────────────────────────────────────

class TestOQueSeLeNumProcesso:
    """Os documentos do cliente continuam visíveis no processo.

    Com a pasta do processo DENTRO da do cliente, listar só a do processo
    esconderia o que o cliente enviou antes de o processo existir (todo o
    onboarding do Portal). Um documento que desaparece não dá erro
    nenhum — por isso a união é explícita e tem teste.
    """

    def test_a_pasta_legada_le_se_tal_e_qual(self):
        # 12.450 pastas existentes continuam a ser lidas pelo caminho
        # gravado, sem mudança nenhuma de comportamento.
        leituras = raiz.leituras_do_mapeamento("Documentação Clientes/Joao_Silva")
        assert [l.prefixo for l in leituras] == ["Documentação Clientes/Joao_Silva"]
        assert leituras[0].excluir_processos is False

    def test_a_pasta_de_um_processo_le_TAMBEM_a_raiz_do_cliente(self):
        pasta_cliente = raiz.pasta_do_cliente(CID_CAROLINA_1)
        pasta_processo = raiz.pasta_do_processo(PID, client_id=CID_CAROLINA_1)
        leituras = raiz.leituras_do_mapeamento(pasta_processo)
        prefixos = [l.prefixo for l in leituras]
        assert prefixos == [pasta_processo, pasta_cliente]

    def test_a_raiz_do_cliente_e_lida_SEM_os_processos(self):
        pasta_processo = raiz.pasta_do_processo(PID, client_id=CID_CAROLINA_1)
        leituras = raiz.leituras_do_mapeamento(pasta_processo)
        raiz_do_cliente = [l for l in leituras if l.excluir_processos]
        assert len(raiz_do_cliente) == 1
        assert raiz_do_cliente[0].prefixo == raiz.pasta_do_cliente(CID_CAROLINA_1)

    def test_o_processo_IRMAO_nunca_entra(self):
        # É a diferença entre "o cliente também é meu" e "o processo do lado".
        pasta_a = raiz.pasta_do_processo("aaaa-1111-2222-3333", client_id=CID_CAROLINA_1)
        leituras = raiz.leituras_do_mapeamento(pasta_a)
        chave_do_irmao = (
            f"{raiz.pasta_do_processo('bbbb-1111-2222-3333', client_id=CID_CAROLINA_1)}"
            "/Financeiros/irs.pdf"
        )
        assert not any(
            raiz.chave_pertence_a_leitura(chave_do_irmao, l) for l in leituras
        )

    def test_o_documento_do_ONBOARDING_entra(self):
        pasta_a = raiz.pasta_do_processo("aaaa-1111-2222-3333", client_id=CID_CAROLINA_1)
        leituras = raiz.leituras_do_mapeamento(pasta_a)
        chave = f"{raiz.pasta_do_cliente(CID_CAROLINA_1)}/Financeiros/irs.pdf"
        assert any(raiz.chave_pertence_a_leitura(chave, l) for l in leituras)

    def test_o_documento_DO_processo_entra(self):
        pasta_a = raiz.pasta_do_processo("aaaa-1111-2222-3333", client_id=CID_CAROLINA_1)
        leituras = raiz.leituras_do_mapeamento(pasta_a)
        chave = f"{pasta_a}/Financeiros/irs.pdf"
        assert any(raiz.chave_pertence_a_leitura(chave, l) for l in leituras)

    def test_a_pasta_do_cliente_le_a_raiz_e_os_processos_dele(self):
        # Na ficha do CLIENTE mostra-se tudo o que é dele.
        pasta_cliente = raiz.pasta_do_cliente(CID_CAROLINA_1)
        leituras = raiz.leituras_do_mapeamento(pasta_cliente)
        assert [l.prefixo for l in leituras] == [pasta_cliente]
        assert leituras[0].excluir_processos is False


# ────────────────────────────────────────────────────────────────────
# 4) AS LIGAÇÕES (sem elas, o ponto único é decoração)
# ────────────────────────────────────────────────────────────────────

class TestARaizEUmaSo:
    """Três módulos declaram a raiz; têm de declarar a MESMA."""

    def test_a_guarda_de_seguranca_usa_a_mesma_raiz(self):
        from services.document_process_resolve import DOCUMENT_S3_ROOT_PREFIX

        assert DOCUMENT_S3_ROOT_PREFIX == raiz.RAIZ

    def test_o_explorador_usa_a_mesma_raiz(self):
        from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR

        assert RAIZ_DO_EXPLORADOR.rstrip("/") == raiz.RAIZ.rstrip("/")


class TestOsCaminhosAutomaticosNaoProcuramPorNome:
    """Guarda sobre a FONTE: o caminho de escrita não vê nomes.

    Cada uma destas vem com a contraprova ao lado — "o sítio certo chama
    mesmo X" —, senão apagar a chamada satisfaria o guarda.
    """

    def _fonte(self, funcao):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        return codigo_da_funcao_sem_comentarios(funcao)

    def test_ensure_mapping_nao_procura_pasta_por_nome(self):
        from services.s3_storage import S3Service

        fonte = self._fonte(S3Service.ensure_client_folder_mapping)
        assert "_find_client_folder" not in fonte
        # Contraprova: continua a criar a estrutura.
        assert "initialize_client_folders" in fonte

    def test_initialize_folders_nao_procura_pasta_por_nome(self):
        from services.s3_storage import S3Service

        fonte = self._fonte(S3Service.initialize_client_folders)
        assert "_find_client_folder" not in fonte
        assert "_get_client_base_path_for_upload" in fonte

    def test_o_construtor_do_caminho_deriva_do_modulo_unico(self):
        from services.s3_storage import S3Service

        fonte = self._fonte(S3Service._get_client_base_path_for_upload)
        assert "pasta_do_cliente" in fonte
        assert "pasta_do_processo" in fonte
        # E não há nenhum literal de caminho construído à mão.
        assert "Documentação Clientes/" not in fonte

    def test_a_funcao_com_o_incrementador_morto_NAO_voltou(self):
        """`_get_client_base_path` acrescentava `_2`/`_3` e não tinha um único
        chamador — e era ela que sustentava a ideia, escrita no
        `s3_folder_relink`, de que o sistema desambiguava homónimos."""
        from services.s3_storage import S3Service

        assert not hasattr(S3Service, "_get_client_base_path")

    def test_a_atribuicao_de_cliente_nao_constroi_o_caminho_a_mao(self):
        import services.client_assign as mod
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(open(mod.__file__, encoding="utf-8").read())
        assert "pasta_do_processo(process_id, client_id=client_id)" in fonte.replace(
            "'", '"'
        )
        # Contraprova: nenhum caminho de documentos escrito à mão sobrou.
        assert "Documentação Clientes/" not in fonte


class TestQuemAindaPodeProcurarPorNome:
    """A procura por nome não foi apagada — foi despromovida.

    Continua a servir a LEITURA de um processo legado sem mapeamento (não
    devolver nada esconderia documentos que existem) e a sugestão ao
    administrador no religamento manual. O que deixou de fazer é decidir
    onde um upload NOVO vai.
    """

    # INVERTIDOS no Lote 8 (D-19 fechada). Estes três testes afirmavam
    # que a procura por nome existia e era EXACTA — o Lote 6 tirou-lhe o
    # score e manteve-a para ler fichas legadas. A medição em produção
    # contou zero fichas a depender dela e o recurso foi apagado, logo a
    # pergunta mudou: já não é «o match é exacto?», é «ele não voltou?».
    # Invertidos em vez de apagados, porque um teste apagado não impede o
    # regresso do defeito que ele descrevia.

    def test_a_procura_por_NOME_foi_apagada_do_servico(self):
        from services.s3_storage import S3Service

        for funcao in (
            "_find_client_folder_combined",
            "_find_client_folder",
            "_nomes_de_pasta_candidatos",
            "_get_possible_client_paths",
        ):
            assert not hasattr(S3Service, funcao), (
                f"`{funcao}` voltou ao S3Service — era por aqui que a "
                "«Carolina Agostinho da Silva» herdava a pasta da "
                "«Carolina Silva»"
            )

    def test_nem_o_match_EXACTO_sobreviveu(self):
        # Não foi uma despromoção, foi um corte: mesmo o match exacto saiu,
        # porque dois homónimos EXACTOS continuavam a partilhar pasta — o
        # resíduo que mantinha a D-19 aberta.
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = (
            Path(__file__).resolve().parents[2] / "services" / "s3_storage.py"
        )
        with open(caminho, encoding="utf-8") as fh:
            fonte = codigo_sem_comentarios(fh.read())
        assert "def list_files" in fonte, "o leitor não leu o módulo certo"
        for vestigio in ("best_score", "intersection", "name_variations"):
            assert vestigio not in fonte, f"o match por nome voltou: {vestigio}"

    def test_a_identidade_passou_a_vir_SO_do_id(self):
        # Contraprova no sentido oposto: apagar a procura por nome não pode
        # ter levado a derivação canónica com ela.
        assert raiz.pasta_do_cliente("0b1c2d3e-4f50-6171-8291-a2b3c4d5e6f7")
        assert raiz.pasta_do_processo(
            "0b1c2d3e-4f50-6171-8291-a2b3c4d5e6f7",
            client_id="11111111-1111-1111-1111-111111111111",
        )


class TestOProcessoQueHERDAAPastaDoCliente:
    """`onboarding_mandatory_config` cria o processo a herdar o `s3_folder`.

    Herdar a RAIZ do cliente faria a leitura do processo trazer os documentos
    dos outros processos dele. Trocar o mapeamento quando o cliente tem uma
    pasta LEGADA (ou escolhida à mão) é pior ainda: os documentos estão lá e o
    processo passaria a olhar para uma pasta vazia.
    """

    def test_cliente_na_raiz_CANONICA_da_subpasta_ao_processo(self):
        pasta = raiz.pasta_do_processo_sob_mapeamento_do_cliente(
            PID, CID_CAROLINA_1, raiz.pasta_do_cliente(CID_CAROLINA_1)
        )
        assert pasta == raiz.pasta_do_processo(PID, client_id=CID_CAROLINA_1)

    def test_cliente_SEM_mapeamento_da_subpasta_ao_processo(self):
        pasta = raiz.pasta_do_processo_sob_mapeamento_do_cliente(
            PID, CID_CAROLINA_1, None
        )
        assert pasta == raiz.pasta_do_processo(PID, client_id=CID_CAROLINA_1)

    def test_pasta_LEGADA_do_cliente_e_herdada_tal_e_qual(self):
        legada = "Documentação Clientes/Carolina_Silva"
        pasta = raiz.pasta_do_processo_sob_mapeamento_do_cliente(
            PID, CID_CAROLINA_1, legada
        )
        assert pasta == legada

    def test_pasta_escolhida_A_MAO_e_herdada_tal_e_qual(self):
        escolhida = "Documentação Clientes/pasta-religada-pelo-admin"
        pasta = raiz.pasta_do_processo_sob_mapeamento_do_cliente(
            PID, CID_CAROLINA_1, escolhida
        )
        assert pasta == escolhida

    def test_a_barra_final_nao_muda_a_decisao(self):
        # Um `s3_folder` gravado com barra final não pode parecer "diferente"
        # da raiz canónica e disparar a herança do legado.
        com_barra = raiz.pasta_do_cliente(CID_CAROLINA_1) + "/"
        pasta = raiz.pasta_do_processo_sob_mapeamento_do_cliente(
            PID, CID_CAROLINA_1, com_barra
        )
        assert pasta == raiz.pasta_do_processo(PID, client_id=CID_CAROLINA_1)

    def test_a_criacao_por_onboarding_usa_o_ponto_unico(self):
        import services.onboarding_mandatory_config as mod
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(open(mod.__file__, encoding="utf-8").read())
        assert "pasta_do_processo_sob_mapeamento_do_cliente" in fonte
        # Contraprova: já não herda o campo do cliente às cegas.
        assert 's3_folder = client.get("s3_folder")' not in fonte.replace("'", '"')


class TestDuasPerguntasDiferentesSobreUmId:
    """`id_valido` e `e_id_gerado` respondem a coisas diferentes.

    A primeira pergunta "serve como segmento de caminho?"; a segunda, "isto
    foi gerado por nós?". Um nome sanitizado (`Rui_Pereira`) responde SIM à
    primeira — e foi usá-la pela segunda que fez um reparador de nomes deixar
    de reparar nomes legítimos.
    """

    def test_um_nome_sanitizado_serve_de_segmento_mas_nao_e_um_id(self):
        assert raiz.id_valido("Rui_Pereira") is True
        assert raiz.e_id_gerado("Rui_Pereira") is False

    def test_um_uuid_e_as_duas_coisas(self):
        assert raiz.id_valido(CID_CAROLINA_1) is True
        assert raiz.e_id_gerado(CID_CAROLINA_1) is True

    def test_um_id_legado_nao_uuid_falha_para_o_lado_ANTIGO(self):
        # Responder `False` faz quem pergunta tratar a pasta como pasta por
        # nome, que é o comportamento anterior — seguro.
        assert raiz.e_id_gerado("cli-1") is False

    @pytest.mark.parametrize("mau", [None, "", "11111111-1111-4111-8111", 12345])
    def test_o_que_nao_e_uuid(self, mau):
        assert raiz.e_id_gerado(mau) is False
