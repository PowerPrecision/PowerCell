"""
Testes unitários — `S3Service.ensure_client_folder_mapping`

Garante a criação/recuperação robusta de mapeamentos S3 em falta,
usada tanto nos fluxos normais (upload do Portal) como pelo script
de recuperação `backend/scripts/hotfix_restore_s3_mappings.py`.

LOTE 6 — QUATRO DESTES TESTES FORAM INVERTIDOS, NÃO APAGADOS
============================================================
Afirmavam o passo do meio da resolução: "não há mapeamento gravado, logo
procura-se uma pasta parecida POR NOME e reutiliza-se". Era esse passo que
punha os documentos de uma cliente nova na pasta de uma existente
(score 0.867 entre "Carolina Agostinho da Silva" e `carolina_silva`).

Ficam a afirmar o CONTRÁRIO, porque um teste apagado perde a memória de que
aquele comportamento existiu — e alguém o reintroduz como "optimização para
evitar pastas duplicadas", que é exactamente como nasceu.
"""
from unittest.mock import MagicMock

from services.s3_storage import S3Service


def _make_service(configured=True):
    service = S3Service.__new__(S3Service)  # bypass __init__ (evita boto3 real)
    service.s3_client = MagicMock() if configured else None
    service.bucket_name = "test-bucket" if configured else None
    return service


class TestEnsureClientFolderMappingNotConfigured:
    def test_returns_failure_when_not_configured(self):
        service = _make_service(configured=False)
        result = service.ensure_client_folder_mapping("client-1", "João Silva")
        assert result == {
            "success": False,
            "s3_folder": None,
            "created": False,
            "reused_existing": False,
        }

    def test_sem_nome_JA_cria_pasta_porque_a_identidade_e_o_ID(self):
        """INVERTIDO (Lote 6): o nome deixou de ser requisito.

        Exigir nome era negar pasta — e portanto documentação — a uma ficha
        que a UI deixa criar sem nome. O caminho não depende do nome.
        """
        service = _make_service(configured=True)
        service.initialize_client_folders = MagicMock(
            return_value=(True, "Documentação Clientes/client-1")
        )
        result = service.ensure_client_folder_mapping("client-1", "")
        assert result["success"] is True
        assert result["s3_folder"] == "Documentação Clientes/client-1"


class TestEnsureClientFolderMappingReuseExisting:
    def test_reuses_valid_existing_mapping_without_creating(self):
        service = _make_service()
        service._folder_exists = MagicMock(return_value=True)
        service._find_client_folder_combined = MagicMock()
        service.initialize_client_folders = MagicMock()

        result = service.ensure_client_folder_mapping(
            "client-1", "João Silva", existing_s3_folder="Documentação Clientes/Joao_Silva"
        )

        assert result == {
            "success": True,
            "s3_folder": "Documentação Clientes/Joao_Silva",
            "created": False,
            "reused_existing": True,
        }
        # Nunca deve tentar criar/procurar de novo se o existente é válido.
        service._find_client_folder_combined.assert_not_called()
        service.initialize_client_folders.assert_not_called()

    def test_mapeamento_invalido_NAO_procura_por_nome(self):
        """INVERTIDO: `"undefined"` gravado já não manda procurar uma pasta
        parecida — deriva do id. Era por aqui que um cliente apanhava a pasta
        do homónimo com o sufixo `_2`, que é OUTRA pessoa."""
        service = _make_service()
        service._folder_exists = MagicMock(return_value=False)
        service._find_client_folder_combined = MagicMock(
            return_value="Documentação Clientes/Joao_Silva_2"
        )
        service.initialize_client_folders = MagicMock(
            return_value=(True, "Documentação Clientes/client-1")
        )

        result = service.ensure_client_folder_mapping(
            "client-1", "João Silva", existing_s3_folder="undefined"
        )

        assert result["s3_folder"] == "Documentação Clientes/client-1"
        assert result["created"] is True
        service._find_client_folder_combined.assert_not_called()

    def test_pasta_gravada_que_desapareceu_NAO_procura_por_nome(self):
        """INVERTIDO: a pasta gravada já não existe no S3 (apagada à mão).

        Antes procurava-se uma parecida pelo nome; hoje cria-se a pasta por id.
        A diferença importa: "a pasta deste cliente desapareceu" e "existe uma
        pasta com um nome parecido" são afirmações diferentes, e tratar a
        segunda como resposta à primeira é o defeito.
        """
        service = _make_service()
        service._folder_exists = MagicMock(return_value=False)
        service._find_client_folder_combined = MagicMock(
            return_value="Documentação Clientes/Joao_Silva"
        )
        service.initialize_client_folders = MagicMock(
            return_value=(True, "Documentação Clientes/client-1")
        )

        result = service.ensure_client_folder_mapping(
            "client-1", "João Silva",
            existing_s3_folder="Documentação Clientes/Pasta_Apagada",
        )

        assert result["s3_folder"] == "Documentação Clientes/client-1"
        service._find_client_folder_combined.assert_not_called()


class TestEnsureClientFolderMappingCreateNew:
    def test_creates_new_folder_when_nothing_found(self):
        service = _make_service()
        service._find_client_folder_combined = MagicMock(return_value=None)
        service._folder_exists = MagicMock(return_value=False)
        service.initialize_client_folders = MagicMock(return_value=(True, "Documentação Clientes/Novo_Cliente"))

        result = service.ensure_client_folder_mapping("client-2", "Novo Cliente", existing_s3_folder=None)

        assert result == {
            "success": True,
            "s3_folder": "Documentação Clientes/Novo_Cliente",
            "created": True,
            "reused_existing": False,
        }

    def test_returns_failure_when_creation_fails(self):
        service = _make_service()
        service._find_client_folder_combined = MagicMock(return_value=None)
        service.initialize_client_folders = MagicMock(return_value=(False, None))

        result = service.ensure_client_folder_mapping("client-3", "Cliente Falhado")

        assert result["success"] is False
        assert result["s3_folder"] is None

    def test_handles_unexpected_exception_gracefully(self):
        service = _make_service()
        service._find_client_folder_combined = MagicMock(return_value=None)
        service.initialize_client_folders = MagicMock(side_effect=RuntimeError("boom"))

        result = service.ensure_client_folder_mapping("client-4", "Cliente Erro")

        assert result["success"] is False
        assert result["s3_folder"] is None

    def test_o_2o_titular_JA_NAO_entra_no_caminho(self):
        """INVERTIDO: o nome do 2.º titular ia para o nome da pasta
        (`Joao_Silva_e_Maria_Santos`), o que fazia a pasta MUDAR quando se
        acrescentava ou removia um titular. Com a pasta derivada do id, o nome
        só serve para o log — e por isso o nome dos titulares já não é
        argumento de posicionamento do caminho."""
        service = _make_service()
        service._find_client_folder_combined = MagicMock(return_value=None)
        service.initialize_client_folders = MagicMock(
            return_value=(True, "Documentação Clientes/client-5")
        )

        result = service.ensure_client_folder_mapping(
            "client-5", "João Silva", second_client_name="Maria Santos"
        )

        service._find_client_folder_combined.assert_not_called()
        chamada = service.initialize_client_folders.call_args
        assert chamada.args == ("client-5", "João Silva", "Maria Santos")
        assert chamada.kwargs == {"owner_client_id": None}
        assert result["s3_folder"] == "Documentação Clientes/client-5"
