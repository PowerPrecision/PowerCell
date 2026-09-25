"""A medição da cobertura pasta ↔ processo (Épico 10, Gestor S3, Passo 2)."""
from __future__ import annotations

from services.s3_folder_coverage import (
    analisar,
    formatar_relatorio,
    nome_da_pasta,
    normalizar_para_comparacao,
)
from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR

R = RAIZ_DO_EXPLORADOR


def pasta(nome):
    return f"{R}/{nome}"


def processo(pid, *, folder=None, rede="grupo_power_precision", nome="Joao Silva"):
    doc = {"id": pid, "network_id": rede, "client_name": nome}
    if folder:
        doc["s3_folder"] = folder
    return doc


class TestNomes:
    def test_nome_da_pasta_e_o_ultimo_segmento(self):
        assert nome_da_pasta(f"{R}/Joao_Silva/") == "Joao_Silva"
        assert nome_da_pasta(f"{R}/Joao_Silva") == "Joao_Silva"

    def test_normalizacao_ignora_acentos_e_capitalizacao(self):
        # Nomes gravados em épocas diferentes divergem; sem isto perdiam-se
        # correspondências óbvias no backfill.
        assert normalizar_para_comparacao("João Silva") == normalizar_para_comparacao("joao_silva")
        assert normalizar_para_comparacao("MARIA  SANTOS") == "maria_santos"


class TestContagens:
    def test_pasta_com_dono_conta_como_mapeada(self):
        c = analisar([pasta("Joao_Silva")], [processo("p1", folder=pasta("Joao_Silva"))])
        assert c.mapeadas == 1
        assert c.orfas == []
        assert c.percentagem_mapeada == 100.0

    def test_pasta_sem_dono_e_orfa(self):
        c = analisar([pasta("Antiga")], [processo("p1", folder=pasta("Joao_Silva"))])
        assert c.orfas == [pasta("Antiga")]
        assert c.mapeadas == 0

    def test_pasta_reclamada_por_duas_redes_e_ambigua(self):
        """A mais perigosa: mostrar à "primeira" seria escolher à sorte
        qual das redes vê os documentos da outra."""
        c = analisar(
            [pasta("Joao_Silva")],
            [
                processo("p1", folder=pasta("Joao_Silva"), rede="grupo_power_precision"),
                processo("p2", folder=pasta("Joao_Silva"), rede="domus"),
            ],
        )
        assert c.ambiguas == [pasta("Joao_Silva")]

    def test_dois_processos_da_MESMA_rede_nao_e_ambiguo(self):
        # Um cliente com dois processos na mesma empresa é o caso normal.
        c = analisar(
            [pasta("Joao_Silva")],
            [
                processo("p1", folder=pasta("Joao_Silva")),
                processo("p2", folder=pasta("Joao_Silva")),
            ],
        )
        assert c.ambiguas == []
        assert c.mapeadas == 1

    def test_processo_sem_rede_nao_torna_a_pasta_ambigua(self):
        """Por carimbar não é "outra rede" — é ausência de carimbo."""
        c = analisar(
            [pasta("Joao_Silva")],
            [
                processo("p1", folder=pasta("Joao_Silva"), rede="domus"),
                processo("p2", folder=pasta("Joao_Silva"), rede=""),
            ],
        )
        assert c.ambiguas == []

    def test_ligacao_partida_quando_a_pasta_ja_nao_existe(self):
        """Sintoma típico de um `rename` no Explorador: move os objectos e
        deixa o `s3_folder` a apontar para o nome antigo."""
        c = analisar([pasta("Nome_Novo")], [processo("p1", folder=pasta("Nome_Antigo"))])
        assert c.ligacoes_partidas == [pasta("Nome_Antigo")]

    def test_barra_final_nao_conta_como_pasta_diferente(self):
        c = analisar([f"{R}/Joao_Silva/"], [processo("p1", folder=pasta("Joao_Silva"))])
        assert c.mapeadas == 1
        assert c.ligacoes_partidas == []

    def test_bucket_vazio_nao_rebenta(self):
        c = analisar([], [])
        assert c.percentagem_mapeada == 0.0
        assert c.pastas_no_s3 == 0


class TestPropostasDeBackfill:
    def test_propoe_quando_ha_um_unico_candidato(self):
        c = analisar(
            [pasta("Joao_Silva")],
            [processo("p1", nome="João Silva")],
        )
        assert c.orfas_resoluveis == {pasta("Joao_Silva"): "p1"}

    def test_recusa_escolher_com_dois_candidatos(self):
        """Um mapeamento errado torna a pasta visível à rede errada, e a
        execução seguinte aceitá-lo-ia como verdade."""
        c = analisar(
            [pasta("Joao_Silva")],
            [
                processo("p1", nome="Joao Silva", rede="domus"),
                processo("p2", nome="João Silva", rede="grupo_power_precision"),
            ],
        )
        assert c.orfas_resoluveis == {}

    def test_nao_rouba_um_mapeamento_existente(self):
        # Um processo que JÁ tem pasta não é candidato a outra.
        c = analisar(
            [pasta("Joao_Silva"), pasta("Orfa")],
            [processo("p1", folder=pasta("Joao_Silva"), nome="Orfa")],
        )
        assert c.orfas_resoluveis == {}

    def test_sem_nome_de_cliente_nao_ha_proposta(self):
        c = analisar([pasta("Joao_Silva")], [processo("p1", nome="")])
        assert c.orfas_resoluveis == {}


class TestRelatorio:
    def test_mostra_os_quatro_numeros_que_decidem(self):
        c = analisar(
            [pasta("A"), pasta("B")],
            [processo("p1", folder=pasta("A"))],
        )
        texto = formatar_relatorio(c)
        for esperado in ["Pastas no S3", "Mapeadas", "ÓRFÃS", "AMBÍGUAS", "Ligações partidas"]:
            assert esperado in texto

    def test_lista_as_ambiguas_pelo_nome(self):
        c = analisar(
            [pasta("Partilhada")],
            [
                processo("p1", folder=pasta("Partilhada"), rede="domus"),
                processo("p2", folder=pasta("Partilhada"), rede="grupo_power_precision"),
            ],
        )
        assert "Partilhada" in formatar_relatorio(c)
