"""
====================================================================
DATA AGGREGATOR SERVICE - CREDITOIMO
====================================================================
Serviço de agregação e deduplicação de dados extraídos de documentos.

Implementa a lógica de importação "cliente a cliente":
1. Acumula dados extraídos de múltiplos documentos em memória
2. Deduplica campos (usa valor mais recente quando há conflito)
3. Agrega salários por empresa (lista + soma total)
4. Consolida e salva uma única vez por cliente

Regras especiais:
- Salários de empresas diferentes são agregados (somados)
- Salários da mesma empresa não são duplicados (usa mais recente)
- Dados pessoais (NIF, data nascimento) usam sempre valor mais recente
- Créditos CRC são agregados na lista, não substituídos
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger(__name__)


class ClientDataAggregator:
    """
    Agregador de dados para um único cliente.
    
    Acumula extrações de múltiplos documentos e consolida
    antes de salvar na base de dados.
    """
    
    def __init__(self, process_id: str, client_name: str):
        self.process_id = process_id
        self.client_name = client_name
        self.documents_processed: List[Dict[str, Any]] = []
        
        # Dados acumulados por categoria
        self.personal_data: Dict[str, Any] = {}
        self.financial_data: Dict[str, Any] = {}
        self.real_estate_data: Dict[str, Any] = {}
        self.other_data: Dict[str, Any] = {}
        
        # Lista especial de salários (por empresa)
        # Estrutura: {empresa_normalizada: {empresa, salario_bruto, salario_liquido, tipo_contrato, mes_ref, timestamp}}
        self.salarios_por_empresa: Dict[str, Dict[str, Any]] = {}
        
        # Lista de créditos (CRC) - não sobrescreve, agrega
        self.creditos_ativos: List[Dict[str, Any]] = []
        
        # Timestamp da última actualização
        self.last_update = datetime.now(timezone.utc)
    
    def _normalize_empresa(self, empresa: str) -> str:
        """Normalizar nome de empresa para comparação."""
        if not empresa:
            return ""
        
        # Remover prefixos/sufixos comuns
        empresa = empresa.strip().lower()
        for suffix in [", lda", " lda", ", sa", " sa", " unipessoal", ", unipessoal"]:
            empresa = empresa.replace(suffix, "")
        
        # Remover caracteres especiais
        empresa = ''.join(c for c in empresa if c.isalnum() or c.isspace())
        empresa = ' '.join(empresa.split())  # Normalizar espaços
        
        return empresa
    
    def add_extraction(
        self,
        document_type: str,
        extracted_data: Dict[str, Any],
        filename: str = ""
    ):
        """
        Adicionar dados extraídos de um documento.
        
        Args:
            document_type: Tipo do documento (cc, recibo_vencimento, irs, etc.)
            extracted_data: Dados extraídos pelo LLM
            filename: Nome do ficheiro original
        """
        timestamp = datetime.now(timezone.utc)
        
        # Registar documento processado
        self.documents_processed.append({
            "document_type": document_type,
            "filename": filename,
            "processed_at": timestamp.isoformat(),
            "fields_count": len(extracted_data)
        })
        
        # Processar baseado no tipo de documento
        if document_type == 'cc':
            self._process_cc(extracted_data, timestamp)
        elif document_type in ['recibo_vencimento', 'payslip']:
            self._process_recibo(extracted_data, timestamp)
        elif document_type == 'irs':
            self._process_irs(extracted_data, timestamp)
        elif document_type == 'mapa_crc':
            self._process_crc(extracted_data, timestamp)
        elif document_type == 'contrato_trabalho':
            self._process_contrato(extracted_data, timestamp)
        elif document_type == 'cpcv':
            self._process_cpcv(extracted_data, timestamp)
        elif document_type == 'caderneta_predial':
            self._process_caderneta(extracted_data, timestamp)
        elif document_type == 'simulacao_credito':
            self._process_simulacao(extracted_data, timestamp)
        elif document_type == 'extrato_bancario':
            self._process_extrato(extracted_data, timestamp)
        else:
            self._process_generic(extracted_data, timestamp)
        
        self.last_update = timestamp
        logger.info(f"[AGGREGATOR] {self.client_name}: +{document_type} ({len(extracted_data)} campos)")
    
    def _process_cc(self, data: Dict[str, Any], timestamp: datetime):
        """Processar dados do Cartão de Cidadão."""
        field_mapping = {
            'nif': 'nif',
            'numero_documento': 'documento_id',
            'data_nascimento': 'data_nascimento',
            'data_validade': 'data_validade_cc',
            'naturalidade': 'naturalidade',
            'nacionalidade': 'nacionalidade',
            'sexo': 'sexo',
            'morada': 'morada',
            'codigo_postal': 'codigo_postal',
            'pai': 'nome_pai',
            'mae': 'nome_mae',
            'nome_completo': 'nome_completo',
        }
        
        for src, dest in field_mapping.items():
            if data.get(src):
                self.personal_data[dest] = data[src]
    
    def _process_recibo(self, data: Dict[str, Any], timestamp: datetime):
        """
        Processar dados do Recibo de Vencimento.
        
        REGRA ESPECIAL: Salários de empresas diferentes são agregados.
        SUPORTE: Recibos de PT, FR, ES, UK, DE (portugueses no estrangeiro).
        """
        # Identificar país de origem
        pais_origem = data.get('pais_origem', 'PT')
        
        # Extrair empresa
        empresa = data.get('empresa')
        if isinstance(empresa, dict):
            empresa = empresa.get('nome', '')
        empresa = empresa or data.get('entidade_patronal', '') or 'Desconhecida'
        
        empresa_norm = self._normalize_empresa(empresa)
        
        # Extrair valores do salário
        salario_info = {
            'empresa': empresa,
            'empresa_normalizada': empresa_norm,
            'salario_bruto': self._parse_money(data.get('salario_bruto')),
            'salario_liquido': self._parse_money(data.get('salario_liquido')),
            'tipo_contrato': data.get('tipo_contrato'),
            'categoria_profissional': data.get('categoria_profissional'),
            'mes_referencia': data.get('mes_referencia'),
            'pais_origem': pais_origem,
            'moeda': data.get('moeda', 'EUR'),
            'timestamp': timestamp.isoformat()
        }
        
        # Remover valores None
        salario_info = {k: v for k, v in salario_info.items() if v is not None}
        
        if empresa_norm:
            # Verificar se já existe salário desta empresa
            if empresa_norm in self.salarios_por_empresa:
                # Actualizar apenas se mais recente ou com mais dados
                if salario_info.get('salario_liquido') or salario_info.get('salario_bruto'):
                    self.salarios_por_empresa[empresa_norm] = salario_info
                    logger.info(f"[AGGREGATOR] Actualizado salário empresa '{empresa}' ({pais_origem}) (existia)")
            else:
                self.salarios_por_empresa[empresa_norm] = salario_info
                logger.info(f"[AGGREGATOR] Novo salário empresa '{empresa}' ({pais_origem})")
        
        # NIF do funcionário (se presente e válido para PT)
        nif = data.get('nif')
        if nif and pais_origem == 'PT':
            self.personal_data['nif'] = nif
        elif nif and pais_origem != 'PT':
            # Guardar NIF estrangeiro separadamente
            self.personal_data[f'nif_{pais_origem.lower()}'] = nif
            
        if data.get('nome_funcionario'):
            self.personal_data['nome_recibo'] = data['nome_funcionario']
        
        # Guardar país de trabalho se diferente de PT
        if pais_origem and pais_origem != 'PT':
            self.other_data['pais_trabalho'] = pais_origem
            self.other_data['trabalha_no_estrangeiro'] = True
    
    def _process_irs(self, data: Dict[str, Any], timestamp: datetime):
        """
        Processar dados da Declaração de IRS.
        SUPORTE: Declarações de PT, FR, ES (portugueses no estrangeiro).
        """
        # Identificar país de origem
        pais_origem = data.get('pais_origem', 'PT')
        
        # NIF do titular
        if data.get('nif_titular'):
            if pais_origem == 'PT':
                self.personal_data['nif'] = data['nif_titular']
            else:
                self.personal_data[f'nif_{pais_origem.lower()}'] = data['nif_titular']
        
        # Morada fiscal (importante para residentes no estrangeiro)
        if data.get('morada_fiscal'):
            self.other_data['morada_fiscal'] = data['morada_fiscal']
            self.other_data[f'morada_fiscal_{pais_origem.lower()}'] = data['morada_fiscal']
        
        # Estado civil
        if data.get('estado_civil_fiscal'):
            estado = data['estado_civil_fiscal'].lower()
            if any(x in estado for x in ['casad', 'marié', 'married']):
                self.personal_data['estado_civil'] = 'casado'
            elif any(x in estado for x in ['soltei', 'célibat', 'single']):
                self.personal_data['estado_civil'] = 'solteiro'
            elif any(x in estado for x in ['uni', 'facto', 'pacsé']):
                self.personal_data['estado_civil'] = 'uniao_facto'
        
        # Rendimentos anuais
        if data.get('rendimento_liquido_anual'):
            self.financial_data[f'rendimento_anual_{pais_origem.lower()}'] = self._parse_money(data['rendimento_liquido_anual'])
            # Calcular mensal dependendo do país
            anual = self._parse_money(data['rendimento_liquido_anual'])
            if anual:
                # Portugal = 14 meses, França/outros = 12 meses
                meses = 14 if pais_origem == 'PT' else 12
                self.financial_data['rendimento_mensal_irs'] = round(anual / meses, 2)
                self.financial_data['rendimento_anual'] = anual
        
        # Co-titular (cônjuge)
        if data.get('nif_titular_2') or data.get('nome_titular_2'):
            self.other_data['conjuge'] = {
                'nome': data.get('nome_titular_2'),
                'nif': data.get('nif_titular_2')
            }
        
        # Marcar se declaração estrangeira
        if pais_origem and pais_origem != 'PT':
            self.other_data['pais_residencia_fiscal'] = pais_origem
            self.other_data['residente_no_estrangeiro'] = True
    
    def _process_crc(self, data: Dict[str, Any], timestamp: datetime):
        """Processar dados do Mapa CRC (Central Responsabilidades Crédito)."""
        # NIF do titular
        titular = data.get('titular', {})
        if titular.get('nif'):
            self.personal_data['nif'] = titular['nif']
        
        # Resumo de dívidas
        resumo = data.get('resumo', {})
        if resumo.get('total_divida'):
            self.financial_data['divida_total_crc'] = self._parse_money(resumo['total_divida'])
        if resumo.get('prestacao_mensal_total'):
            self.financial_data['prestacao_creditos_mensal'] = self._parse_money(resumo['prestacao_mensal_total'])
        
        # Lista de créditos - agregar sem duplicar
        creditos = data.get('creditos', [])
        for credito in creditos:
            if not isinstance(credito, dict):
                continue
            
            # Normalizar dados do crédito
            credito_info = {
                'instituicao': credito.get('instituicao'),
                'tipo': credito.get('tipo_produto', 'Outro'),
                'valor_divida': self._parse_money(credito.get('valor_em_divida')),
                'prestacao': self._parse_money(credito.get('prestacao_mensal')),
                'data_fim': credito.get('data_fim'),
                'em_incumprimento': credito.get('em_incumprimento', False)
            }
            credito_info = {k: v for k, v in credito_info.items() if v is not None}
            
            # Verificar se já existe crédito idêntico
            is_duplicate = any(
                c.get('instituicao') == credito_info.get('instituicao') and
                c.get('tipo') == credito_info.get('tipo') and
                c.get('valor_divida') == credito_info.get('valor_divida')
                for c in self.creditos_ativos
            )
            
            if not is_duplicate and credito_info.get('instituicao'):
                self.creditos_ativos.append(credito_info)
    
    def _process_contrato(self, data: Dict[str, Any], timestamp: datetime):
        """Processar dados do Contrato de Trabalho."""
        colaborador = data.get('colaboradora', data.get('funcionario', {}))
        empresa = data.get('empresa', {})
        
        if isinstance(empresa, str):
            empresa = {'nome': empresa}
        
        if colaborador.get('tipo_contrato'):
            self.financial_data['tipo_contrato'] = colaborador['tipo_contrato']
        if colaborador.get('data_inicio'):
            self.financial_data['data_inicio_trabalho'] = colaborador['data_inicio']
        if colaborador.get('nif'):
            self.personal_data['nif'] = colaborador['nif']
        if empresa.get('nome'):
            self.financial_data['empresa'] = empresa['nome']
    
    def _process_cpcv(self, data: Dict[str, Any], timestamp: datetime):
        """Processar dados do CPCV."""
        imovel = data.get('imovel', {})
        valores = data.get('valores', {})
        datas = data.get('datas', {})
        
        # Dados do imóvel
        if imovel.get('morada_completa') or imovel.get('localizacao'):
            self.real_estate_data['localizacao'] = imovel.get('morada_completa') or imovel.get('localizacao')
        if imovel.get('tipologia'):
            self.real_estate_data['tipologia'] = imovel['tipologia']
        if imovel.get('area_util'):
            self.real_estate_data['area'] = imovel['area_util']
        
        # Valores do negócio
        if valores.get('preco_total'):
            self.real_estate_data['valor_imovel'] = self._parse_money(valores['preco_total'])
        if valores.get('sinal'):
            self.financial_data['valor_entrada'] = self._parse_money(valores['sinal'])
        if valores.get('valor_financiamento'):
            self.financial_data['valor_pretendido'] = self._parse_money(valores['valor_financiamento'])
        
        # Datas
        if datas.get('data_escritura_prevista'):
            self.real_estate_data['data_escritura_prevista'] = datas['data_escritura_prevista']
        
        # Compradores
        compradores = data.get('compradores', [])
        if compradores:
            self.other_data['co_buyers'] = compradores
            # Primeiro comprador vai para dados pessoais
            if compradores[0]:
                comp = compradores[0]
                if comp.get('nif'):
                    self.personal_data['nif'] = comp['nif']
                if comp.get('morada'):
                    self.personal_data['morada'] = comp['morada']
                if comp.get('estado_civil'):
                    self.personal_data['estado_civil'] = comp['estado_civil']
    
    def _process_caderneta(self, data: Dict[str, Any], timestamp: datetime):
        """Processar dados da Caderneta Predial."""
        field_mapping = {
            'artigo_matricial': 'artigo_matricial',
            'valor_patrimonial_tributario': 'valor_patrimonial',
            'area_bruta': 'area',
            'localizacao': 'localizacao',
            'tipologia': 'tipologia',
        }
        for src, dest in field_mapping.items():
            if data.get(src):
                self.real_estate_data[dest] = data[src]
    
    def _process_simulacao(self, data: Dict[str, Any], timestamp: datetime):
        """Processar dados da Simulação de Crédito."""
        credito = data.get('credito', {})
        imovel = data.get('imovel', {})
        
        if credito.get('montante_financiamento'):
            self.financial_data['valor_pretendido'] = self._parse_money(credito['montante_financiamento'])
        if credito.get('prazo_anos'):
            self.financial_data['prazo_anos'] = credito['prazo_anos']
        if credito.get('prestacao_mensal'):
            self.financial_data['prestacao_estimada'] = self._parse_money(credito['prestacao_mensal'])
        if data.get('banco'):
            self.financial_data['banco'] = data['banco']
        
        if imovel.get('valor_aquisicao'):
            self.real_estate_data['valor_imovel'] = self._parse_money(imovel['valor_aquisicao'])
    
    def _process_extrato(self, data: Dict[str, Any], timestamp: datetime):
        """Processar dados do Extrato Bancário."""
        if data.get('titular'):
            self.personal_data['nome_extrato'] = data['titular']
        if data.get('nif'):
            self.personal_data['nif'] = data['nif']
        
        saldos = data.get('saldos', {})
        if saldos.get('final'):
            self.financial_data['saldo_bancario'] = self._parse_money(saldos['final'])
    
    def _process_generic(self, data: Dict[str, Any], timestamp: datetime):
        """Processar documento genérico."""
        # Tentar extrair campos comuns
        if data.get('nif'):
            self.personal_data['nif'] = data['nif']
        if data.get('nome'):
            self.personal_data['nome_documento'] = data['nome']
    
    def _parse_money(self, value) -> Optional[float]:
        """Converter valor monetário para float."""
        if not value:
            return None
        try:
            if isinstance(value, (int, float)):
                return float(value)
            val_str = str(value).replace('€', '').replace(',', '.').replace(' ', '').strip()
            return float(val_str)
        except (ValueError, TypeError):
            return None
    
    def get_consolidated_data(self) -> Dict[str, Any]:
        """
        Obter dados consolidados e prontos para guardar na DB.
        
        Returns:
            Dict com todas as categorias de dados agregados
        """
        result = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "ai_import_aggregated": True,
            "ai_import_timestamp": self.last_update.isoformat(),
            "ai_documents_count": len(self.documents_processed)
        }
        
        # Personal data
        if self.personal_data:
            result["personal_data"] = self.personal_data
        
        # Financial data
        financial = dict(self.financial_data)
        
        # === AGREGAR SALÁRIOS ===
        if self.salarios_por_empresa:
            salarios_list = list(self.salarios_por_empresa.values())
            financial["salarios"] = salarios_list
            
            # Calcular soma total
            soma_bruto = sum(s.get('salario_bruto', 0) or 0 for s in salarios_list)
            soma_liquido = sum(s.get('salario_liquido', 0) or 0 for s in salarios_list)
            
            if soma_bruto > 0:
                financial["rendimento_bruto_total"] = round(soma_bruto, 2)
            if soma_liquido > 0:
                financial["rendimento_liquido_total"] = round(soma_liquido, 2)
            
            # Número de fontes de rendimento
            financial["num_fontes_rendimento"] = len(salarios_list)
            
            logger.info(f"[AGGREGATOR] {self.client_name}: {len(salarios_list)} salários agregados, "
                       f"total líquido: {soma_liquido:.2f}€")
        
        # Agregar créditos CRC
        if self.creditos_ativos:
            financial["creditos_ativos"] = self.creditos_ativos
            financial["numero_creditos_ativos"] = len(self.creditos_ativos)
            
            # Calcular totais
            divida_total = sum(c.get('valor_divida', 0) or 0 for c in self.creditos_ativos)
            prestacao_total = sum(c.get('prestacao', 0) or 0 for c in self.creditos_ativos)
            
            if divida_total > 0:
                financial["divida_total_crc"] = round(divida_total, 2)
            if prestacao_total > 0:
                financial["prestacao_creditos_mensal"] = round(prestacao_total, 2)
        
        if financial:
            result["financial_data"] = financial
        
        # Real estate data
        if self.real_estate_data:
            result["real_estate_data"] = self.real_estate_data
        
        # Other data
        if self.other_data.get('co_buyers'):
            result["co_buyers"] = self.other_data['co_buyers']
        if self.other_data.get('conjuge'):
            result["co_applicants"] = [self.other_data['conjuge']]
        
        # Log de documentos processados
        result["ai_extraction_history"] = [{
            "aggregated_import": True,
            "timestamp": self.last_update.isoformat(),
            "documents_processed": self.documents_processed,
            "total_documents": len(self.documents_processed)
        }]
        
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """Obter resumo do agregador."""
        salarios_sum = sum(
            s.get('salario_liquido', 0) or 0 
            for s in self.salarios_por_empresa.values()
        )
        
        return {
            "process_id": self.process_id,
            "client_name": self.client_name,
            "documents_count": len(self.documents_processed),
            "salarios_count": len(self.salarios_por_empresa),
            "salarios_total": round(salarios_sum, 2),
            "creditos_count": len(self.creditos_ativos),
            "has_personal_data": bool(self.personal_data),
            "has_financial_data": bool(self.financial_data) or bool(self.salarios_por_empresa),
            "has_real_estate_data": bool(self.real_estate_data)
        }


class SessionAggregator:
    """
    Gestor de sessão de importação agregada.
    
    Mantém agregadores para múltiplos clientes durante uma sessão de importação.
    """
    
    def __init__(self, session_id: str, user_email: str):
        self.session_id = session_id
        self.user_email = user_email
        self.created_at = datetime.now(timezone.utc)
        
        # Agregadores por process_id
        self.aggregators: Dict[str, ClientDataAggregator] = {}
        
        # Estatísticas da sessão
        self.total_files = 0
        self.processed_files = 0
        self.errors = 0
    
    def get_or_create_aggregator(self, process_id: str, client_name: str) -> ClientDataAggregator:
        """Obter ou criar agregador para um cliente."""
        if process_id not in self.aggregators:
            self.aggregators[process_id] = ClientDataAggregator(process_id, client_name)
            logger.info(f"[SESSION] Novo agregador criado para '{client_name}' ({process_id})")
        return self.aggregators[process_id]
    
    def add_file_extraction(
        self,
        process_id: str,
        client_name: str,
        document_type: str,
        extracted_data: Dict[str, Any],
        filename: str = ""
    ):
        """Adicionar extração de um ficheiro."""
        aggregator = self.get_or_create_aggregator(process_id, client_name)
        aggregator.add_extraction(document_type, extracted_data, filename)
        self.processed_files += 1
    
    def increment_error(self):
        """Incrementar contador de erros."""
        self.errors += 1
    
    def get_all_consolidated_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Obter dados consolidados de todos os clientes.
        
        Returns:
            Dict {process_id: consolidated_data}
        """
        return {
            pid: agg.get_consolidated_data()
            for pid, agg in self.aggregators.items()
        }
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Obter resumo da sessão."""
        client_summaries = [
            agg.get_summary() 
            for agg in self.aggregators.values()
        ]
        
        return {
            "session_id": self.session_id,
            "user_email": self.user_email,
            "created_at": self.created_at.isoformat(),
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "errors": self.errors,
            "clients_count": len(self.aggregators),
            "clients": client_summaries
        }


# Cache de sessões activas (em memória)
# Estrutura: {session_id: SessionAggregator}
active_sessions: Dict[str, SessionAggregator] = {}


async def persist_session_to_db(session: SessionAggregator):
    """Persistir sessão na base de dados para recuperação após reinício."""
    from database import db
    
    session_data = {
        "session_id": session.session_id,
        "user_email": session.user_email,
        "created_at": session.created_at.isoformat(),
        "total_files": session.total_files,
        "processed_files": session.processed_files,
        "errors": session.errors,
        "clients_count": len(session.aggregators),
        "is_active": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.aggregated_sessions.update_one(
        {"session_id": session.session_id},
        {"$set": session_data},
        upsert=True
    )


async def load_session_from_db(session_id: str) -> Optional[SessionAggregator]:
    """Tentar carregar sessão da DB."""
    from database import db
    
    session_doc = await db.aggregated_sessions.find_one(
        {"session_id": session_id, "is_active": True},
        {"_id": 0}
    )
    
    if session_doc:
        session = SessionAggregator(session_id, session_doc.get("user_email", "unknown"))
        session.total_files = session_doc.get("total_files", 0)
        session.processed_files = session_doc.get("processed_files", 0)
        session.errors = session_doc.get("errors", 0)
        
        # Restaurar created_at
        if session_doc.get("created_at"):
            try:
                session.created_at = datetime.fromisoformat(session_doc["created_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        logger.info(f"[AGGREGATOR] Sessão recuperada da DB: {session_id}")
        return session
    
    return None


def get_or_create_session(session_id: str, user_email: str) -> SessionAggregator:
    """Obter ou criar sessão de agregação."""
    if session_id not in active_sessions:
        active_sessions[session_id] = SessionAggregator(session_id, user_email)
        logger.info(f"[AGGREGATOR] Nova sessão criada: {session_id}")
    return active_sessions[session_id]


def get_session(session_id: str) -> Optional[SessionAggregator]:
    """Obter sessão existente (apenas da memória - use get_session_async para DB)."""
    return active_sessions.get(session_id)


async def get_session_async(session_id: str) -> Optional[SessionAggregator]:
    """Obter sessão existente, verificando primeiro na memória e depois na DB."""
    # Verificar na memória
    session = active_sessions.get(session_id)
    if session:
        return session
    
    # Tentar recuperar da DB
    session = await load_session_from_db(session_id)
    if session:
        # Guardar em memória para próximos acessos
        active_sessions[session_id] = session
        return session
    
    return None


def close_session(session_id: str) -> Optional[SessionAggregator]:
    """Fechar e remover sessão."""
    return active_sessions.pop(session_id, None)


def cleanup_old_sessions(max_age_hours: int = 24):
    """Limpar sessões antigas."""
    now = datetime.now(timezone.utc)
    expired = []
    
    for sid, session in active_sessions.items():
        age = (now - session.created_at).total_seconds() / 3600
        if age > max_age_hours:
            expired.append(sid)
    
    for sid in expired:
        del active_sessions[sid]
        logger.info(f"[AGGREGATOR] Sessão expirada removida: {sid}")
    
    return len(expired)
