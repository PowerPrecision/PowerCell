/**
 * FinancialTab — extraído de ProcessDetails.js (tab financial).
 * Mantém o JSX original; estado e permissões vêm por props.
 */
import { Card, CardContent } from "../../ui/card";
import { Input } from "../../ui/input";
import { Label } from "../../ui/label";
import { Badge } from "../../ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../ui/select";
import { AIBadge } from "../../ui/AIBadge";
import AutoDSTIBadge from "../../AutoDSTIBadge";
import {
  Briefcase, CreditCard, Database, User, Eye, EyeOff, Pencil, Plus, AlertCircle,
} from "lucide-react";
import { BANK_LIST, getBankColor } from "../../../pages/processDetails/processDetailsConstants";
import { safeString } from "../../../utils/safeString";

export default function FinancialTab({
  titular2Data, setTitular2Data, financialData, setFinancialData, process, editingCardId, editingCreditField, setEditingCreditField, showPortalSenha, setShowPortalSenha, showSegSocialSenha, setShowSegSocialSenha, canEditFinancial, CardHeaderWithEdit, getFieldMetaFor, token, id, shouldCardBeCollapsed,
}) {
  return (
    <>
                    <div className="space-y-4">
                      {/* DSTI Automático */}
                      <AutoDSTIBadge processId={id} token={token} compact={false} showDetails={true} />
                      {/* Rendimentos */}
                      <Card className={`border-l-4 border-l-green-500 ${editingCardId !== 'financial_rendimentos' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Rendimentos" cardKey="financial_rendimentos" icon={Briefcase} canEdit={canEditFinancial} collapsible />
                          {!shouldCardBeCollapsed('financial_rendimentos') && (
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <div className="flex items-center gap-1">
                                <Label className="text-xs text-muted-foreground">Rendimento Mensal (€)</Label>
                                <AIBadge {...(getFieldMetaFor("financial_data.monthly_income") || {})} />
                              </div>
                              <Input
                                type="number"
                                value={financialData.monthly_income || financialData.salario_liquido || ""}
                                onChange={(e) => setFinancialData({ ...financialData, monthly_income: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_rendimentos' || !canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center gap-1">
                                <Label className="text-xs text-muted-foreground">Rendimento Bruto (€)</Label>
                                <AIBadge {...(getFieldMetaFor("financial_data.rendimento_bruto") || {})} />
                              </div>
                              <Input
                                type="number"
                                value={financialData.rendimento_bruto || financialData.salario_bruto || ""}
                                onChange={(e) => setFinancialData({ ...financialData, rendimento_bruto: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_rendimentos' || !canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Rendimento Anual (€)</Label>
                              <Input
                                type="number"
                                value={financialData.rendimento_anual || ""}
                                onChange={(e) => setFinancialData({ ...financialData, rendimento_anual: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_rendimentos' || !canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Capital Próprio (€)</Label>
                              <Input
                                type="number"
                                value={financialData.capital_proprio || financialData.other_income || ""}
                                onChange={(e) => setFinancialData({ ...financialData, capital_proprio: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_rendimentos' || !canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center gap-1">
                                <Label className="text-xs text-muted-foreground">Valor a Financiar</Label>
                                <AIBadge {...(getFieldMetaFor("financial_data.valor_financiado") || {})} />
                              </div>
                              <Input
                                value={financialData.valor_financiado || ""}
                                onChange={(e) => setFinancialData({ ...financialData, valor_financiado: e.target.value })}
                                disabled={editingCardId !== 'financial_rendimentos' || !canEditFinancial}
                                className="h-9"
                                placeholder="Ex: 200.000€ ou 80%"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Renda Habitação Atual (€)</Label>
                              <Input
                                type="number"
                                value={financialData.renda_habitacao_atual || ""}
                                onChange={(e) => setFinancialData({ ...financialData, renda_habitacao_atual: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_rendimentos' || !canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Rendimento Co-Titular (€)</Label>
                              <Input
                                type="number"
                                value={financialData.rendimento_co_titular || ""}
                                onChange={(e) => setFinancialData({ ...financialData, rendimento_co_titular: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_rendimentos' || !canEditFinancial}
                                className="h-9"
                                placeholder="Rendimento do 2º titular"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nº de Dependentes</Label>
                              <Input
                                type="number"
                                min="0"
                                value={financialData.nr_dependentes || financialData.number_of_dependents || ""}
                                onChange={(e) => setFinancialData({ ...financialData, nr_dependentes: parseInt(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_rendimentos' || !canEditFinancial}
                                className="h-9"
                                placeholder="0"
                              />
                            </div>
                          </div>
                          )}
                        </CardContent>
                      </Card>
                      
                      {/* Situação Financeira */}
                      <Card className={`border-l-4 border-l-blue-500 ${editingCardId !== 'financial_situacao' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Situação Financeira" cardKey="financial_situacao" icon={CreditCard} canEdit={canEditFinancial} />
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Contrato Efetivo?</Label>
                              <Select
                                value={financialData.efetivo || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, efetivo: value })}
                                disabled={editingCardId !== 'financial_situacao' || !canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Precisa Vender Casa?</Label>
                              <Select
                                value={financialData.precisa_vender_casa || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, precisa_vender_casa: value })}
                                disabled={editingCardId !== 'financial_situacao' || !canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Tem Fiador?</Label>
                              <Select
                                value={financialData.fiador || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, fiador: value })}
                                disabled={editingCardId !== 'financial_situacao' || !canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Créditos Existentes (€)</Label>
                              <Input
                                type="number"
                                value={financialData.creditos_existentes || ""}
                                onChange={(e) => setFinancialData({ ...financialData, creditos_existentes: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_situacao' || !canEditFinancial}
                                className="h-9"
                                placeholder="Valor total em dívida"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Prestação Créditos Mensal (€)</Label>
                              <Input
                                type="number"
                                value={financialData.prestacao_creditos_mensal || ""}
                                onChange={(e) => setFinancialData({ ...financialData, prestacao_creditos_mensal: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_situacao' || !canEditFinancial}
                                className="h-9"
                                placeholder="Total prestações mensais"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Acesso Portais Oficiais?</Label>
                              <Select
                                value={financialData.acesso_portal_financas || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, acesso_portal_financas: value })}
                                disabled={editingCardId !== 'financial_situacao' || !canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="portal_financas">Portal das Finanças</SelectItem>
                                  <SelectItem value="seguranca_social">Segurança Social Direta</SelectItem>
                                  <SelectItem value="ambos">Ambos</SelectItem>
                                  <SelectItem value="nenhuma">Nenhuma</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Chave Móvel Digital?</Label>
                              <Select
                                value={financialData.chave_movel_digital || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, chave_movel_digital: value })}
                                disabled={editingCardId !== 'financial_situacao' || !canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                          </div>
                        </CardContent>
                      </Card>

                      {/* Credenciais de Portais Oficiais */}
                      <Card className={`border-l-4 border-l-orange-500 ${editingCardId !== 'financial_credenciais' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Credenciais de Portais Oficiais" cardKey="financial_credenciais" icon={Database} canEdit={canEditFinancial} collapsible />
                          {!shouldCardBeCollapsed('financial_credenciais') && (
                          <>
                          <p className="text-xs text-muted-foreground mb-3">
                            Preencha as credenciais de acesso aos portais oficiais para facilitar a gestão do processo.
                          </p>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            {/* Portal das Finanças */}
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Portal Finanças - Utilizador</Label>
                              <Input
                                value={financialData.portal_financas_utilizador || ""}
                                onChange={(e) => setFinancialData({ ...financialData, portal_financas_utilizador: e.target.value })}
                                disabled={editingCardId !== 'financial_credenciais' || !canEditFinancial}
                                className="h-9"
                                placeholder="NIF ou email"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Portal Finanças - Senha</Label>
                              <div className="relative">
                                <Input
                                  type={showPortalSenha ? "text" : "password"}
                                  value={financialData.portal_financas_senha || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, portal_financas_senha: e.target.value })}
                                  disabled={editingCardId !== 'financial_credenciais' || !canEditFinancial}
                                  className="h-9 pr-9"
                                  placeholder="Senha de acesso"
                                />
                                <button
                                  type="button"
                                  onClick={() => setShowPortalSenha(!showPortalSenha)}
                                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground min-h-[44px] min-w-[44px] flex items-center justify-center"
                                  tabIndex={-1}
                                >
                                  {showPortalSenha ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                              </div>
                            </div>
                            {/* Segurança Social Direta */}
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Seg. Social - Utilizador</Label>
                              <Input
                                value={financialData.seg_social_utilizador || ""}
                                onChange={(e) => setFinancialData({ ...financialData, seg_social_utilizador: e.target.value })}
                                disabled={editingCardId !== 'financial_credenciais' || !canEditFinancial}
                                className="h-9"
                                placeholder="NISS ou email"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Seg. Social - Senha</Label>
                              <div className="relative">
                                <Input
                                  type={showSegSocialSenha ? "text" : "password"}
                                  value={financialData.seg_social_senha || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, seg_social_senha: e.target.value })}
                                  disabled={editingCardId !== 'financial_credenciais' || !canEditFinancial}
                                  className="h-9 pr-9"
                                  placeholder="Senha de acesso"
                                />
                                <button
                                  type="button"
                                  onClick={() => setShowSegSocialSenha(!showSegSocialSenha)}
                                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground min-h-[44px] min-w-[44px] flex items-center justify-center"
                                  tabIndex={-1}
                                >
                                  {showSegSocialSenha ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                              </div>
                            </div>
                          </div>
                          </>
                          )}
                        </CardContent>
                      </Card>

                      {/* Credenciais de Portais Oficiais - 2º Proponente */}
                      {(process?.titular2_data || Object.keys(titular2Data).length > 0) && (
                        <Card className={`border-l-4 border-l-orange-300 ${editingCardId !== 'financial_credenciais_2' ? 'read-only-card' : ''}`}>
                          <CardContent className="pt-4">
                            <div className="flex items-center gap-2">
                              <CardHeaderWithEdit title="Credenciais de Portais Oficiais" cardKey="financial_credenciais_2" icon={Database} canEdit={canEditFinancial} collapsible />
                              <Badge variant="outline" className="text-xs bg-orange-50 text-orange-600 border-orange-200">2º Proponente</Badge>
                            </div>
                            {!shouldCardBeCollapsed('financial_credenciais_2') && (
                            <>
                            <p className="text-xs text-muted-foreground mb-3">
                              Credenciais de acesso aos portais oficiais do segundo proponente/titular.
                            </p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              {/* Portal das Finanças */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Finanças - Utilizador</Label>
                                <Input
                                  value={titular2Data.portal_financas_utilizador || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, portal_financas_utilizador: e.target.value })}
                                  disabled={editingCardId !== 'financial_credenciais_2' || !canEditFinancial}
                                  className="h-9"
                                  placeholder="NIF ou email"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Finanças - Senha</Label>
                                <Input
                                  type="password"
                                  value={titular2Data.portal_financas_senha || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, portal_financas_senha: e.target.value })}
                                  disabled={editingCardId !== 'financial_credenciais_2' || !canEditFinancial}
                                  className="h-9"
                                  placeholder="Senha de acesso"
                                />
                              </div>
                              {/* Segurança Social Direta */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Seg. Social - Utilizador</Label>
                                <Input
                                  value={titular2Data.seg_social_utilizador || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, seg_social_utilizador: e.target.value })}
                                  disabled={editingCardId !== 'financial_credenciais_2' || !canEditFinancial}
                                  className="h-9"
                                  placeholder="NISS ou email"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Seg. Social - Senha</Label>
                                <Input
                                  type="password"
                                  value={titular2Data.seg_social_senha || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, seg_social_senha: e.target.value })}
                                  disabled={editingCardId !== 'financial_credenciais_2' || !canEditFinancial}
                                  className="h-9"
                                  placeholder="Senha de acesso"
                                />
                              </div>
                            </div>
                            </>
                            )}
                          </CardContent>
                        </Card>
                      )}

                      {/* Créditos/Bancos */}
                      <Card className="border-l-4 border-l-red-500">
                        <CardContent className="pt-4">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="font-semibold text-sm flex items-center gap-2">
                              <AlertCircle className="h-4 w-4 text-red-500" />
                              Créditos Ativos
                            </h4>
                            {canEditFinancial && editingCreditField !== 'creditos' && (
                              <button
                                type="button"
                                onClick={() => setEditingCreditField('creditos')}
                                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                              >
                                <Pencil className="h-3 w-3" />
                                Editar
                              </button>
                            )}
                            {canEditFinancial && editingCreditField === 'creditos' && (
                              <button
                                type="button"
                                onClick={() => setEditingCreditField(null)}
                                className="text-xs text-green-600 hover:text-green-700 flex items-center gap-1 transition-colors"
                              >
                                <CheckCircle className="h-3 w-3" />
                                Concluído
                              </button>
                            )}
                          </div>
                          {editingCreditField === 'creditos' && canEditFinancial ? (
                            <div className="space-y-2">
                              {(financialData.bancos_creditos || []).map((item, idx) => {
                                const banco = typeof item === 'object' ? item.banco : item;
                                const valor = typeof item === 'object' ? item.valor : null;
                                return (
                                  <div key={idx} className="flex items-center gap-2">
                                    <select
                                      value={banco || ''}
                                      onChange={(e) => {
                                        const updated = [...(financialData.bancos_creditos || [])];
                                        updated[idx] = { ...updated[idx], banco: e.target.value };
                                        setFinancialData({ ...financialData, bancos_creditos: updated });
                                      }}
                                      className="text-xs border rounded px-2 py-1 bg-background"
                                    >
                                      <option value="">Banco...</option>
                                      {BANK_LIST.map((b) => (
                                        <option key={b} value={b}>{b}</option>
                                      ))}
                                    </select>
                                    <input
                                      type="number"
                                      placeholder="Valor"
                                      value={valor || ''}
                                      onChange={(e) => {
                                        const updated = [...(financialData.bancos_creditos || [])];
                                        updated[idx] = { ...updated[idx], valor: parseFloat(e.target.value) || 0 };
                                        setFinancialData({ ...financialData, bancos_creditos: updated });
                                      }}
                                      className="text-xs border rounded px-2 py-1 w-28 bg-background"
                                    />
                                    <button
                                      type="button"
                                      onClick={() => {
                                        const updated = (financialData.bancos_creditos || []).filter((_, i) => i !== idx);
                                        setFinancialData({ ...financialData, bancos_creditos: updated });
                                      }}
                                      className="p-1 hover:bg-red-100 rounded text-red-500 transition-colors"
                                    >
                                      <Trash2 className="h-3.5 w-3.5" />
                                    </button>
                                  </div>
                                );
                              })}
                              <button
                                type="button"
                                onClick={() => {
                                  const updated = [...(financialData.bancos_creditos || []), { banco: '', valor: 0 }];
                                  setFinancialData({ ...financialData, bancos_creditos: updated });
                                }}
                                className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700 font-medium mt-1"
                              >
                                <Plus className="h-3.5 w-3.5" />
                                Adicionar crédito
                              </button>
                            </div>
                          ) : (
                            <div>
                              {(() => {
                                const total = (financialData.bancos_creditos || []).reduce((sum, item) => {
                                  if (typeof item === 'object' && item.valor) return sum + item.valor;
                                  return sum;
                                }, 0);
                                if (total > 0) {
                                  return (
                                    <p className="text-xs text-muted-foreground mb-2">
                                      Total: <span className="font-semibold text-foreground">{total.toLocaleString('pt-PT', { style: 'currency', currency: 'EUR' })}</span>
                                    </p>
                                  );
                                }
                                return null;
                              })()}
                              <div className="space-y-2">
                                {Array.isArray(financialData.bancos_creditos) && financialData.bancos_creditos.length > 0 ? (
                                  financialData.bancos_creditos.map((item, idx) => {
                                    const banco = typeof item === 'object' ? safeString(item.banco) : safeString(item);
                                    const valor = typeof item === 'object' ? item.valor : null;
                                    return (
                                      <div key={idx} className="flex items-center gap-2">
                                        <Badge className={getBankColor(banco)}>{safeString(banco)}</Badge>
                                        {valor != null && valor > 0 && (
                                          <span className="text-xs font-medium text-muted-foreground">
                                            {valor.toLocaleString('pt-PT', { style: 'currency', currency: 'EUR' })}
                                          </span>
                                        )}
                                      </div>
                                    );
                                  })
                                ) : (
                                  <span className="text-xs text-muted-foreground">Nenhum crédito registado</span>
                                )}
                              </div>
                            </div>
                          )}
                        </CardContent>
                      </Card>

                      {/* Contas de Crédito Abertas */}
                      <Card className="border-l-4 border-l-amber-500">
                        <CardContent className="pt-4">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="font-semibold text-sm flex items-center gap-2">
                              <CreditCard className="h-4 w-4 text-amber-500" />
                              Contas de Crédito Abertas
                            </h4>
                            {canEditFinancial && editingCreditField !== 'contas' && (
                              <button
                                type="button"
                                onClick={() => setEditingCreditField('contas')}
                                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                              >
                                <Pencil className="h-3 w-3" />
                                Editar
                              </button>
                            )}
                            {canEditFinancial && editingCreditField === 'contas' && (
                              <button
                                type="button"
                                onClick={() => setEditingCreditField(null)}
                                className="text-xs text-green-600 hover:text-green-700 flex items-center gap-1 transition-colors"
                              >
                                <CheckCircle className="h-3 w-3" />
                                Concluído
                              </button>
                            )}
                          </div>
                          {editingCreditField === 'contas' && canEditFinancial ? (
                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => setFinancialData({ ...financialData, tem_creditos_activos: [] })}
                                className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                                  (financialData.tem_creditos_activos || []).length === 0
                                    ? 'ring-2 ring-offset-1 ring-amber-400 scale-105 bg-slate-700 text-white border-slate-700'
                                    : 'opacity-50 hover:opacity-80 bg-transparent text-slate-600 border-slate-400'
                                }`}
                              >
                                {(financialData.tem_creditos_activos || []).length === 0 && <span className="mr-1">✓</span>}
                                Nenhuma
                              </button>
                              {BANK_LIST.map((banco) => {
                                const selected = (financialData.tem_creditos_activos || []).includes(banco);
                                return (
                                  <button
                                    key={`contas-${banco}`}
                                    type="button"
                                    onClick={() => {
                                      const current = financialData.tem_creditos_activos || [];
                                      setFinancialData({
                                        ...financialData,
                                        tem_creditos_activos: current.includes(banco)
                                          ? current.filter(b => b !== banco)
                                          : [...current, banco]
                                      });
                                    }}
                                    className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${selected ? 'ring-2 ring-offset-1 ring-amber-400 scale-105' : 'opacity-50 hover:opacity-80'} ${getBankColor(banco)}`}
                                  >
                                    {selected && <span className="mr-1">✓</span>}
                                    {banco}
                                  </button>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="flex flex-wrap gap-2">
                              {Array.isArray(financialData?.tem_creditos_activos) && financialData.tem_creditos_activos.length > 0 ? (
                                financialData.tem_creditos_activos.map((banco, idx) => (
                                  <Badge key={idx} className={getBankColor(banco)}>{safeString(banco)}</Badge>
                                ))
                              ) : (
                                <span className="text-xs text-muted-foreground">Nenhuma conta registada</span>
                              )}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                      
                      {/* Simulações de Crédito */}
                      <Card className="border-l-4 border-l-blue-500">
                        <CardContent className="pt-4">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="font-semibold text-sm flex items-center gap-2">
                              <CreditCard className="h-4 w-4 text-blue-500" />
                              Simulações de Crédito Efetuadas
                            </h4>
                            {canEditFinancial && editingCreditField !== 'simulacoes' && (
                              <button
                                type="button"
                                onClick={() => setEditingCreditField('simulacoes')}
                                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                              >
                                <Pencil className="h-3 w-3" />
                                Editar
                              </button>
                            )}
                            {canEditFinancial && editingCreditField === 'simulacoes' && (
                              <button
                                type="button"
                                onClick={() => setEditingCreditField(null)}
                                className="text-xs text-green-600 hover:text-green-700 flex items-center gap-1 transition-colors"
                              >
                                <CheckCircle className="h-3 w-3" />
                                Concluído
                              </button>
                            )}
                          </div>
                          {editingCreditField === 'simulacoes' && canEditFinancial ? (
                            <div className="flex flex-wrap gap-2">
                              {BANK_LIST.map((banco) => {
                                const selected = (financialData.bancos_simulacoes || []).includes(banco);
                                return (
                                  <button
                                    key={`sim-${banco}`}
                                    type="button"
                                    onClick={() => {
                                      const current = financialData.bancos_simulacoes || [];
                                      setFinancialData({
                                        ...financialData,
                                        bancos_simulacoes: current.includes(banco)
                                          ? current.filter(b => b !== banco)
                                          : [...current, banco]
                                      });
                                    }}
                                    className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${selected ? 'ring-2 ring-offset-1 ring-blue-400 scale-105' : 'opacity-50 hover:opacity-80'} ${getBankColor(banco)}`}
                                  >
                                    {selected && <span className="mr-1">✓</span>}
                                    {banco}
                                  </button>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="flex flex-wrap gap-2">
                              {Array.isArray(financialData.bancos_simulacoes) && financialData.bancos_simulacoes.length > 0 ? (
                                financialData.bancos_simulacoes.map((banco, idx) => (
                                  <Badge key={idx} variant="outline" className="border-blue-300 text-blue-700">{safeString(banco)}</Badge>
                                ))
                              ) : (
                                <span className="text-xs text-muted-foreground">Nenhuma simulação registada</span>
                              )}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                      
                      {/* Tempo Restante do Crédito (Refinanciamento) */}
                      {financialData?.tempo_restante_credito && (
                        <Card className="border-l-4 border-l-amber-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <Clock className="h-4 w-4 text-amber-500" />
                              Tempo Restante do Crédito Atual
                            </h4>
                            <p className="text-sm">
                              {financialData.tempo_restante_credito === "menos_1_ano" ? "Menos de 1 ano" :
                               financialData.tempo_restante_credito === "1_5_anos" ? "1 a 5 anos" :
                               financialData.tempo_restante_credito === "5_10_anos" ? "5 a 10 anos" :
                               financialData.tempo_restante_credito === "10_15_anos" ? "10 a 15 anos" :
                               financialData.tempo_restante_credito === "15_20_anos" ? "15 a 20 anos" :
                               financialData.tempo_restante_credito === "mais_20_anos" ? "Mais de 20 anos" : 
                               financialData.tempo_restante_credito}
                            </p>
                          </CardContent>
                        </Card>
                      )}
                      
                      {/* Emprego */}
                      <Card className={`border-l-4 border-l-purple-500 ${editingCardId !== 'financial_profissional' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Situação Profissional" cardKey="financial_profissional" icon={User} canEdit={canEditFinancial} />
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Tipo de Emprego</Label>
                              <Select
                                value={financialData.employment_type || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, employment_type: value })}
                                disabled={editingCardId !== 'financial_profissional' || !canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="efetivo">Contrato Efetivo</SelectItem>
                                  <SelectItem value="termo_certo">Termo Certo</SelectItem>
                                  <SelectItem value="termo_incerto">Termo Incerto</SelectItem>
                                  <SelectItem value="independente">Trabalhador Independente</SelectItem>
                                  <SelectItem value="empresario">Empresário</SelectItem>
                                  <SelectItem value="reformado">Reformado</SelectItem>
                                  <SelectItem value="desempregado">Desempregado</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Trabalha no Estrangeiro?</Label>
                              <Select
                                value={financialData.trabalha_estrangeiro || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, trabalha_estrangeiro: value })}
                                disabled={editingCardId !== 'financial_profissional' || !canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Tempo de Emprego</Label>
                              <Input
                                value={financialData.employment_duration || ""}
                                onChange={(e) => setFinancialData({ ...financialData, employment_duration: e.target.value })}
                                disabled={editingCardId !== 'financial_profissional' || !canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Entidade Empregadora</Label>
                              <Input
                                value={financialData.employer_name || ""}
                                onChange={(e) => setFinancialData({ ...financialData, employer_name: e.target.value })}
                                disabled={editingCardId !== 'financial_profissional' || !canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">NIF da Entidade Empregadora</Label>
                              <Input
                                value={financialData.employer_nif || ""}
                                onChange={(e) => {
                                  const val = e.target.value.replace(/\D/g, '').slice(0, 9);
                                  setFinancialData({ ...financialData, employer_nif: val });
                                }}
                                disabled={editingCardId !== 'financial_profissional' || !canEditFinancial}
                                className="h-9"
                                placeholder="NIF da empresa"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Categoria Profissional</Label>
                              <Input
                                value={financialData.categoria_profissional || ""}
                                onChange={(e) => setFinancialData({ ...financialData, categoria_profissional: e.target.value })}
                                disabled={editingCardId !== 'financial_profissional' || !canEditFinancial}
                                className="h-9"
                                placeholder="Ex: Técnico superior, Operário..."
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Subsídio Alimentação (€)</Label>
                              <Input
                                type="number"
                                value={financialData.subsidiario_alimentacao || ""}
                                onChange={(e) => setFinancialData({ ...financialData, subsidiario_alimentacao: parseFloat(e.target.value) || null })}
                                disabled={editingCardId !== 'financial_profissional' || !canEditFinancial}
                                className="h-9"
                                placeholder="0.00"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Data de Referência (Recibo)</Label>
                              <Input
                                type="month"
                                value={financialData.data_referencia || ""}
                                onChange={(e) => setFinancialData({ ...financialData, data_referencia: e.target.value })}
                                disabled={editingCardId !== 'financial_profissional' || !canEditFinancial}
                                className="h-9"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </div>
    </>
  );
}
