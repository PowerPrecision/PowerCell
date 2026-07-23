"""
Testes unitários — `S3Service.ensure_client_folder_mapping`

Garante a criação/recuperação robusta de mapeamentos S3 em falta,
usada tanto nos fluxos normais (upload do Portal) como pelo script
de recuperação `backend/scripts/hotfix_restore_s3_mappings.py`.
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

    def test_returns_failure_when_no_client_name(self):
        service = _make_service(configured=True)
        result = service.ensure_client_folder_mapping("client-1", "")
        assert result["success"] is False


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

    def test_ignores_invalid_existing_values_and_searches_again(self):
        service = _make_service()
        service._folder_exists = MagicMock(return_value=False)
        service._find_client_folder_combined = MagicMock(return_value="Documentação Clientes/Joao_Silva_2")
        service.initialize_client_folders = MagicMock()

        result = service.ensure_client_folder_mapping(
            "client-1", "João Silva", existing_s3_folder="undefined"
        )

        assert result["success"] is True
        assert result["s3_folder"] == "Documentação Clientes/Joao_Silva_2"
        assert result["reused_existing"] is True
        service.initialize_client_folders.assert_not_called()

    def test_stale_existing_folder_falls_back_to_search(self):
        """Pasta guardada na BD já não existe no S3 (ex.: apagada
        manualmente) — deve procurar de novo por nome antes de criar."""
        service = _make_service()
        service._folder_exists = MagicMock(return_value=False)
        service._find_client_folder_combined = MagicMock(return_value="Documentação Clientes/Joao_Silva")
        service.initialize_client_folders = MagicMock()

        result = service.ensure_client_folder_mapping(
            "client-1", "João Silva", existing_s3_folder="Documentação Clientes/Pasta_Apagada"
        )

        assert result["s3_folder"] == "Documentação Clientes/Joao_Silva"
        assert result["reused_existing"] is True
        service.initialize_client_folders.assert_not_called()


class TestEnsureClientFolderMappingCreateNew:
    def test_creates_new_folder_when_nothing_found(self):
        service = _make_service()
        service._find_client_folder_combined = MagicMock(return_value=None)
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

    def test_passes_second_client_name_through(self):
        service = _make_service()
        service._find_client_folder_combined = MagicMock(return_value=None)
        service.initialize_client_folders = MagicMock(return_value=(True, "Documentação Clientes/Joao_e_Maria"))

        result = service.ensure_client_folder_mapping(
            "client-5", "João Silva", second_client_name="Maria Santos"
        )

        service._find_client_folder_combined.assert_called_once_with("João Silva", "Maria Santos")
        service.initialize_client_folders.assert_called_once_with("client-5", "João Silva", "Maria Santos")
        assert result["s3_folder"] == "Documentação Clientes/Joao_e_Maria"
