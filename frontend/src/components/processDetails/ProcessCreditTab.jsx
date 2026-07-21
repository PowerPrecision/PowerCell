/**
 * ProcessCreditTab — extraído de ProcessDetails.js (tab credit).
 * Mantém o JSX original; estado e permissões vêm por props.
 */
import { Card, CardContent } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { Switch } from "../ui/switch";
import { AIBadge } from "../ui/AIBadge";
import { CreditCard, Building2, Shield } from "lucide-react";
import { formatDateForInput } from "../../pages/processDetails/processFormCleaners";
import { safeNumber } from "../dashboard/DashboardShared";

export default function ProcessCreditTab({
  realEstateData, creditData, setCreditData, editingCardId, canEditCredit, CardHeaderWithEdit, getFieldMetaFor, shouldCardBeCollapsed, collapsedCards,
}) {
  return (
    <>
                      <>
                      {/* Dados do Crédito */}
                      <Card className={`border-l-4 border-l-teal-500 ${editingCardId !== 'credit_dados' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Dados do Crédito" cardKey="credit_dados" icon={CreditCard} canEdit={canEditCredit} collapsible />
                          {!shouldCardBeCollapsed('credit_dados') && (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <div className="flex items-center gap-1">
                            <Label>Valor do Empréstimo (€)</Label>
                            <AIBadge {...(getFieldMetaFor("credit_data.requested_amount") || {})} />
                          </div>
                          <Input
                            type="number"
                            value={creditData.requested_amount || ""}
                            onChange={(e) => setCreditData({ ...creditData, requested_amount: parseFloat(e.target.value) || null })}
                            disabled={editingCardId !== 'credit_dados' || !canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Prazo (anos)</Label>
                          <Input
                            type="number"
                            value={creditData.loan_term_years || ""}
                            onChange={(e) => setCreditData({ ...creditData, loan_term_years: parseInt(e.target.value) || null })}
                            disabled={editingCardId !== 'credit_dados' || !canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <div className="flex items-center gap-1">
                            <Label>Taxa de Juro (%)</Label>
                            <AIBadge {...(getFieldMetaFor("credit_data.interest_rate") || {})} />
                          </div>
                          <Input
                            type="number"
                            step="0.01"
                            value={creditData.interest_rate || ""}
                            onChange={(e) => setCreditData({ ...creditData, interest_rate: parseFloat(e.target.value) || null })}
                            disabled={editingCardId !== 'credit_dados' || !canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <div className="flex items-center gap-1">
                            <Label>Prestação Mensal (€)</Label>
                            <AIBadge {...(getFieldMetaFor("credit_data.monthly_payment") || {})} />
                          </div>
                          <Input
                            type="number"
                            value={creditData.monthly_payment || ""}
                            onChange={(e) => setCreditData({ ...creditData, monthly_payment: parseFloat(e.target.value) || null })}
                            disabled={editingCardId !== 'credit_dados' || !canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Banco</Label>
                          <Input
                            value={creditData.bank_name || ""}
                            onChange={(e) => setCreditData({ ...creditData, bank_name: e.target.value })}
                            disabled={editingCardId !== 'credit_dados' || !canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Data de Aprovação</Label>
                          <Input
                            type="date"
                            value={formatDateForInput(creditData.bank_approval_date)}
                            onChange={(e) => setCreditData({ ...creditData, bank_approval_date: e.target.value })}
                            disabled={editingCardId !== 'credit_dados' || !canEditCredit}
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label>Notas da Aprovação</Label>
                          <Textarea
                            value={creditData.bank_approval_notes || ""}
                            onChange={(e) => setCreditData({ ...creditData, bank_approval_notes: e.target.value })}
                            disabled={editingCardId !== 'credit_dados' || !canEditCredit}
                          />
                        </div>
                      </div>
                          )}
                        </CardContent>
                      </Card>

                      {/* ====== Avaliação Bancária (Fase 3) ====== */}
                      <Card className={`border-l-4 border-l-emerald-500 ${editingCardId !== 'credit_avaliacao' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Avaliação Bancária" cardKey="credit_avaliacao" icon={Building2} canEdit={canEditCredit} />
                          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Valor da Avaliação (€)</Label>
                              <Input
                                type="number"
                                value={creditData.valuation_value || ""}
                                onChange={(e) => setCreditData({ ...creditData, valuation_value: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'credit_avaliacao' || !canEditCredit}
                                className="h-9"
                                placeholder="0.00"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Data da Avaliação</Label>
                              <Input
                                type="date"
                                value={creditData.valuation_date || ""}
                                onChange={(e) => setCreditData({ ...creditData, valuation_date: e.target.value })}
                                disabled={editingCardId !== 'credit_avaliacao' || !canEditCredit}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Banco Avaliador</Label>
                              <Input
                                value={creditData.valuation_bank || ""}
                                onChange={(e) => setCreditData({ ...creditData, valuation_bank: e.target.value })}
                                disabled={editingCardId !== 'credit_avaliacao' || !canEditCredit}
                                className="h-9"
                                placeholder="Ex: CGD, Millennium BCP"
                              />
                            </div>
                            <div className="space-y-1 sm:col-span-2 md:col-span-3">
                              <Label className="text-xs text-muted-foreground">Notas da Avaliação</Label>
                              <Textarea
                                value={creditData.valuation_notes || ""}
                                onChange={(e) => setCreditData({ ...creditData, valuation_notes: e.target.value })}
                                disabled={editingCardId !== 'credit_avaliacao' || !canEditCredit}
                                rows={2}
                                placeholder="Observações sobre a avaliação bancária"
                              />
                            </div>
                          </div>
                          {/* Alerta: Avaliação abaixo do valor de compra */}
                          {creditData.valuation_value && realEstateData.valor_imovel && creditData.valuation_value < realEstateData.valor_imovel && (
                            <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2">
                              <AlertTriangle className="h-4 w-4 text-red-500 shrink-0" />
                              <p className="text-xs text-red-700 dark:text-red-300">
                                Valor da avaliação ({safeNumber(creditData.valuation_value).toLocaleString('pt-PT')}€) é inferior ao valor do imóvel ({safeNumber(realEstateData.valor_imovel).toLocaleString('pt-PT')}€). Diferença de {safeNumber(Math.abs(realEstateData.valor_imovel - creditData.valuation_value)).toLocaleString('pt-PT')}€.
                              </p>
                            </div>
                          )}
                        </CardContent>
                      </Card>

                      {/* ====== Compliance & Perfil de Risco (Pacote AC) ====== */}
                      {/* Cartão minimizado por defeito (collapsedCards inicial = { credit_compliance: true }).
                          Campos: admission_year (Ano de admissão), is_ppe (PPE), is_fpe (FPE),
                          credit_incidents (texto livre). Persistidos em credit_data via cleanCreditDataForSubmit. */}
                      <Card className={`border-l-4 border-l-rose-500 ${editingCardId !== 'credit_compliance' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Compliance & Perfil de Risco" cardKey="credit_compliance" icon={Shield} canEdit={canEditCredit} collapsible />
                          {!shouldCardBeCollapsed('credit_compliance') && (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Ano de Admissão */}
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Ano de Admissão (no emprego atual)</Label>
                              <Input
                                type="number"
                                min="1950"
                                max="2099"
                                value={creditData.admission_year || ""}
                                onChange={(e) => setCreditData({ ...creditData, admission_year: parseInt(e.target.value) || null })}
                                disabled={editingCardId !== 'credit_compliance' || !canEditCredit}
                                className="h-9"
                                placeholder="Ex: 2020"
                              />
                            </div>

                            {/* PPE — Pessoa Politicamente Exposta */}
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Pessoa Politicamente Exposta (PPE)</Label>
                              <div className="flex items-center gap-2 h-9">
                                <Switch
                                  checked={creditData.is_ppe === true}
                                  onCheckedChange={(checked) => setCreditData({ ...creditData, is_ppe: checked })}
                                  disabled={editingCardId !== 'credit_compliance' || !canEditCredit}
                                />
                                <span className="text-xs text-muted-foreground">
                                  {creditData.is_ppe === true ? "Sim — sujeito a compliance reforçado" : "Não"}
                                </span>
                              </div>
                            </div>

                            {/* FPE — Pessoa Fiscalmente Exposta */}
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Pessoa Fiscalmente Exposta (FPE)</Label>
                              <div className="flex items-center gap-2 h-9">
                                <Switch
                                  checked={creditData.is_fpe === true}
                                  onCheckedChange={(checked) => setCreditData({ ...creditData, is_fpe: checked })}
                                  disabled={editingCardId !== 'credit_compliance' || !canEditCredit}
                                />
                                <span className="text-xs text-muted-foreground">
                                  {creditData.is_fpe === true ? "Sim — incumprimento fiscal registado" : "Não"}
                                </span>
                              </div>
                            </div>

                            {/* Incidentes de Crédito (texto livre) */}
                            <div className="space-y-1 md:col-span-2">
                              <Label className="text-xs text-muted-foreground">Incidentes de Crédito</Label>
                              <Textarea
                                value={creditData.credit_incidents || ""}
                                onChange={(e) => setCreditData({ ...creditData, credit_incidents: e.target.value })}
                                disabled={editingCardId !== 'credit_compliance' || !canEditCredit}
                                rows={3}
                                placeholder="Registos de incidentes de crédito (ex.: contas encerradas, incumprimentos, execuções fiscais). Deixar vazio se não houver."
                              />
                            </div>

                            {/* Aviso se PPE ou FPE ativos */}
                            {(creditData.is_ppe === true || creditData.is_fpe === true) && (
                              <div className="md:col-span-2 p-3 bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-lg flex items-start gap-2">
                                <AlertTriangle className="h-4 w-4 text-rose-500 shrink-0 mt-0.5" />
                                <p className="text-xs text-rose-700 dark:text-rose-300">
                                  {creditData.is_ppe === true && creditData.is_fpe === true
                                    ? "Cliente identificado como PPE e FPE. Sujeito a compliance regulamentar reforçado (Banco de Portugal). Verifique procedimentos KYC/AML aplicáveis."
                                    : creditData.is_ppe === true
                                    ? "Cliente identificado como Pessoa Politicamente Exposta (PPE). Sujeito a procedimentos KYC/AML reforçados."
                                    : "Cliente identificado como Pessoa Fiscalmente Exposta (FPE). Verificar impacto na análise de risco de crédito."}
                                </p>
                              </div>
                            )}
                          </div>
                          )}
                        </CardContent>
                      </Card>
                      </>
    </>
  );
}
