/**
 * ProcessDetailsModal Component
 *
 * Modal de detalhes do processo — visualização rápida e edição inline.
 *
 * FASE 3 — Paradigma Relacional (Cliente ↔ Processo):
 * - Interface dividida em DUAS TABS: "Dados do Cliente" e "Dados do Processo"
 * - Dados do Cliente: Nome, Email, Telemóvel, NIF, Estado Civil (vindos de GET /clients/{id})
 * - Dados do Processo: Imóvel, Valores, Crédito, Status, Prioridade (vindos de GET /processes/{id})
 * - O botão "Guardar" dispara dois PUTs concorrentes (Promise.all):
 *   → PUT /clients/{client_id} para campos do cliente
 *   → PUT /processes/{process_id} para campos do processo
 *
 * PERFORMANCE:
 * - Estado isolado do componente pai
 * - Não causa re-renders no KanbanBoard
 */
import React, { memo, useCallback, useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import {
  User, Mail, Phone, Home, MapPin, Euro, Calendar, Users,
  AlertTriangle, Building2, CreditCard, FileText, ExternalLink,
  Loader2, Save, Pencil, X
} from 'lucide-react';
import { safeString } from '../../utils/safeString';
import { getClient, updateClient, updateProcess } from '../../services/api';
import { toast } from 'sonner';

// ── Helpers ────────────────────────────────────────────────────────
const formatCurrency = (value) => {
  if (value == null) return '—';
  return Number(value).toLocaleString('pt-PT') + '€';
};

const ESTADO_CIVIL_OPTIONS = [
  'Solteiro', 'Casado', 'Divorciado', 'Viúvo', 'União de Facto', 'Separado',
];

const ProcessDetailsModal = memo(({
  open,
  onOpenChange,
  process,
  isLockedByOther = false,
  lockedBy,
}) => {
  const navigate = useNavigate();

  // ── Estado de dados ──────────────────────────────────────────────
  const [clientData, setClientData] = useState(null);
  const [clientLoading, setClientLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('client');
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // ── Estado editável do Cliente ───────────────────────────────────
  const [editClient, setEditClient] = useState({
    nome: '',
    email: '',
    telefone: '',
    nif: '',
    estado_civil: '',
  });

  // ── Estado editável do Processo ──────────────────────────────────
  const [editProcess, setEditProcess] = useState({
    property_type: '',
    property_location: '',
    property_value: '',
    loan_amount: '',
    spread: '',
    taxa_esforco: '',
    banco_avaliacao: '',
    valor_avaliacao: '',
    status: '',
    prioridade: 'media',
    notes: '',
  });

  // ── Snapshot original para detetar mudanças ──────────────────────
  const originalClientRef = useRef(null);
  const originalProcessRef = useRef(null);

  // ── Carregar dados do cliente via client_id ──────────────────────
  useEffect(() => {
    if (!open || !process?.client_id) {
      setClientData(null);
      return;
    }
    let cancelled = false;
    const fetchClient = async () => {
      setClientLoading(true);
      try {
        const res = await getClient(process.client_id);
        if (!cancelled) setClientData(res.data);
      } catch {
        setClientData(null);
      } finally {
        if (!cancelled) setClientLoading(false);
      }
    };
    fetchClient();
    return () => { cancelled = true; };
  }, [open, process?.client_id]);

  // ── Preencher estado editável quando os dados carregam ───────────
  useEffect(() => {
    if (!open || !process) return;

    // Dados do Cliente
    const clientName = clientData?.nome || process.client_name || '';
    const clientEmail = clientData?.contacto?.email || process.client_email || '';
    const clientPhone = clientData?.contacto?.telefone || process.client_phone || '';
    const clientNif = clientData?.dados_pessoais?.nif || process.client_nif || process.personal_data?.nif || '';
    const clientEstadoCivil = clientData?.dados_pessoais?.estado_civil || process.personal_data?.estado_civil || '';

    const clientState = {
      nome: clientName,
      email: clientEmail,
      telefone: clientPhone,
      nif: clientNif,
      estado_civil: clientEstadoCivil,
    };
    setEditClient(clientState);
    originalClientRef.current = clientState;

    // Dados do Processo
    const reData = process.real_estate_data || {};
    const crData = process.credit_data || {};
    const processState = {
      property_type: reData.tipo_imovel || process.property_type || '',
      property_location: reData.localizacao || process.property_location || '',
      property_value: reData.valor_imovel || process.property_value || '',
      loan_amount: reData.valor_financiado || process.loan_amount || '',
      spread: crData.spread || process.spread || '',
      taxa_esforco: crData.taxa_esforco || process.taxa_esforco || '',
      banco_avaliacao: crData.valuation_bank || crData.banco_avaliacao || '',
      valor_avaliacao: crData.valuation_value || crData.valor_avaliacao || '',
      status: process.status || '',
      prioridade: process.prioridade || process.priority || 'media',
      notes: process.notes || '',
    };
    setEditProcess(processState);
    originalProcessRef.current = processState;

    // Reset editing state
    setIsEditing(false);
    setHasChanges(false);
    setActiveTab('client');
  }, [open, process, clientData]);

  // ── Detectar mudanças ────────────────────────────────────────────
  useEffect(() => {
    if (!originalClientRef.current || !originalProcessRef.current) return;

    const clientChanged = Object.keys(editClient).some(
      key => editClient[key] !== originalClientRef.current[key]
    );
    const processChanged = Object.keys(editProcess).some(
      key => String(editProcess[key]) !== String(originalProcessRef.current[key])
    );
    setHasChanges(clientChanged || processChanged);
  }, [editClient, editProcess]);

  // ── Navegar para página completa ─────────────────────────────────
  const handleOpenFullPage = useCallback(() => {
    onOpenChange?.(false);
    navigate(`/process/${process?.id}`);
  }, [navigate, onOpenChange, process?.id]);

  // ── handleSave: Gravação concorrente com Promise.all ─────────────
  const handleSave = useCallback(async () => {
    if (!process?.id) return;
    setSaving(true);
    try {
      const promises = [];

      // ── 1. PUT /clients/{client_id} — se houver client_id e campos alterados ──
      if (process.client_id) {
        const clientChanged = Object.keys(editClient).some(
          key => editClient[key] !== originalClientRef.current?.[key]
        );
        if (clientChanged) {
          const clientPayload = {
            nome: editClient.nome || undefined,
            contacto: {
              email: editClient.email || undefined,
              telefone: editClient.telefone || undefined,
            },
            dados_pessoais: {
              nif: editClient.nif || undefined,
              estado_civil: editClient.estado_civil || undefined,
            },
          };
          promises.push(updateClient(process.client_id, clientPayload));
        }
      }

      // ── 2. PUT /processes/{process_id} — se campos do processo alterados ──
      const processChanged = Object.keys(editProcess).some(
        key => String(editProcess[key]) !== String(originalProcessRef.current?.[key])
      );
      if (processChanged) {
        const processPayload = {};
        // Mapear para a estrutura do backend
        const realEstateData = {};
        if (editProcess.property_type) realEstateData.tipo_imovel = editProcess.property_type;
        if (editProcess.property_location) realEstateData.localizacao = editProcess.property_location;
        if (editProcess.property_value) realEstateData.valor_imovel = Number(editProcess.property_value) || undefined;
        if (editProcess.loan_amount) realEstateData.valor_financiado = Number(editProcess.loan_amount) || undefined;

        const creditData = {};
        if (editProcess.spread) creditData.spread = editProcess.spread;
        if (editProcess.taxa_esforco) creditData.taxa_esforco = editProcess.taxa_esforco;
        if (editProcess.banco_avaliacao) creditData.valuation_bank = editProcess.banco_avaliacao;
        if (editProcess.valor_avaliacao) creditData.valuation_value = Number(editProcess.valor_avaliacao) || undefined;

        if (Object.keys(realEstateData).length > 0) processPayload.real_estate_data = realEstateData;
        if (Object.keys(creditData).length > 0) processPayload.credit_data = creditData;
        if (editProcess.status && editProcess.status !== originalProcessRef.current?.status) {
          processPayload.status = editProcess.status;
        }
        if (editProcess.prioridade && editProcess.prioridade !== originalProcessRef.current?.prioridade) {
          processPayload.prioridade = editProcess.prioridade;
        }
        if (editProcess.notes !== originalProcessRef.current?.notes) {
          processPayload.notes = editProcess.notes;
        }

        if (Object.keys(processPayload).length > 0) {
          promises.push(updateProcess(process.id, processPayload));
        }
      }

      if (promises.length === 0) {
        toast.info('Sem alterações para guardar.');
        setSaving(false);
        return;
      }

      await Promise.all(promises);
      toast.success('Alterações guardadas com sucesso!');
      setIsEditing(false);
      setHasChanges(false);

      // Atualizar snapshots
      originalClientRef.current = { ...editClient };
      originalProcessRef.current = { ...editProcess };

    } catch (error) {
      console.error('Erro ao guardar:', error);
      const detail = error.response?.data?.detail || error.message || 'Erro ao guardar alterações';
      toast.error(typeof detail === 'string' ? detail : 'Erro ao guardar alterações');
    } finally {
      setSaving(false);
    }
  }, [process, editClient, editProcess]);

  // ── Cancelar edição ──────────────────────────────────────────────
  const handleCancelEdit = useCallback(() => {
    if (originalClientRef.current) setEditClient({ ...originalClientRef.current });
    if (originalProcessRef.current) setEditProcess({ ...originalProcessRef.current });
    setIsEditing(false);
    setHasChanges(false);
  }, []);

  if (!process) return null;

  const readOnly = !isEditing || isLockedByOther;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col" aria-describedby="process-dialog-description">
        {/* ── Header ─────────────────────────────────────────────── */}
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-blue-600" />
              Processo #{process.process_number || '—'} — {process.client_name || process.client_data?.name || process.client_data?.personal_data?.nome || 'Cliente'}
            </span>
            <div className="flex items-center gap-2">
              {isEditing ? (
                <>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCancelEdit}
                    className="gap-1"
                  >
                    <X className="h-3.5 w-3.5" />
                    Cancelar
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={saving || !hasChanges}
                    className="gap-1 bg-teal-600 hover:bg-teal-700"
                  >
                    {saving ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Save className="h-3.5 w-3.5" />
                    )}
                    Guardar
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleOpenFullPage}
                    className="gap-1"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Página Completa
                  </Button>
                  {!isLockedByOther && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setIsEditing(true)}
                      className="gap-1"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      Editar
                    </Button>
                  )}
                </>
              )}
            </div>
          </DialogTitle>
          <DialogDescription id="process-dialog-description" className="sr-only">
            Visualização e edição dos detalhes do processo
          </DialogDescription>
        </DialogHeader>

        {/* Lock collision warning */}
        {isLockedByOther && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0" />
            <p className="text-sm text-amber-800 dark:text-amber-200">
              <strong>{lockedBy}</strong> está a editar este processo neste momento.
              Aguarde um instante para evitar conflitos.
            </p>
          </div>
        )}

        {/* ── Tabs: Cliente / Processo ────────────────────────────── */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 overflow-hidden">
          <TabsList className="w-full grid grid-cols-2">
            <TabsTrigger
              value="client"
              className="flex items-center gap-2 data-[state=active]:bg-teal-50 data-[state=active]:text-teal-700 dark:data-[state=active]:bg-teal-950/30 dark:data-[state=active]:text-teal-300"
            >
              <User className="h-3.5 w-3.5" />
              Dados do Cliente
              {process.client_id && (
                <Badge variant="outline" className="text-[9px] border-teal-300 text-teal-600 dark:border-teal-700 dark:text-teal-400 ml-1 py-0">
                  Ficha
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger
              value="process"
              className="flex items-center gap-2 data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700 dark:data-[state=active]:bg-blue-950/30 dark:data-[state=active]:text-blue-300"
            >
              <FileText className="h-3.5 w-3.5" />
              Dados do Processo
            </TabsTrigger>
          </TabsList>

          {/* ══════════════════════════════════════════════════════════
              TAB 1: DADOS DO CLIENTE
              Estes dados pertencem à entidade Cliente (coleção clients).
              Gravação: PUT /clients/{client_id}
              ══════════════════════════════════════════════════════════ */}
          <TabsContent value="client" className="overflow-y-auto max-h-[60vh] mt-0">
            {clientLoading ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">A carregar dados do cliente...</span>
              </div>
            ) : (
              <div className="space-y-4 p-1">
                {/* Indicador de entidade */}
                <div className="flex items-center gap-2 p-2.5 bg-teal-50/70 dark:bg-teal-950/10 border border-teal-100 dark:border-teal-900/30 rounded-lg">
                  <div className="flex items-center justify-center h-8 w-8 rounded-full bg-teal-100 dark:bg-teal-900/30">
                    <User className="h-4 w-4 text-teal-700 dark:text-teal-300" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-teal-700 dark:text-teal-300">
                      Dados do Cliente
                    </p>
                    <p className="text-[10px] text-teal-600/70 dark:text-teal-400/70">
                      {process.client_id
                        ? 'Editados aqui → guardados na ficha do Cliente'
                        : 'Sem client_id associado (dados de fallback do processo)'}
                    </p>
                  </div>
                </div>

                {/* Campos editáveis */}
                <div className="grid grid-cols-2 gap-3">
                  {/* Nome */}
                  <div className="col-span-2 space-y-1.5">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1">
                      <User className="h-3 w-3" /> Nome
                    </Label>
                    {isEditing ? (
                      <Input
                        value={editClient.nome}
                        onChange={(e) => setEditClient(prev => ({ ...prev, nome: e.target.value }))}
                        placeholder="Nome completo"
                      />
                    ) : (
                      <p className="font-medium text-sm">{safeString(editClient.nome) || '—'}</p>
                    )}
                  </div>

                  {/* Email */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1">
                      <Mail className="h-3 w-3" /> Email
                    </Label>
                    {isEditing ? (
                      <Input
                        type="email"
                        value={editClient.email}
                        onChange={(e) => setEditClient(prev => ({ ...prev, email: e.target.value }))}
                        placeholder="email@exemplo.pt"
                      />
                    ) : (
                      <p className="font-medium text-sm flex items-center gap-1">
                        {editClient.email ? (
                          <>
                            <Mail className="h-3 w-3" />
                            {safeString(editClient.email)}
                          </>
                        ) : '—'}
                      </p>
                    )}
                  </div>

                  {/* Telefone */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1">
                      <Phone className="h-3 w-3" /> Telefone
                    </Label>
                    {isEditing ? (
                      <Input
                        value={editClient.telefone}
                        onChange={(e) => setEditClient(prev => ({ ...prev, telefone: e.target.value }))}
                        placeholder="912 345 678"
                      />
                    ) : (
                      <p className="font-medium text-sm flex items-center gap-1">
                        {editClient.telefone ? (
                          <>
                            <Phone className="h-3 w-3" />
                            {safeString(editClient.telefone)}
                          </>
                        ) : '—'}
                      </p>
                    )}
                  </div>

                  {/* NIF */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">NIF</Label>
                    {isEditing ? (
                      <Input
                        value={editClient.nif}
                        onChange={(e) => {
                          const v = e.target.value.replace(/[^\d]/g, '').slice(0, 9);
                          setEditClient(prev => ({ ...prev, nif: v }));
                        }}
                        placeholder="123456789"
                        maxLength={9}
                      />
                    ) : (
                      <p className="font-medium text-sm">{safeString(editClient.nif) || '—'}</p>
                    )}
                  </div>

                  {/* Estado Civil */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Estado Civil</Label>
                    {isEditing ? (
                      <Select
                        value={editClient.estado_civil || ''}
                        onValueChange={(v) => setEditClient(prev => ({ ...prev, estado_civil: v }))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Selecionar..." />
                        </SelectTrigger>
                        <SelectContent>
                          {ESTADO_CIVIL_OPTIONS.map(opt => (
                            <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <p className="font-medium text-sm capitalize">{safeString(editClient.estado_civil) || '—'}</p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          {/* ══════════════════════════════════════════════════════════
              TAB 2: DADOS DO PROCESSO / NEGÓCIO
              Estes dados pertencem à entidade Processo (coleção processes).
              Gravação: PUT /processes/{process_id}
              ══════════════════════════════════════════════════════════ */}
          <TabsContent value="process" className="overflow-y-auto max-h-[60vh] mt-0">
            <div className="space-y-4 p-1">
              {/* Indicador de entidade */}
              <div className="flex items-center gap-2 p-2.5 bg-blue-50/70 dark:bg-blue-950/10 border border-blue-100 dark:border-blue-900/30 rounded-lg">
                <div className="flex items-center justify-center h-8 w-8 rounded-full bg-blue-100 dark:bg-blue-900/30">
                  <FileText className="h-4 w-4 text-blue-700 dark:text-blue-300" />
                </div>
                <div>
                  <p className="text-xs font-medium text-blue-700 dark:text-blue-300">
                    Dados do Processo / Negócio
                  </p>
                  <p className="text-[10px] text-blue-600/70 dark:text-blue-400/70">
                    Editados aqui → guardados no Processo #{process.process_number || '—'}
                  </p>
                </div>
              </div>

              {/* Status e Prioridade (sempre visíveis) */}
              <div className="flex gap-2 flex-wrap">
                <Badge variant="outline" className="capitalize">
                  {editProcess.status?.replace(/_/g, ' ') || '—'}
                </Badge>
                <Badge
                  variant={editProcess.prioridade === 'alta' ? 'destructive' : editProcess.prioridade === 'media' ? 'secondary' : 'outline'}
                  className="capitalize"
                >
                  {editProcess.prioridade === 'alta' ? 'Alta' : editProcess.prioridade === 'media' ? 'Média' : 'Baixa'}
                </Badge>
                {process.process_type && (
                  <Badge variant="outline" className="capitalize text-teal-700 border-teal-300">
                    {process.process_type.replace(/_/g, ' ')}
                  </Badge>
                )}
              </div>

              {/* ── Imóvel ──────────────────────────────────────────── */}
              <div className="bg-blue-50/50 dark:bg-blue-950/10 rounded-lg p-3 border border-blue-100 dark:border-blue-900/30">
                <h4 className="text-xs font-medium text-muted-foreground mb-3 flex items-center gap-1">
                  <Home className="h-3 w-3" />
                  Imóvel
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  {/* Tipo de Imóvel */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Tipo</Label>
                    {isEditing ? (
                      <Input
                        value={editProcess.property_type}
                        onChange={(e) => setEditProcess(prev => ({ ...prev, property_type: e.target.value }))}
                        placeholder="Apartamento, Moradia..."
                      />
                    ) : (
                      <p className="font-medium text-sm capitalize">{safeString(editProcess.property_type) || '—'}</p>
                    )}
                  </div>

                  {/* Localização */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Localização</Label>
                    {isEditing ? (
                      <Input
                        value={editProcess.property_location}
                        onChange={(e) => setEditProcess(prev => ({ ...prev, property_location: e.target.value }))}
                        placeholder="Cidade / Zona"
                      />
                    ) : (
                      <p className="font-medium text-sm flex items-center gap-1">
                        {editProcess.property_location ? (
                          <>
                            <MapPin className="h-3 w-3" />
                            {safeString(editProcess.property_location)}
                          </>
                        ) : '—'}
                      </p>
                    )}
                  </div>

                  {/* Valor do Imóvel */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Valor do Imóvel</Label>
                    {isEditing ? (
                      <Input
                        type="number"
                        value={editProcess.property_value}
                        onChange={(e) => setEditProcess(prev => ({ ...prev, property_value: e.target.value }))}
                        placeholder="250000"
                      />
                    ) : (
                      <p className="font-medium text-sm text-emerald-600 flex items-center gap-1">
                        {editProcess.property_value ? (
                          <>
                            <Euro className="h-3 w-3" />
                            {formatCurrency(editProcess.property_value)}
                          </>
                        ) : '—'}
                      </p>
                    )}
                  </div>

                  {/* Valor Financiado */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Valor Financiado</Label>
                    {isEditing ? (
                      <Input
                        type="number"
                        value={editProcess.loan_amount}
                        onChange={(e) => setEditProcess(prev => ({ ...prev, loan_amount: e.target.value }))}
                        placeholder="200000"
                      />
                    ) : (
                      <p className="font-medium text-sm flex items-center gap-1">
                        {editProcess.loan_amount ? (
                          <>
                            <Euro className="h-3 w-3" />
                            {formatCurrency(editProcess.loan_amount)}
                          </>
                        ) : '—'}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* ── Crédito / Banco ──────────────────────────────────── */}
              <div className="bg-purple-50/50 dark:bg-purple-950/10 rounded-lg p-3 border border-purple-100 dark:border-purple-900/30">
                <h4 className="text-xs font-medium text-muted-foreground mb-3 flex items-center gap-1">
                  <CreditCard className="h-3 w-3" />
                  Crédito / Banco
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  {/* Banco de Avaliação */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Banco</Label>
                    {isEditing ? (
                      <Input
                        value={editProcess.banco_avaliacao}
                        onChange={(e) => setEditProcess(prev => ({ ...prev, banco_avaliacao: e.target.value }))}
                        placeholder="BPI, CGD..."
                      />
                    ) : (
                      <p className="font-medium text-sm">{safeString(editProcess.banco_avaliacao) || '—'}</p>
                    )}
                  </div>

                  {/* Valor de Avaliação */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Avaliação</Label>
                    {isEditing ? (
                      <Input
                        type="number"
                        value={editProcess.valor_avaliacao}
                        onChange={(e) => setEditProcess(prev => ({ ...prev, valor_avaliacao: e.target.value }))}
                        placeholder="240000"
                      />
                    ) : (
                      <p className="font-medium text-sm flex items-center gap-1">
                        {editProcess.valor_avaliacao ? (
                          <>
                            <Euro className="h-3 w-3" />
                            {formatCurrency(editProcess.valor_avaliacao)}
                          </>
                        ) : '—'}
                      </p>
                    )}
                  </div>

                  {/* Spread */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Spread</Label>
                    {isEditing ? (
                      <Input
                        value={editProcess.spread}
                        onChange={(e) => setEditProcess(prev => ({ ...prev, spread: e.target.value }))}
                        placeholder="1.2%"
                      />
                    ) : (
                      <p className="font-medium text-sm">{safeString(editProcess.spread) || '—'}</p>
                    )}
                  </div>

                  {/* Taxa de Esforço */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Taxa Esforço</Label>
                    {isEditing ? (
                      <Input
                        value={editProcess.taxa_esforco}
                        onChange={(e) => setEditProcess(prev => ({ ...prev, taxa_esforco: e.target.value }))}
                        placeholder="32%"
                      />
                    ) : (
                      <p className="font-medium text-sm">{safeString(editProcess.taxa_esforco) || '—'}</p>
                    )}
                  </div>
                </div>
              </div>

              {/* ── Prioridade e Notas ──────────────────────────────── */}
              <div className="space-y-3">
                {isEditing && (
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Prioridade</Label>
                    <Select
                      value={editProcess.prioridade}
                      onValueChange={(v) => setEditProcess(prev => ({ ...prev, prioridade: v }))}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="alta">Alta</SelectItem>
                        <SelectItem value="media">Média</SelectItem>
                        <SelectItem value="baixa">Baixa</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}

                {/* Notas */}
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Notas</Label>
                  {isEditing ? (
                    <Textarea
                      value={editProcess.notes}
                      onChange={(e) => setEditProcess(prev => ({ ...prev, notes: e.target.value }))}
                      placeholder="Notas sobre o processo..."
                      rows={3}
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                      {safeString(editProcess.notes) || '—'}
                    </p>
                  )}
                </div>
              </div>

              {/* Atribuições */}
              {(process.consultor_name || process.mediador_name || process.assigned_consultor_name || process.assigned_intermediario_name) && (
                <div className="space-y-2">
                  <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                    <Users className="h-3 w-3" />
                    Atribuições
                  </h4>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    {(process.consultor_name || process.assigned_consultor_name) && (
                      <div>
                        <p className="text-muted-foreground text-xs">Consultor</p>
                        <p className="font-medium">{safeString(process.consultor_name || process.assigned_consultor_name)}</p>
                      </div>
                    )}
                    {(process.mediador_name || process.assigned_intermediario_name) && (
                      <div>
                        <p className="text-muted-foreground text-xs">Intermediário</p>
                        <p className="font-medium">{safeString(process.mediador_name || process.assigned_intermediario_name)}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Datas */}
              <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1">
                {process.created_at && (
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Criado: {new Date(process.created_at).toLocaleDateString('pt-PT')}
                  </span>
                )}
                {process.updated_at && (
                  <span>
                    Atualizado: {new Date(process.updated_at).toLocaleDateString('pt-PT')}
                  </span>
                )}
              </div>
            </div>
          </TabsContent>
        </Tabs>

        {/* ── Footer com Guardar (quando em edição) ──────────────── */}
        {isEditing && (
          <DialogFooter className="border-t pt-3">
            <Button variant="outline" onClick={handleCancelEdit} disabled={saving}>
              Cancelar
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className="bg-teal-600 hover:bg-teal-700 gap-1"
            >
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  A guardar...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4" />
                  Guardar Alterações
                </>
              )}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
});

ProcessDetailsModal.displayName = 'ProcessDetailsModal';

export default ProcessDetailsModal;
