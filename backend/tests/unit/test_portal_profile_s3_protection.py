"""
Testes unitários — Hotfix: Portal do Cliente NUNCA deve apagar/sobrescrever
mapeamentos S3 (s3_folder, etc.) ou relações com processos ao atualizar
o perfil (PUT /portal/me → services/portal_profile.py).

Cobre:
- `build_portal_profile_mongo_update`: gera o dict de atualização
  MongoDB apenas com os campos whitelisted, usando $set granular
  (notação de ponto), nunca substituindo sub-documentos inteiros.
- `_assert_no_protected_fields`: rede de segurança que bloqueia
  qualquer tentativa de escrever campos internos protegidos.
"""
from services.portal_profile import (
    build_portal_profile_mongo_update,
    _assert_no_protected_fields,
    ClientProfileUpdate,
    PORTAL_PROTECTED_CLIENT_FIELDS,
    PROFILE_UPDATABLE_CONTACT_FIELDS,
    PROFILE_UPDATABLE_PERSONAL_FIELDS,
)

NOW = "2026-07-23T12:00:00+00:00"


class TestAssertNoProtectedFields:
    """A rede de segurança final nunca deve deixar passar campos internos."""

    def test_strips_s3_folder(self):
        result = _assert_no_protected_fields({
            "contacto.telefone": "912345678",
            "s3_folder": "Documentação Clientes/Hacker",
        })
        assert "s3_folder" not in result
        assert result["contacto.telefone"] == "912345678"

    def test_strips_dotted_protected_keys(self):
        # Mesmo com notação de ponto, a chave de topo-de-nível é o que conta.
        result = _assert_no_protected_fields({
            "s3_folder_path.nested": "x",
            "process_ids": ["p1"],
            "dados_pessoais.profissao": "Engenheiro",
        })
        assert result == {"dados_pessoais.profissao": "Engenheiro"}

    def test_all_protected_fields_are_blocked(self):
        payload = {field: "malicious" for field in PORTAL_PROTECTED_CLIENT_FIELDS}
        payload["contacto.email"] = "safe@example.com"
        result = _assert_no_protected_fields(payload)
        assert result == {"contacto.email": "safe@example.com"}

    def test_empty_input_returns_empty(self):
        assert _assert_no_protected_fields({}) == {}


class TestBuildPortalProfileMongoUpdate:
    """Verifica que a atualização de perfil do Portal é sempre segura."""

    def test_only_whitelisted_contact_fields_pass_through(self):
        data = ClientProfileUpdate(contacto={
            "telefone": "912345678",
            "email": "cliente@example.com",
            # Campo NÃO permitido — deve ser ignorado silenciosamente.
            "s3_folder": "Documentação Clientes/Hacker",
        })
        update = build_portal_profile_mongo_update(data, existing_client={}, now=NOW)

        assert "s3_folder" not in update
        assert update["contacto.telefone"] == "912345678"
        assert "contacto.email" in update
        assert update["updated_at"] == NOW

    def test_only_whitelisted_personal_fields_pass_through(self):
        data = ClientProfileUpdate(dados_pessoais={
            "profissao": "Engenheiro Civil",
            "nif": "123456789",  # NIF NUNCA pode ser alterado pelo cliente
        })
        update = build_portal_profile_mongo_update(data, existing_client={}, now=NOW)

        assert update["dados_pessoais.profissao"] == "Engenheiro Civil"
        assert "dados_pessoais.nif" not in update

    def test_never_touches_s3_or_process_fields(self):
        """Regressão do bug crítico: garantir que nenhum caminho de código
        permite que a atualização do Portal contenha chaves de topo-de-nível
        que substituam s3_folder, s3_mapping_id ou process_ids."""
        data = ClientProfileUpdate(
            contacto={"telefone": "911111111", "email": "a@b.pt"},
            dados_pessoais={"profissao": "Médica", "estado_civil": "Casado"},
        )
        existing_client = {
            "process_ids": ["proc-1", "proc-2"],
            "s3_folder": "Documentação Clientes/Joao_Silva",
            "field_metadata": {"dados_pessoais.nif": {"source": "manual"}},
        }
        update = build_portal_profile_mongo_update(data, existing_client, NOW)

        forbidden_top_level = {"s3_folder", "s3_folder_path", "s3_mapping_id", "process_ids", "id"}
        touched_top_level = {key.split(".", 1)[0] for key in update}
        assert touched_top_level.isdisjoint(forbidden_top_level)

        # Apenas $set granular — nunca substitui contacto/dados_pessoais como um todo.
        assert "contacto" not in update
        assert "dados_pessoais" not in update
        assert all(k.startswith(("contacto.", "dados_pessoais.")) or k in ("updated_at", "field_metadata") for k in update)

    def test_field_metadata_merges_without_losing_history(self):
        """Bug relacionado: a projeção do find_one tinha de incluir
        field_metadata, senão o histórico de proveniência era sempre apagado."""
        data = ClientProfileUpdate(contacto={"telefone": "919999999"})
        existing_client = {
            "field_metadata": {
                "dados_pessoais.nif": {"source": "manual", "updated_at": "2025-01-01T00:00:00+00:00"},
            }
        }
        update = build_portal_profile_mongo_update(data, existing_client, NOW)

        merged = update["field_metadata"]
        # Histórico anterior preservado...
        assert merged["dados_pessoais.nif"]["source"] == "manual"
        # ...e novo campo adicionado.
        assert merged["contacto.telefone"]["source"] == "client"

    def test_empty_payload_returns_empty_update(self):
        data = ClientProfileUpdate()
        update = build_portal_profile_mongo_update(data, existing_client={}, now=NOW)
        assert update == {}

    def test_only_disallowed_fields_returns_empty_update(self):
        data = ClientProfileUpdate(dados_pessoais={"nif": "123456789"})
        update = build_portal_profile_mongo_update(data, existing_client={}, now=NOW)
        assert update == {}

    def test_whitelists_are_disjoint_from_protected_fields(self):
        """Garantia estrutural: nenhum campo permitido colide com um campo protegido."""
        assert PROFILE_UPDATABLE_CONTACT_FIELDS.isdisjoint(PORTAL_PROTECTED_CLIENT_FIELDS)
        assert PROFILE_UPDATABLE_PERSONAL_FIELDS.isdisjoint(PORTAL_PROTECTED_CLIENT_FIELDS)
