"""
====================================================================
SERVIÇO DE ANÁLISE SEMANAL DE ERROS (COM IA)
====================================================================
Este serviço analisa os erros de importação semanalmente e envia
sugestões de resolução ao admin via notificação e email.

Funcionalidades:
- Agregação de erros por tipo e padrão
- Análise IA com Claude 3.5 Sonnet para sugestões inteligentes
- Geração de relatório semanal automático
- Envio de notificações ao admin
====================================================================
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import uuid

from database import db

logger = logging.getLogger(__name__)


async def analyze_weekly_errors() -> Dict[str, Any]:
    """
    Analisa os erros da última semana e gera um relatório com sugestões.
    Usa Claude 3.5 Sonnet para análise inteligente.
    
    Returns:
        Dict com análise e sugestões
    """
    # Calcular período da última semana
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    
    # Buscar erros da última semana
    query = {
        "timestamp": {"$gte": week_ago.isoformat()}
    }
    
    errors = await db.import_errors.find(query, {"_id": 0}).to_list(1000)
    # Usar system_error_logs (colecção actual) em vez de error_logs (deprecated)
    system_logs = await db.system_error_logs.find(query, {"_id": 0}).to_list(1000)
    
    # Combinar erros de ambas as colecções
    all_errors = errors + system_logs
    
    if not all_errors:
        return {
            "period": {
                "start": week_ago.isoformat(),
                "end": now.isoformat()
            },
            "total_errors": 0,
            "summary": "Sem erros na última semana. Excelente!",
            "suggestions": [],
            "action_items": [],
            "ai_analysis": None
        }
    
    # Agrupar por tipo de erro
    error_types = {}
    error_patterns = {}
    
    for error in all_errors:
        # Por fonte
        source = error.get("source") or error.get("document_type") or "unknown"
        if source not in error_types:
            error_types[source] = {"count": 0, "examples": []}
        error_types[source]["count"] += 1
        if len(error_types[source]["examples"]) < 3:
            error_types[source]["examples"].append(
                error.get("error_message") or error.get("error") or str(error)[:100]
            )
        
        # Por padrão de mensagem
        msg = (error.get("error_message") or error.get("error") or "")[:50].lower()
        if msg:
            if msg not in error_patterns:
                error_patterns[msg] = 0
            error_patterns[msg] += 1
    
    # Análise IA com Claude
    ai_analysis = None
    try:
        from services.ai_page_analyzer import page_analyzer
        ai_analysis = await page_analyzer.analyze_errors(all_errors, error_patterns)
        logger.info("Análise IA concluída com sucesso")
    except Exception as e:
        logger.warning(f"Análise IA falhou (usando fallback): {e}")
        ai_analysis = {"error": str(e), "fallback": True}
    
    # Gerar sugestões (fallback se IA falhar)
    suggestions = []
    action_items = []
    
    if ai_analysis and not ai_analysis.get("error"):
        # Usar sugestões da IA
        suggestions = ai_analysis.get("suggestions", [])
        action_items = ai_analysis.get("priority_actions", [])
    else:
        # Fallback para análise manual
        for pattern, count in sorted(error_patterns.items(), key=lambda x: -x[1])[:10]:
            if count >= 3:
                suggestion = generate_suggestion_for_pattern(pattern, count)
                if suggestion:
                    suggestions.append(suggestion)
        
        for source, data in sorted(error_types.items(), key=lambda x: -x[1]["count"])[:5]:
            if data["count"] >= 5:
                action = generate_action_for_source(source, data["count"], data["examples"])
                if action:
                    action_items.append(action)
    
    report = {
        "period": {
            "start": week_ago.isoformat(),
            "end": now.isoformat()
        },
        "total_errors": len(all_errors),
        "errors_by_type": error_types,
        "top_patterns": dict(sorted(error_patterns.items(), key=lambda x: -x[1])[:5]),
        "summary": ai_analysis.get("summary") if ai_analysis and not ai_analysis.get("error") else generate_summary(len(all_errors), error_types),
        "root_causes": ai_analysis.get("root_causes", []) if ai_analysis else [],
        "suggestions": suggestions,
        "action_items": action_items,
        "ai_analysis": ai_analysis,
        "ai_model": "gpt-4o" if ai_analysis and not ai_analysis.get("error") else "fallback",
        "generated_at": now.isoformat()
    }
    
    return report


def generate_suggestion_for_pattern(pattern: str, count: int) -> Dict[str, Any]:
    """Gera sugestão baseada num padrão de erro."""
    
    suggestions_map = {
        "falta": {
            "priority": "high",
            "title": "Campos Obrigatórios em Falta",
            "description": f"Detectados {count} erros de campos obrigatórios em falta.",
            "recommendation": "Crie um template Excel com colunas obrigatórias destacadas. Valide dados antes de importar."
        },
        "formato": {
            "priority": "medium",
            "title": "Problemas de Formato",
            "description": f"Detectados {count} erros de formato de dados.",
            "recommendation": "Verifique se os números não têm caracteres especiais e datas estão no formato correcto."
        },
        "duplicad": {
            "priority": "medium",
            "title": "Registos Duplicados",
            "description": f"Detectados {count} registos duplicados.",
            "recommendation": "Verifique NIFs e emails antes de importar para evitar duplicações."
        },
        "nif": {
            "priority": "high",
            "title": "NIFs Inválidos",
            "description": f"Detectados {count} erros de NIF.",
            "recommendation": "NIFs devem ter 9 dígitos. NIFs começados por 5 são de empresas e podem não ser aceites para clientes particulares."
        },
        "email": {
            "priority": "low",
            "title": "Emails Inválidos",
            "description": f"Detectados {count} erros de formato de email.",
            "recommendation": "Verifique que os emails têm formato válido (ex: nome@dominio.pt)."
        },
        "ficheiro": {
            "priority": "medium",
            "title": "Problemas com Ficheiros",
            "description": f"Detectados {count} erros relacionados com ficheiros.",
            "recommendation": "Verifique o tamanho máximo (10MB) e formatos suportados (PDF, imagens, Excel)."
        },
        "timeout": {
            "priority": "low",
            "title": "Timeouts de Processamento",
            "description": f"Detectados {count} timeouts.",
            "recommendation": "Divida ficheiros grandes em lotes menores para processamento mais rápido."
        },
        "10mb": {
            "priority": "medium",
            "title": "Ficheiros Muito Grandes",
            "description": f"Detectados {count} ficheiros que excedem 10MB.",
            "recommendation": "Comprima ficheiros ou divida em partes antes de importar."
        }
    }
    
    for keyword, suggestion in suggestions_map.items():
        if keyword in pattern:
            return suggestion
    
    # Sugestão genérica
    if count >= 5:
        return {
            "priority": "info",
            "title": "Padrão de Erro Recorrente",
            "description": f"Detectados {count} erros com padrão semelhante.",
            "recommendation": "Analise manualmente os ficheiros afectados para identificar a causa raiz."
        }
    
    return None


def generate_action_for_source(source: str, count: int, examples: List[str]) -> Dict[str, Any]:
    """Gera item de acção baseado na fonte de erro."""
    
    source_actions = {
        "excel_import": {
            "action": "Rever template de importação Excel",
            "steps": [
                "Verificar se todas as colunas obrigatórias estão presentes",
                "Validar formato dos dados antes de importar",
                "Criar validação automática no Excel"
            ]
        },
        "document_analysis": {
            "action": "Melhorar qualidade dos documentos",
            "steps": [
                "Usar digitalizações de alta resolução",
                "Preferir PDFs a imagens",
                "Verificar orientação dos documentos"
            ]
        },
        "scraper": {
            "action": "Verificar sites bloqueados",
            "steps": [
                "Alguns sites podem estar a bloquear o scraper",
                "Tentar URLs alternativas",
                "Contactar suporte se problema persistir"
            ]
        }
    }
    
    for key, action in source_actions.items():
        if key in source.lower():
            return {
                "source": source,
                "count": count,
                **action,
                "examples": examples[:2]
            }
    
    return {
        "source": source,
        "count": count,
        "action": f"Investigar erros de {source}",
        "steps": ["Rever logs detalhados", "Identificar padrão comum", "Implementar validação preventiva"],
        "examples": examples[:2]
    }


def generate_summary(total: int, error_types: Dict) -> str:
    """Gera sumário textual do relatório."""
    
    if total == 0:
        return "Excelente! Sem erros na última semana."
    
    if total < 5:
        return f"Apenas {total} erros na última semana. Sistema a funcionar bem."
    
    if total < 20:
        main_source = max(error_types.items(), key=lambda x: x[1]["count"])[0]
        return f"{total} erros detectados, principalmente em {main_source}. Reveja as sugestões abaixo."
    
    return f"Atenção: {total} erros na última semana. Reveja as sugestões e implemente as correcções recomendadas."


async def send_weekly_report_to_admin():
    """
    Envia o relatório semanal de erros para o admin.
    Cria notificação no sistema e opcionalmente envia email.
    """
    try:
        # Gerar relatório
        report = await analyze_weekly_errors()
        
        if report["total_errors"] == 0:
            logger.info("Sem erros na última semana - relatório não enviado")
            return {"sent": False, "reason": "no_errors"}
        
        # Criar notificação no sistema
        notification = {
            "id": str(uuid.uuid4()),
            "type": "weekly_error_report",
            "title": f"Relatório Semanal: {report['total_errors']} erros detectados",
            "message": report["summary"],
            "data": {
                "period": report["period"],
                "total_errors": report["total_errors"],
                "suggestions_count": len(report["suggestions"]),
                "top_patterns": list(report.get("top_patterns", {}).keys())[:3]
            },
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.notifications.insert_one(notification)
        
        # Guardar relatório completo para consulta
        report["id"] = str(uuid.uuid4())
        report["type"] = "weekly_error_analysis"
        await db.error_reports.insert_one(report)
        
        logger.info(f"Relatório semanal enviado: {report['total_errors']} erros, {len(report['suggestions'])} sugestões")
        
        return {
            "sent": True,
            "report_id": report["id"],
            "total_errors": report["total_errors"],
            "suggestions_count": len(report["suggestions"])
        }
        
    except Exception as e:
        logger.error(f"Erro ao enviar relatório semanal: {e}")
        return {"sent": False, "error": str(e)}


async def get_latest_weekly_report() -> Dict[str, Any]:
    """
    Obtém o último relatório semanal gerado.
    """
    report = await db.error_reports.find_one(
        {"type": "weekly_error_analysis"},
        {"_id": 0},
        sort=[("generated_at", -1)]
    )
    
    if not report:
        # Gerar um novo se não existir
        return await analyze_weekly_errors()
    
    return report
