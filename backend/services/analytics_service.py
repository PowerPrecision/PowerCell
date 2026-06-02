"""
====================================================================
SERVIÇO DE ANALYTICS - RELATÓRIO SEMANAL DO CEO
====================================================================
Agregação de dados de produtividade por utilizador para o relatório
semanal enviado ao CEO todas as Segundas-feiras às 06:00.

Métricas por utilizador:
- Processos Movidos/Avançados
- Tarefas Concluídas
- Tarefas Atrasadas/Pendentes
====================================================================
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


async def generate_weekly_team_report(db) -> Dict[str, Any]:
    """
    Gerar relatório semanal de produtividade da equipa.

    Agrega dados das colecções `history`, `task_logs` e `processes`
    dos últimos 7 dias, agrupados por utilizador.

    Args:
        db: Instância Motor da base de dados MongoDB (async)

    Returns:
        Dict com:
        - period_start: data de início do período (ISO string)
        - period_end: data de fim do período (ISO string)
        - users: lista de dicts com métricas por utilizador
        - summary: métricas globais da equipa
    """
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=7)
    period_start_iso = period_start.isoformat()
    period_end_iso = now.isoformat()

    logger.info(
        f"[Analytics] A gerar relatório semanal: "
        f"{period_start.strftime('%d/%m/%Y')} - {now.strftime('%d/%m/%Y')}"
    )

    # ----------------------------------------------------------------
    # 1. BUSCAR UTILIZADORES ACTIVOS (staff only — sem clientes/parceiros)
    # ----------------------------------------------------------------
    from services.role_query import deep_role_in_filter

    staff_filter = deep_role_in_filter(
        ["consultor", "intermediario", "administrativo", "indexacao", "diretor", "ceo", "admin"]
    )

    users_cursor = db.users.find(
        {"$and": [staff_filter, {"is_active": {"$ne": False}}]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    )
    users_list = await users_cursor.to_list(200)

    # Mapear user_id -> {name, email, role}
    user_map: Dict[str, Dict[str, str]] = {}
    for u in users_list:
        user_map[u["id"]] = {
            "name": u.get("name", "Desconhecido"),
            "email": u.get("email", ""),
            "role": u.get("role", ""),
        }

    # ----------------------------------------------------------------
    # 2. PROCESSOS MOVIDOS / AVANÇADOS (histórico de status_change)
    # ----------------------------------------------------------------
    # Query à colecção `history` — entradas onde action contém
    # "status_change" ou "status_update" nos últimos 7 dias.
    # Agrupar por user_id para contar quantos processos cada
    # utilizador avançou.
    moved_pipeline = [
        {
            "$match": {
                "action": {"$regex": "status_change|status_update|moveu|avançou", "$options": "i"},
                "created_at": {"$gte": period_start_iso}
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "processes_moved": {"$sum": 1},
                "unique_processes": {"$addToSet": "$process_id"}
            }
        }
    ]

    moved_results = await db.history.aggregate(moved_pipeline).to_list(200)

    # Contar processos únicos movidos por user
    user_moved_counts: Dict[str, Dict[str, Any]] = {}
    for entry in moved_results:
        uid = entry["_id"]
        if uid:
            user_moved_counts[uid] = {
                "processes_moved": len(entry.get("unique_processes", [])),
                "total_actions": entry.get("processes_moved", 0),
            }

    # ----------------------------------------------------------------
    # 3. TAREFAS CONCLUÍDAS (task_logs com status=completed)
    # ----------------------------------------------------------------
    completed_pipeline = [
        {
            "$match": {
                "status": "completed",
                "completed_at": {"$gte": period_start_iso}
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "tasks_completed": {"$sum": 1}
            }
        }
    ]

    completed_results = await db.task_logs.aggregate(completed_pipeline).to_list(200)

    user_completed_counts: Dict[str, int] = {}
    for entry in completed_results:
        uid = entry["_id"]
        if uid:
            user_completed_counts[uid] = entry.get("tasks_completed", 0)

    # ----------------------------------------------------------------
    # 4. TAREFAS ATRASADAS / PENDENTES
    # ----------------------------------------------------------------
    # Atrasadas: task_logs com status=failed ou PENDING com created_at
    #   anterior a 7 dias atrás (ainda não concluídas).
    # Pendentes: task_logs com status em (pending, processing) criadas
    #   no período que ainda não foram concluídas.

    overdue_pipeline = [
        {
            "$match": {
                "status": {"$in": ["pending", "processing", "failed"]},
                "created_at": {"$lt": period_start_iso}
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "tasks_overdue": {"$sum": 1}
            }
        }
    ]

    overdue_results = await db.task_logs.aggregate(overdue_pipeline).to_list(200)

    user_overdue_counts: Dict[str, int] = {}
    for entry in overdue_results:
        uid = entry["_id"]
        if uid:
            user_overdue_counts[uid] = entry.get("tasks_overdue", 0)

    # Pendentes criadas no período (ainda não concluídas)
    pending_pipeline = [
        {
            "$match": {
                "status": {"$in": ["pending", "processing"]},
                "created_at": {"$gte": period_start_iso}
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "tasks_pending": {"$sum": 1}
            }
        }
    ]

    pending_results = await db.task_logs.aggregate(pending_pipeline).to_list(200)

    user_pending_counts: Dict[str, int] = {}
    for entry in pending_results:
        uid = entry["_id"]
        if uid:
            user_pending_counts[uid] = entry.get("tasks_pending", 0)

    # ----------------------------------------------------------------
    # 5. MONTAR RESULTADO POR UTILIZADOR
    # ----------------------------------------------------------------
    user_reports: List[Dict[str, Any]] = []

    for uid, info in user_map.items():
        moved = user_moved_counts.get(uid, {})
        report = {
            "user_id": uid,
            "name": info["name"],
            "email": info["email"],
            "role": info["role"],
            "processes_moved": moved.get("processes_moved", 0),
            "tasks_completed": user_completed_counts.get(uid, 0),
            "tasks_overdue": user_overdue_counts.get(uid, 0),
            "tasks_pending": user_pending_counts.get(uid, 0),
        }
        user_reports.append(report)

    # Ordenar por processos movidos (desc), depois tarefas concluídas (desc)
    user_reports.sort(
        key=lambda x: (x["processes_moved"], x["tasks_completed"]),
        reverse=True
    )

    # ----------------------------------------------------------------
    # 6. RESUMO GLOBAL
    # ----------------------------------------------------------------
    total_processes_moved = sum(u["processes_moved"] for u in user_reports)
    total_tasks_completed = sum(u["tasks_completed"] for u in user_reports)
    total_tasks_overdue = sum(u["tasks_overdue"] for u in user_reports)
    total_tasks_pending = sum(u["tasks_pending"] for u in user_reports)

    summary = {
        "total_users": len(user_reports),
        "total_processes_moved": total_processes_moved,
        "total_tasks_completed": total_tasks_completed,
        "total_tasks_overdue": total_tasks_overdue,
        "total_tasks_pending": total_tasks_pending,
    }

    result = {
        "period_start": period_start_iso,
        "period_end": period_end_iso,
        "users": user_reports,
        "summary": summary,
    }

    logger.info(
        f"[Analytics] Relatório gerado: {len(user_reports)} utilizadores, "
        f"{total_processes_moved} processos movidos, "
        f"{total_tasks_completed} tarefas concluídas, "
        f"{total_tasks_overdue} atrasadas, "
        f"{total_tasks_pending} pendentes"
    )

    return result


def format_report_html(report: Dict[str, Any]) -> str:
    """
    Format weekly team report data into a clean, professional HTML email
    for the CEO.

    Args:
        report: Dict retornado por generate_weekly_team_report()

    Returns:
        HTML string pronto para ser enviado como body_html no send_email
    """
    period_start = datetime.fromisoformat(report["period_start"])
    period_end = datetime.fromisoformat(report["period_end"])
    period_label = (
        f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}"
    )
    summary = report["summary"]

    # Linhas da tabela de utilizadores
    user_rows = ""
    for idx, user in enumerate(report["users"], 1):
        # Indicador visual de performance
        score = user["processes_moved"] + user["tasks_completed"]
        if score >= 10:
            badge = '<span style="background:#16a34a;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">Top</span>'
        elif score >= 5:
            badge = '<span style="background:#2563eb;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">Bom</span>'
        else:
            badge = ""

        overdue_color = "#dc2626" if user["tasks_overdue"] > 0 else "#334155"
        pending_color = "#f59e0b" if user["tasks_pending"] > 0 else "#334155"

        role_label = {
            "consultor": "Consultor",
            "intermediario": "Intermediário",
            "administrativo": "Administrativo",
            "indexacao": "Indexação",
            "diretor": "Diretor",
            "ceo": "CEO",
            "admin": "Admin",
        }.get(user["role"], user["role"])

        user_rows += f"""
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px 12px;font-size:13px;color:#334155;">{idx}</td>
                <td style="padding:10px 12px;font-size:13px;color:#334155;font-weight:600;">{user['name']} {badge}</td>
                <td style="padding:10px 12px;font-size:13px;color:#64748b;">{role_label}</td>
                <td style="padding:10px 12px;font-size:13px;color:#0f766e;font-weight:700;text-align:center;">{user['processes_moved']}</td>
                <td style="padding:10px 12px;font-size:13px;color:#16a34a;font-weight:700;text-align:center;">{user['tasks_completed']}</td>
                <td style="padding:10px 12px;font-size:13px;color:{overdue_color};font-weight:600;text-align:center;">{user['tasks_overdue']}</td>
                <td style="padding:10px 12px;font-size:13px;color:{pending_color};font-weight:600;text-align:center;">{user['tasks_pending']}</td>
            </tr>"""

    # Top performers
    top_performers = sorted(
        report["users"],
        key=lambda x: x["processes_moved"] + x["tasks_completed"],
        reverse=True
    )[:3]
    top_performers_html = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, tp in enumerate(top_performers):
        score = tp["processes_moved"] + tp["tasks_completed"]
        if score > 0:
            top_performers_html += f"""
                <div style="display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #f1f5f9;">
                    <span style="font-size:20px;margin-right:10px;">{medals[i]}</span>
                    <span style="font-size:14px;font-weight:600;color:#334155;">{tp['name']}</span>
                    <span style="margin-left:auto;font-size:13px;color:#0f766e;font-weight:700;">{score} acções</span>
                </div>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
            .container {{ max-width: 700px; margin: 0 auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #0f766e 100%); color: white; padding: 30px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 22px; letter-spacing: 0.5px; }}
            .header p {{ margin: 8px 0 0 0; opacity: 0.9; font-size: 13px; }}
            .content {{ padding: 25px 30px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 25px; }}
            .stat-card {{ background: #f8fafc; border-radius: 8px; padding: 14px 10px; text-align: center; border-left: 3px solid; }}
            .stat-card.moved {{ border-left-color: #0f766e; }}
            .stat-card.completed {{ border-left-color: #16a34a; }}
            .stat-card.overdue {{ border-left-color: #dc2626; }}
            .stat-card.pending {{ border-left-color: #f59e0b; }}
            .stat-value {{ font-size: 28px; font-weight: bold; }}
            .stat-value.moved {{ color: #0f766e; }}
            .stat-value.completed {{ color: #16a34a; }}
            .stat-value.overdue {{ color: #dc2626; }}
            .stat-value.pending {{ color: #f59e0b; }}
            .stat-label {{ font-size: 11px; color: #64748b; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
            .section {{ margin-top: 25px; }}
            .section h3 {{ font-size: 14px; color: #334155; margin-bottom: 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #f8fafc; padding: 10px 12px; font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; border-bottom: 2px solid #e2e8f0; }}
            th.center {{ text-align: center; }}
            .footer {{ text-align: center; padding: 20px; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
            .top-performers {{ background: #f0fdf4; border-radius: 8px; padding: 15px; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Relatório Semanal de Produtividade</h1>
                <p>PowerCell CRM - {period_label}</p>
            </div>
            <div class="content">
                <!-- Resumo Global -->
                <div class="stats-grid">
                    <div class="stat-card moved">
                        <div class="stat-value moved">{summary['total_processes_moved']}</div>
                        <div class="stat-label">Processos Movidos</div>
                    </div>
                    <div class="stat-card completed">
                        <div class="stat-value completed">{summary['total_tasks_completed']}</div>
                        <div class="stat-label">Tarefas Concluídas</div>
                    </div>
                    <div class="stat-card overdue">
                        <div class="stat-value overdue">{summary['total_tasks_overdue']}</div>
                        <div class="stat-label">Tarefas Atrasadas</div>
                    </div>
                    <div class="stat-card pending">
                        <div class="stat-value pending">{summary['total_tasks_pending']}</div>
                        <div class="stat-label">Tarefas Pendentes</div>
                    </div>
                </div>

                <!-- Top Performers -->
                {f'''<div class="top-performers">
                    <h3 style="font-size:14px;color:#166534;margin:0 0 10px 0;">Top Performers da Semana</h3>
                    {top_performers_html}
                </div>''' if top_performers_html else ''}

                <!-- Tabela por Utilizador -->
                <div class="section">
                    <h3>Produtividade por Utilizador</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Utilizador</th>
                                <th>Cargo</th>
                                <th class="center">Movidos</th>
                                <th class="center">Concluídas</th>
                                <th class="center">Atrasadas</th>
                                <th class="center">Pendentes</th>
                            </tr>
                        </thead>
                        <tbody>
                            {user_rows if user_rows else '<tr><td colspan="7" style="padding:20px;text-align:center;color:#94a3b8;">Sem dados no período</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="footer">
                <p>Este relatório foi gerado automaticamente pelo PowerCell CRM</p>
                <p>Power Real Estate & Precision Crédito</p>
            </div>
        </div>
    </body>
    </html>"""

    return html
