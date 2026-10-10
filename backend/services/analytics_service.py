"""
====================================================================
SERVIÇO DE ANALYTICS - RELATÓRIO SEMANAL DO CEO
====================================================================
Fachada do relatório semanal enviado ao CEO às Segundas-feiras e do
formatador do email. A agregação vive em `services/executive_report.py`
(Bloco 4): UM motor para o email, o Dashboard Executivo, o Relatório
Semanal e o PDF.

Métricas por utilizador:
- Processos Movidos/Avançados
- Tarefas Concluídas
- Tarefas Atrasadas/Pendentes
====================================================================
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


async def generate_weekly_team_report(
    db,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    user: Optional[Dict[str, Any]] = None,
    user_ids: Optional[List[str]] = None,
    papeis: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Relatório de produtividade da equipa — fachada do motor executivo.

    Bloco 4 (pontos 13 e 16): a agregação mudou para
    `services/executive_report.py`, que serve também o Dashboard Executivo,
    o Relatório Semanal e o PDF. Esta assinatura mantém-se para o email de
    segunda-feira e para o painel antigo; duas implementações da mesma
    política divergem (ver a docstring do motor para os defeitos corrigidos).

    Args:
        db: Base de dados Motor (a do chamador; os testes passam uma falsa).
        period_start / period_end: instantes UTC; contam os DIAS que tocam
            (o fim é inclusivo). Omissão: os 7 dias que terminam hoje.
        user: Quem pede. Restringe o relatório à REDE de quem pede. `None`
            é o consolidado do email automático (D-7) e é avisado no log.
        user_ids / papeis: filtros que só estreitam o âmbito.
    """
    from services import executive_report as er

    fim = period_end.astimezone(timezone.utc).date() if period_end else None
    inicio = period_start.astimezone(timezone.utc).date() if period_start else None
    periodo = er.construir_periodo(
        inicio.isoformat() if inicio else None,
        fim.isoformat() if fim else None,
    )
    ambito = await er.resolver_ambito(user)
    return await er.gerar_relatorio(
        ambito,
        er.Filtros(
            periodo=periodo,
            user_ids=er.normalizar_lista(user_ids),
            papeis=er.normalizar_lista(papeis),
        ),
        base=db,
    )


def format_report_html(report: Dict[str, Any]) -> str:
    """
    Format weekly team report data into a clean, professional HTML email
    for the CEO.

    Args:
        report: Dict retornado por generate_weekly_team_report()

    Returns:
        HTML string pronto para ser enviado como body_html no send_email
    """
    import html as _html

    def _n(valor) -> int:
        """`None` (histórico desligado) conta como 0 nas somas."""
        return int(valor or 0)

    def _mostra(valor) -> str:
        return "—" if valor is None else str(valor)

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
        score = _n(user["processes_moved"]) + _n(user["tasks_completed"])
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
                <td style="padding:10px 12px;font-size:13px;color:#334155;font-weight:600;">{_html.escape(str(user['name']))} {badge}</td>
                <td style="padding:10px 12px;font-size:13px;color:#64748b;">{role_label}</td>
                <td style="padding:10px 12px;font-size:13px;color:#0f766e;font-weight:700;text-align:center;">{_mostra(user['processes_moved'])}</td>
                <td style="padding:10px 12px;font-size:13px;color:#16a34a;font-weight:700;text-align:center;">{user['tasks_completed']}</td>
                <td style="padding:10px 12px;font-size:13px;color:{overdue_color};font-weight:600;text-align:center;">{user['tasks_overdue']}</td>
                <td style="padding:10px 12px;font-size:13px;color:{pending_color};font-weight:600;text-align:center;">{user['tasks_pending']}</td>
            </tr>"""

    # Top performers
    top_performers = sorted(
        report["users"],
        key=lambda x: _n(x["processes_moved"]) + _n(x["tasks_completed"]),
        reverse=True
    )[:3]
    top_performers_html = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, tp in enumerate(top_performers):
        score = _n(tp["processes_moved"]) + _n(tp["tasks_completed"])
        if score > 0:
            top_performers_html += f"""
                <div style="display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #f1f5f9;">
                    <span style="font-size:20px;margin-right:10px;">{medals[i]}</span>
                    <span style="font-size:14px;font-weight:600;color:#334155;">{_html.escape(str(tp['name']))}</span>
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
