"""Testes unitários para services/process_status (visibilidade de pré-registo)."""
from models.auth import UserRole
from services.process_status import (
    _should_hide_pre_registo,
    PRE_REGISTO_STATUS,
    INACTIVE_STATUSES,
    ARCHIVED_STATUSES,
    DELETED_STATUS_VALUES,
    STATUS_VALUE_ALIASES,
    LEAD_STATUS_VALUES,
    expand_status_values,
)


class TestShouldHidePreRegisto:
    def test_explicit_pre_registo_filter_never_hides(self):
        # Regra 3: filtrar explicitamente por pre_registo → mostrar
        for role in [UserRole.ADMIN, UserRole.CONSULTOR, UserRole.CEO]:
            assert _should_hide_pre_registo(role, PRE_REGISTO_STATUS, None) is False

    def test_admin_hides_by_default_on_boards(self):
        # Bypass role sem search nem status → esconde (não polui quadros)
        assert _should_hide_pre_registo(UserRole.ADMIN, None, None) is True
        assert _should_hide_pre_registo(UserRole.CEO, None, "") is True

    def test_admin_searching_shows_pre_registo(self):
        # Bypass role com search ativo → mostra
        assert _should_hide_pre_registo(UserRole.ADMIN, None, "joao") is False

    def test_admin_status_filter_shows(self):
        # Bypass role com filtro de status explícito → mostra
        assert _should_hide_pre_registo(UserRole.DIRETOR, "fase_documental", None) is False

    def test_consultor_always_hides(self):
        # Não-bypass: esconde sempre (mesmo a pesquisar)
        assert _should_hide_pre_registo(UserRole.CONSULTOR, None, None) is True
        assert _should_hide_pre_registo(UserRole.CONSULTOR, None, "joao") is True

    def test_consultor_explicit_pre_registo_still_shows(self):
        # Regra 3 tem prioridade mesmo para não-bypass
        assert _should_hide_pre_registo(UserRole.CONSULTOR, PRE_REGISTO_STATUS, None) is False


class TestStatusConstants:
    def test_constants_values(self):
        # Fix: Normalize process status filters to handle legacy singular
        # and plural values — INACTIVE_STATUSES/ARCHIVED_STATUSES têm de
        # incluir TODAS as variações documentadas, não apenas a forma
        # canónica (plural).
        assert INACTIVE_STATUSES == [
            "eliminado", "eliminados",
            "concluido", "concluidos",
            "desistencia", "desistencias", "desistido",
            "cancelado",
            "perdido",
            "arquivo",
        ]
        assert ARCHIVED_STATUSES == [
            "concluido", "concluidos",
            "desistencia", "desistencias", "desistido",
        ]
        assert DELETED_STATUS_VALUES == ["eliminado", "eliminados"]
        assert None in LEAD_STATUS_VALUES and PRE_REGISTO_STATUS in LEAD_STATUS_VALUES


class TestStatusValueAliases:
    def test_deleted_variations_are_symmetric(self):
        assert STATUS_VALUE_ALIASES["eliminado"] == STATUS_VALUE_ALIASES["eliminados"]

    def test_expand_status_values_returns_all_variations(self):
        assert expand_status_values("eliminados") == ["eliminado", "eliminados"]
        assert expand_status_values("concluido") == ["concluido", "concluidos"]
        assert set(expand_status_values("desistido")) == {
            "desistencia", "desistencias", "desistido",
        }

    def test_expand_status_values_falls_back_to_itself(self):
        # Estados sem variações legadas documentadas (fases activas do
        # Kanban) devolvem-se a si próprios — equivalente a uma igualdade.
        assert expand_status_values("escritura") == ["escritura"]

    def test_expand_status_values_handles_empty(self):
        assert expand_status_values(None) == []
        assert expand_status_values("") == []
