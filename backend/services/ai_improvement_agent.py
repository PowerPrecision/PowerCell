"""
=============================================================================
Agente de Melhoria com IA - Análise Preditiva e Prescritiva
=============================================================================
Analisa processos e gera sugestões automáticas para melhorar a eficiência.

Níveis de análise:
- Nível 1: Descritivo (estatísticas e métricas)
- Nível 2: Preditivo (previsão de atrasos e problemas)
- Nível 3: Prescritivo (sugestões de ações)
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from database import db

logger = logging.getLogger(__name__)

# Configuração da LLM
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')


class AIImprovementAgent:
    """Agente de IA para análise e melhoria de processos."""
    
    def __init__(self):
        self.llm_client = None
        self.api_key = EMERGENT_LLM_KEY
        if EMERGENT_LLM_KEY:
            logger.info("AI Agent inicializado com sucesso (usando emergentintegrations)")
        else:
            logger.warning("EMERGENT_LLM_KEY não configurada - AI Agent desativado")
    
    async def analyze_all_processes(self) -> Dict[str, Any]:
        """
        Análise completa de todos os processos activos.
        Retorna insights e sugestões.
        """
        try:
            # Obter todos os processos activos
            processes = await db.processes.find({
                "status": {"$nin": ["Finalizado", "Arquivado", "Cancelado"]}
            }).to_list(500)
            
            if not processes:
                return {"suggestions": [], "stats": {}, "alerts": []}
            
            # Análise estatística básica
            stats = await self._calculate_stats(processes)
            
            # Detectar problemas e gerar alertas
            alerts = await self._detect_problems(processes)
            
            # Gerar sugestões com IA (se disponível)
            suggestions = await self._generate_ai_suggestions(processes, stats, alerts)
            
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_analyzed": len(processes),
                "stats": stats,
                "alerts": alerts,
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"Erro na análise de processos: {e}")
            return {"error": str(e)}
    
    async def _calculate_stats(self, processes: List[Dict]) -> Dict:
        """Calcula estatísticas dos processos."""
        now = datetime.now(timezone.utc)
        
        # Processos por estado
        by_status = {}
        for p in processes:
            status = p.get("status", "Desconhecido")
            by_status[status] = by_status.get(status, 0) + 1
        
        # Processos por consultor
        by_consultant = {}
        for p in processes:
            consultant = p.get("assigned_consultant_name") or p.get("consultor_nome") or "Não atribuído"
            by_consultant[consultant] = by_consultant.get(consultant, 0) + 1
        
        # Calcular tempo médio em cada fase
        phase_times = []
        for p in processes:
            created_at = p.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    try:
                        created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    except ValueError:
                        continue
                else:
                    created_dt = created_at
                
                days_in_system = (now - created_dt).days
                phase_times.append(days_in_system)
        
        avg_days = sum(phase_times) / len(phase_times) if phase_times else 0
        
        # Processos parados (sem actividade há mais de 7 dias)
        stalled_count = 0
        for p in processes:
            last_update = p.get("updated_at") or p.get("created_at")
            if last_update:
                if isinstance(last_update, str):
                    try:
                        last_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                        if (now - last_dt).days > 7:
                            stalled_count += 1
                    except ValueError:
                        pass
        
        return {
            "total_active": len(processes),
            "by_status": by_status,
            "by_consultant": by_consultant,
            "avg_days_in_system": round(avg_days, 1),
            "stalled_processes": stalled_count,
            "stalled_percentage": round((stalled_count / len(processes)) * 100, 1) if processes else 0
        }
    
    async def _detect_problems(self, processes: List[Dict]) -> List[Dict]:
        """Detecta problemas e gera alertas."""
        alerts = []
        now = datetime.now(timezone.utc)
        
        for p in processes:
            process_id = p.get("id")
            client_name = p.get("client_name", "Cliente")
            
            # 1. Processo parado há muito tempo
            last_update = p.get("updated_at") or p.get("created_at")
            if last_update:
                if isinstance(last_update, str):
                    try:
                        last_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                        days_stalled = (now - last_dt).days
                        
                        if days_stalled > 15:
                            alerts.append({
                                "type": "stalled",
                                "severity": "high" if days_stalled > 30 else "medium",
                                "process_id": process_id,
                                "client_name": client_name,
                                "message": f"Processo parado há {days_stalled} dias",
                                "days_stalled": days_stalled,
                                "suggestion": "Contactar cliente ou banco para actualização"
                            })
                    except ValueError:
                        pass
            
            # 2. Documentos em falta ou a expirar
            # (Verificar se há documentos com validade a expirar)
            
            # 3. Processo sem consultor atribuído
            if not p.get("assigned_consultant_id") and not p.get("consultor_id"):
                alerts.append({
                    "type": "unassigned",
                    "severity": "medium",
                    "process_id": process_id,
                    "client_name": client_name,
                    "message": "Processo sem consultor atribuído",
                    "suggestion": "Atribuir um consultor responsável"
                })
            
            # 4. Valor de financiamento não definido
            if not p.get("valor_financiamento") and not p.get("financing_value"):
                status = p.get("status", "")
                if status not in ["Clientes em Espera", "Novo"]:
                    alerts.append({
                        "type": "missing_data",
                        "severity": "low",
                        "process_id": process_id,
                        "client_name": client_name,
                        "message": "Valor de financiamento não definido",
                        "suggestion": "Preencher valor de financiamento pretendido"
                    })
        
        # Ordenar por severidade
        severity_order = {"high": 0, "medium": 1, "low": 2}
        alerts.sort(key=lambda x: severity_order.get(x.get("severity"), 3))
        
        return alerts[:50]  # Limitar a 50 alertas
    
    async def _generate_ai_suggestions(
        self, 
        processes: List[Dict], 
        stats: Dict, 
        alerts: List[Dict]
    ) -> List[Dict]:
        """Gera sugestões usando IA."""
        
        suggestions = []
        
        # Sugestões baseadas em regras (sempre disponíveis)
        
        # 1. Se muitos processos parados
        if stats.get("stalled_percentage", 0) > 20:
            suggestions.append({
                "type": "operational",
                "priority": "high",
                "title": "Alta taxa de processos parados",
                "description": f"{stats['stalled_percentage']}% dos processos estão parados há mais de 7 dias.",
                "action": "Implementar follow-up automático ou reunião de revisão semanal",
                "impact": "Redução do tempo médio de processamento"
            })
        
        # 2. Se há consultores com muitos processos
        by_consultant = stats.get("by_consultant", {})
        for consultant, count in by_consultant.items():
            if count > 30 and consultant != "Não atribuído":
                suggestions.append({
                    "type": "capacity",
                    "priority": "medium",
                    "title": f"Consultor sobrecarregado: {consultant}",
                    "description": f"{consultant} tem {count} processos ativos.",
                    "action": "Redistribuir processos ou contratar mais consultores",
                    "impact": "Melhoria na qualidade do atendimento"
                })
        
        # 3. Se há muitos processos não atribuídos
        unassigned = by_consultant.get("Não atribuído", 0)
        if unassigned > 5:
            suggestions.append({
                "type": "assignment",
                "priority": "high",
                "title": f"{unassigned} processos sem consultor",
                "description": "Processos sem responsável podem ser esquecidos.",
                "action": "Atribuir consultores aos processos pendentes",
                "impact": "Evitar perda de clientes"
            })
        
        # 4. Sugestões com IA (se disponível)
        if self.llm_client and alerts:
            try:
                ai_suggestion = await self._get_ai_insight(stats, alerts[:10])
                if ai_suggestion:
                    suggestions.append(ai_suggestion)
            except Exception as e:
                logger.warning(f"Erro ao gerar sugestão IA: {e}")
        
        return suggestions
    
    async def _get_ai_insight(self, stats: Dict, alerts: List[Dict]) -> Optional[Dict]:
        """Usa LLM para gerar insights personalizados."""
        
        if not self.api_key:
            return None
        
        # Preparar contexto para a IA
        context = f"""
        Analisa os seguintes dados de um CRM de crédito habitação:
        
        Estatísticas:
        - Total de processos ativos: {stats.get('total_active', 0)}
        - Tempo médio no sistema: {stats.get('avg_days_in_system', 0)} dias
        - Processos parados: {stats.get('stalled_processes', 0)} ({stats.get('stalled_percentage', 0)}%)
        
        Principais alertas:
        {chr(10).join([f"- {a.get('client_name')}: {a.get('message')}" for a in alerts[:5]])}
        
        Gera UMA sugestão estratégica para melhorar a eficiência da equipa.
        Responde em português europeu, de forma concisa (máximo 3 frases).
        """
        
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            import uuid
            
            session_id = f"ai-insight-{uuid.uuid4().hex[:8]}"
            chat = LlmChat(
                api_key=self.api_key,
                session_id=session_id,
                system_message="És um consultor especializado em optimização de processos de crédito habitação. Dá sugestões práticas e accionáveis."
            ).with_model("openai", "gpt-4o-mini")
            
            user_message = UserMessage(text=context)
            response = await chat.send_message(user_message)
            
            if response:
                return {
                    "type": "ai_insight",
                    "priority": "medium",
                    "title": "Sugestão da IA",
                    "description": response.strip(),
                    "action": "Analisar e implementar conforme apropriado",
                    "impact": "Optimização baseada em padrões detectados",
                    "generated_by": "AI"
                }
        except Exception as e:
            logger.error(f"Erro na chamada à IA: {e}")
        
        return None
    
    async def analyze_single_process(self, process_id: str) -> Dict[str, Any]:
        """Análise detalhada de um processo específico."""
        
        process = await db.processes.find_one({"id": process_id})
        if not process:
            return {"error": "Processo não encontrado"}
        
        now = datetime.now(timezone.utc)
        
        # Calcular métricas do processo
        created_at = process.get("created_at")
        days_in_system = 0
        if created_at:
            if isinstance(created_at, str):
                try:
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    days_in_system = (now - created_dt).days
                except ValueError:
                    pass
        
        # Verificar última actividade
        last_update = process.get("updated_at") or created_at
        days_since_update = 0
        if last_update:
            if isinstance(last_update, str):
                try:
                    last_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    days_since_update = (now - last_dt).days
                except ValueError:
                    pass
        
        # Gerar recomendações específicas
        recommendations = []
        
        if days_since_update > 15:
            recommendations.append({
                "type": "urgent",
                "message": f"Processo sem actualização há {days_since_update} dias",
                "action": "Contactar cliente para actualização de estado"
            })
        
        if not process.get("assigned_consultant_id"):
            recommendations.append({
                "type": "assignment",
                "message": "Processo sem consultor atribuído",
                "action": "Atribuir um consultor responsável"
            })
        
        # Previsão de conclusão (simplificada)
        avg_completion_days = 60  # Média histórica assumida
        estimated_completion = None
        if created_at and days_in_system < avg_completion_days:
            remaining_days = avg_completion_days - days_in_system
            estimated_completion = (now + timedelta(days=remaining_days)).strftime("%Y-%m-%d")
        
        return {
            "process_id": process_id,
            "client_name": process.get("client_name", "N/A"),
            "status": process.get("status", "N/A"),
            "metrics": {
                "days_in_system": days_in_system,
                "days_since_update": days_since_update,
                "estimated_completion": estimated_completion
            },
            "risk_level": "high" if days_since_update > 30 else "medium" if days_since_update > 15 else "low",
            "recommendations": recommendations,
            "analyzed_at": now.isoformat()
        }


# Instância global
ai_agent = AIImprovementAgent()


# Funções de conveniência
async def run_weekly_analysis() -> Dict[str, Any]:
    """Executa análise semanal completa."""
    return await ai_agent.analyze_all_processes()


async def analyze_process(process_id: str) -> Dict[str, Any]:
    """Analisa um processo específico."""
    return await ai_agent.analyze_single_process(process_id)
