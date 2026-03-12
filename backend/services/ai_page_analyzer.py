"""
====================================================================
SERVIÇO DE IA PARA ANÁLISE (Configurável)
====================================================================
Este serviço gere as configurações de IA do sistema e permite
ao admin escolher qual modelo usar para cada tarefa.

Modelos suportados:
- gemini-1.5-flash: Rápido e económico (scraping)
- gpt-4o-mini: Bom custo-benefício (documentos)
- gpt-4o: Mais capaz (análise complexa)
====================================================================
"""
import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Importar configurações
from config import GEMINI_API_KEY, EMERGENT_LLM_KEY, AI_CONFIG_DEFAULTS, AI_MODELS


async def get_ai_config() -> Dict[str, Any]:
    """
    Obtém a configuração actual de IA para cada tarefa.
    
    Retorna sempre TODAS as tarefas, mesclando DB com defaults.
    """
    from database import db
    
    # Começar com os defaults
    result = dict(AI_CONFIG_DEFAULTS)
    
    # Obter tarefas da DB (se existirem) e adicionar defaults
    db_tasks = await db.ai_tasks.find({}, {"_id": 0}).to_list(100)
    if db_tasks:
        for task in db_tasks:
            if task["key"] not in result:
                result[task["key"]] = task.get("default_model", "gpt-4o-mini")
    
    # Obter configuração personalizada da DB
    config = await db.system_config.find_one(
        {"key": "ai_config"},
        {"_id": 0}
    )
    
    # Mesclar configuração guardada (tem prioridade)
    if config and config.get("value"):
        for key, value in config["value"].items():
            result[key] = value
    
    return result


async def save_ai_config(config: Dict[str, str], user_email: str) -> bool:
    """
    Guarda a configuração de IA na DB.
    Apenas admins podem fazer isto.
    """
    from database import db
    from datetime import datetime, timezone
    
    await db.system_config.update_one(
        {"key": "ai_config"},
        {
            "$set": {
                "key": "ai_config",
                "value": config,
                "updated_by": user_email,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    logger.info(f"Configuração de IA actualizada por {user_email}")
    return True


async def analyze_with_configured_ai(
    content: str,
    task_type: str = "scraper_extraction",
    context: str = ""
) -> Dict[str, Any]:
    """
    Analisa conteúdo usando o modelo configurado para a tarefa.
    
    Args:
        content: Conteúdo a analisar
        task_type: Tipo de tarefa (scraper_extraction, document_analysis, etc.)
        context: Contexto adicional (URL, nome do documento, etc.)
    
    Returns:
        Dict com resultado da análise
    """
    config = await get_ai_config()
    model_key = config.get(task_type, "gemini-1.5-flash")
    
    model_info = AI_MODELS.get(model_key, AI_MODELS["gemini-1.5-flash"])
    provider = model_info["provider"]
    
    logger.info(f"Usando {model_key} ({provider}) para {task_type}")
    
    if provider == "gemini":
        return await _call_gemini(content, task_type, context, model_key)
    elif provider == "openai":
        return await _call_openai(content, task_type, context, model_key)
    else:
        return {"error": f"Provider desconhecido: {provider}"}


async def _call_gemini(content: str, task_type: str, context: str, model: str) -> Dict[str, Any]:
    """Chama Gemini via google.generativeai."""
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY não configurada"}
    
    try:
        import google.generativeai as genai
        import json
        
        genai.configure(api_key=GEMINI_API_KEY)
        
        prompt = _get_prompt_for_task(task_type, content, context)
        
        # Mapear nome do modelo
        gemini_model = "gemini-2.0-flash"  # Default
        if "2.0" in model:
            gemini_model = model.replace("gemini-", "gemini-")
        
        model_instance = genai.GenerativeModel(gemini_model)
        response = model_instance.generate_content(prompt)
        
        result_text = response.text.strip()
        
        # Limpar markdown
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        
        try:
            data = json.loads(result_text.strip())
            return {"success": True, "data": data, "model": model}
        except json.JSONDecodeError:
            return {"success": True, "data": {"raw": result_text}, "model": model}
            
    except Exception as e:
        logger.error(f"Erro Gemini: {e}")
        return {"error": str(e)}


async def _call_openai(content: str, task_type: str, context: str, model: str) -> Dict[str, Any]:
    """Chama OpenAI via emergentintegrations."""
    if not EMERGENT_LLM_KEY:
        return {"error": "EMERGENT_LLM_KEY não configurada"}
    
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import json
        
        prompt = _get_prompt_for_task(task_type, content, context)
        
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"{task_type}-analysis",
            system_message="Responde sempre em formato JSON estruturado. Usa português de Portugal."
        ).with_model("openai", model)
        
        response = await chat.send_message(UserMessage(text=prompt))
        
        # Limpar markdown
        result_text = response.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        
        try:
            data = json.loads(result_text.strip())
            return {"success": True, "data": data, "model": model}
        except json.JSONDecodeError:
            return {"success": True, "data": {"raw": result_text}, "model": model}
            
    except Exception as e:
        logger.error(f"Erro OpenAI: {e}")
        return {"error": str(e)}


def _get_prompt_for_task(task_type: str, content: str, context: str) -> str:
    """Gera prompt adequado ao tipo de tarefa."""
    
    if task_type == "scraper_extraction":
        return f"""Analisa este conteúdo de uma página imobiliária portuguesa e extrai os dados em JSON.
        
URL/Contexto: {context}

Extrai: titulo, preco (número), localizacao, tipologia, area (m²), quartos, casas_banho, descricao, certificacao_energetica

Responde APENAS com JSON. Usa null para campos não encontrados.

Conteúdo:
{content[:15000]}"""
    
    elif task_type == "document_analysis":
        return f"""Analisa este documento e extrai informações relevantes em JSON.
        
Documento: {context}

Identifica: tipo_documento, dados_pessoais, datas_importantes, valores_monetarios, observacoes

Responde em JSON.

Conteúdo:
{content[:10000]}"""
    
    elif task_type == "error_analysis":
        return f"""Analisa estes erros de sistema e gera sugestões em JSON.
        
Gera: summary, root_causes (lista), suggestions (lista ordenada por impacto), priority_actions (lista)

Responde em português de Portugal.

Erros:
{content[:8000]}"""
    
    else:
        return f"""Analisa o seguinte conteúdo e responde em JSON estruturado.
        
Contexto: {context}

{content[:10000]}"""


# Classe wrapper para compatibilidade
class PageAnalyzer:
    """Wrapper para análise de páginas."""
    
    async def analyze(self, html: str, url: str, type: str = "property") -> Dict:
        return await analyze_with_configured_ai(html, "scraper_extraction", url)
    
    async def analyze_errors(self, errors: list, patterns: dict) -> Dict:
        import json
        content = json.dumps({"errors": errors[:50], "patterns": patterns}, indent=2)
        return await analyze_with_configured_ai(content, "error_analysis", "weekly_report")


page_analyzer = PageAnalyzer()
