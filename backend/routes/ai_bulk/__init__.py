"""
AI Bulk Import Module
=====================
Módulo para importação em massa de documentos com análise de IA.

Este módulo foi refatorado de um ficheiro único grande
para melhor organização e manutenção (SonarQube).

Estrutura modular:
- background_jobs.py: Gestão de jobs em background (endpoints)
- nif_cache.py: Endpoints de cache NIF
- document_utils.py: Utilitários de documentos (endpoints)
- import_errors.py: Gestão de erros de importação (endpoints)
- constants.py: Constantes partilhadas
- cache.py: Funções de cache NIF e duplicados
- jobs.py: Gestão de background jobs
- matching.py: Matching de clientes por nome/NIF
- utils.py: Funções utilitárias

NOTA: O router principal continua em ai_bulk.py (um nível acima).
Este __init__.py fornece uma forma limpa de importar o router.
"""

# Importar do ficheiro original ai_bulk.py (que está um nível acima)
# O ficheiro ai_bulk.py contém todas as rotas implementadas
import os

# Obter o caminho do ficheiro ai_bulk.py original
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
_ai_bulk_file = os.path.join(_parent_dir, "ai_bulk.py")

# Importar usando importlib para evitar conflito de nomes
import importlib.util
_spec = importlib.util.spec_from_file_location("_ai_bulk_original", _ai_bulk_file)
_ai_bulk_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ai_bulk_module)

# Exportar o router do módulo original
router = _ai_bulk_module.router

# Exportar também outras funções úteis
normalize_text_for_matching = getattr(_ai_bulk_module, 'normalize_text_for_matching', None)
