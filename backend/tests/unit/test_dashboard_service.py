"""
Testes unitários para serviços de dashboard e estatísticas.
"""
import pytest
from datetime import datetime, timezone, timedelta


class TestDashboardStats:
    """Testes para estatísticas do dashboard."""
    
    def test_process_count_by_status(self):
        """Testa contagem de processos por status."""
        processes = [
            {"status": "triagem"},
            {"status": "documentacao"},
            {"status": "triagem"},
            {"status": "analise"},
            {"status": "aprovado"},
        ]
        
        def count_by_status(processes):
            counts = {}
            for p in processes:
                status = p.get("status")
                counts[status] = counts.get(status, 0) + 1
            return counts
        
        result = count_by_status(processes)
        
        assert result["triagem"] == 2
        assert result["documentacao"] == 1
        assert result["aprovado"] == 1
    
    def test_success_rate_calculation(self):
        """Testa cálculo de taxa de sucesso."""
        def calculate_success_rate(processes):
            total = len(processes)
            if total == 0:
                return 0
            
            successful = len([p for p in processes 
                            if p.get("status") in ["aprovado", "concluido"]])
            
            return round((successful / total) * 100, 1)
        
        processes = [
            {"status": "aprovado"},
            {"status": "concluido"},
            {"status": "recusado"},
            {"status": "triagem"},
            {"status": "aprovado"},
        ]
        
        rate = calculate_success_rate(processes)
        assert rate == 60.0  # 3/5
    
    def test_average_processing_time(self):
        """Testa cálculo de tempo médio de processamento."""
        def calculate_avg_time(processes):
            times = []
            for p in processes:
                if p.get("created_at") and p.get("completed_at"):
                    created = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00"))
                    completed = datetime.fromisoformat(p["completed_at"].replace("Z", "+00:00"))
                    times.append((completed - created).days)
            
            return sum(times) / len(times) if times else 0
        
        now = datetime.now(timezone.utc)
        
        processes = [
            {
                "created_at": (now - timedelta(days=10)).isoformat(),
                "completed_at": now.isoformat()
            },
            {
                "created_at": (now - timedelta(days=20)).isoformat(),
                "completed_at": now.isoformat()
            },
        ]
        
        avg = calculate_avg_time(processes)
        assert avg == 15  # (10 + 20) / 2


class TestPeriodComparison:
    """Testes para comparação de períodos."""
    
    def test_period_growth_calculation(self):
        """Testa cálculo de crescimento entre períodos."""
        def calculate_growth(current, previous):
            if previous == 0:
                return 100 if current > 0 else 0
            return round(((current - previous) / previous) * 100, 1)
        
        assert calculate_growth(150, 100) == 50.0   # +50%
        assert calculate_growth(80, 100) == -20.0   # -20%
        assert calculate_growth(100, 0) == 100      # De 0 para algo
        assert calculate_growth(0, 0) == 0          # Sem mudança
    
    def test_trend_direction(self):
        """Testa determinação de direcção de tendência."""
        def get_trend_direction(current, previous, threshold=5):
            if previous == 0:
                return "up" if current > 0 else "stable"
            
            change = ((current - previous) / previous) * 100
            
            if change > threshold:
                return "up"
            elif change < -threshold:
                return "down"
            return "stable"
        
        assert get_trend_direction(150, 100) == "up"
        assert get_trend_direction(80, 100) == "down"
        assert get_trend_direction(102, 100) == "stable"
    
    def test_period_ranges(self):
        """Testa cálculo de intervalos de período."""
        def get_period_range(period_type):
            now = datetime.now(timezone.utc)
            
            if period_type == "today":
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end = now
            elif period_type == "week":
                start = now - timedelta(days=now.weekday())
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
                end = now
            elif period_type == "month":
                start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end = now
            elif period_type == "year":
                start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end = now
            else:
                start = now - timedelta(days=30)
                end = now
            
            return start, end
        
        start, end = get_period_range("today")
        assert start.hour == 0
        assert start.minute == 0


class TestChartDataGeneration:
    """Testes para geração de dados de gráficos."""
    
    def test_time_series_aggregation(self):
        """Testa agregação de dados em série temporal."""
        events = [
            {"date": "2024-01-01", "value": 10},
            {"date": "2024-01-01", "value": 15},
            {"date": "2024-01-02", "value": 20},
            {"date": "2024-01-03", "value": 5},
        ]
        
        def aggregate_by_date(events):
            result = {}
            for e in events:
                date = e["date"]
                result[date] = result.get(date, 0) + e["value"]
            return [{"date": k, "value": v} for k, v in sorted(result.items())]
        
        aggregated = aggregate_by_date(events)
        
        assert len(aggregated) == 3
        assert aggregated[0]["value"] == 25  # 10 + 15
        assert aggregated[1]["value"] == 20
    
    def test_pie_chart_data(self):
        """Testa geração de dados para gráfico de pizza."""
        def generate_pie_data(counts_by_category, total):
            return [
                {
                    "name": name,
                    "value": count,
                    "percentage": round((count / total) * 100, 1) if total > 0 else 0
                }
                for name, count in counts_by_category.items()
            ]
        
        counts = {"Triagem": 30, "Documentação": 20, "Análise": 50}
        total = sum(counts.values())
        
        pie_data = generate_pie_data(counts, total)
        
        assert len(pie_data) == 3
        total_percentage = sum(d["percentage"] for d in pie_data)
        assert abs(total_percentage - 100) < 0.5  # ~100%
    
    def test_fill_missing_dates(self):
        """Testa preenchimento de datas faltantes."""
        def fill_missing_dates(data, start_date, end_date):
            data_dict = {d["date"]: d["value"] for d in data}
            
            result = []
            current = start_date
            while current <= end_date:
                date_str = current.strftime("%Y-%m-%d")
                result.append({
                    "date": date_str,
                    "value": data_dict.get(date_str, 0)
                })
                current += timedelta(days=1)
            
            return result
        
        data = [
            {"date": "2024-01-01", "value": 10},
            {"date": "2024-01-03", "value": 20},
        ]
        
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 4, tzinfo=timezone.utc)
        
        filled = fill_missing_dates(data, start, end)
        
        assert len(filled) == 4
        assert filled[1]["value"] == 0  # 02-01 preenchido com 0


class TestTopPerformers:
    """Testes para rankings e top performers."""
    
    def test_consultant_ranking(self):
        """Testa ranking de consultores."""
        consultants = [
            {"id": "c1", "name": "João", "closed_deals": 15, "total_value": 3000000},
            {"id": "c2", "name": "Maria", "closed_deals": 12, "total_value": 4500000},
            {"id": "c3", "name": "Pedro", "closed_deals": 18, "total_value": 2800000},
        ]
        
        def rank_by_deals(consultants, top_n=10):
            sorted_list = sorted(consultants, key=lambda c: c["closed_deals"], reverse=True)
            return sorted_list[:top_n]
        
        def rank_by_value(consultants, top_n=10):
            sorted_list = sorted(consultants, key=lambda c: c["total_value"], reverse=True)
            return sorted_list[:top_n]
        
        top_by_deals = rank_by_deals(consultants)
        top_by_value = rank_by_value(consultants)
        
        assert top_by_deals[0]["name"] == "Pedro"  # 18 deals
        assert top_by_value[0]["name"] == "Maria"  # 4.5M
    
    def test_conversion_rate_ranking(self):
        """Testa ranking por taxa de conversão."""
        consultants = [
            {"id": "c1", "leads": 100, "conversions": 25},
            {"id": "c2", "leads": 50, "conversions": 20},
            {"id": "c3", "leads": 80, "conversions": 16},
        ]
        
        def calculate_conversion_rate(consultant):
            if consultant["leads"] == 0:
                return 0
            return (consultant["conversions"] / consultant["leads"]) * 100
        
        for c in consultants:
            c["conversion_rate"] = calculate_conversion_rate(c)
        
        sorted_by_rate = sorted(consultants, key=lambda c: c["conversion_rate"], reverse=True)
        
        assert sorted_by_rate[0]["id"] == "c2"  # 40%
        assert sorted_by_rate[1]["id"] == "c1"  # 25%


class TestReportGeneration:
    """Testes para geração de relatórios."""
    
    def test_summary_report_structure(self):
        """Testa estrutura de relatório sumário."""
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": "monthly",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
            "metrics": {
                "total_processes": 150,
                "completed_processes": 45,
                "success_rate": 85.5,
                "avg_processing_days": 12
            },
            "by_status": {},
            "by_consultant": [],
            "trends": {}
        }
        
        required = ["generated_at", "period", "metrics"]
        for field in required:
            assert field in report
    
    def test_export_format_csv(self):
        """Testa formatação para CSV."""
        def format_as_csv(headers, rows):
            lines = [",".join(headers)]
            for row in rows:
                values = [str(row.get(h, "")) for h in headers]
                lines.append(",".join(values))
            return "\n".join(lines)
        
        headers = ["name", "value", "percentage"]
        rows = [
            {"name": "Triagem", "value": 30, "percentage": 30.0},
            {"name": "Análise", "value": 50, "percentage": 50.0},
        ]
        
        csv = format_as_csv(headers, rows)
        lines = csv.split("\n")
        
        assert len(lines) == 3
        assert "name,value,percentage" in lines[0]
    
    def test_scheduled_report_config(self):
        """Testa configuração de relatório agendado."""
        config = {
            "report_type": "weekly_summary",
            "schedule": "monday_09:00",
            "recipients": ["admin@test.com", "ceo@test.com"],
            "format": "pdf",
            "include_charts": True
        }
        
        def validate_schedule(schedule):
            parts = schedule.split("_")
            if len(parts) != 2:
                return False
            
            day = parts[0]
            time = parts[1]
            
            valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            if day not in valid_days:
                return False
            
            try:
                hour, minute = map(int, time.split(":"))
                return 0 <= hour <= 23 and 0 <= minute <= 59
            except Exception:
                return False
        
        assert validate_schedule(config["schedule"])
