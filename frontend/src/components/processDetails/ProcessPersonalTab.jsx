/**
 * ProcessPersonalTab — extraído de ProcessDetails.js (tab personal).
 * Mantém o JSX original; estado e permissões vêm por props.
 */
import { Card, CardContent } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Badge } from "../ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { AIBadge } from "../ui/AIBadge";
import SecondTitularCard from "../SecondTitularCard";
import { User, Phone, CreditCard, Users, MapPin } from "lucide-react";
import { formatDateForInput } from "../../pages/processDetails/processFormCleaners";
import { validateNIF } from "../../utils/validateNIF";
import { safeString } from "../../utils/safeString";
import { safeNumber } from "../dashboard/DashboardShared";

export default function ProcessPersonalTab({
  personalData, setPersonalData, process, setProcess, clientId, nifError, setNifError, editingCardId, canEditPersonal, CardHeaderWithEdit, getConfidenceIndicator, getFieldMetaFor, fetchData, financialData,
}) {
  return (
    <>
                    <div className="space-y-4">
                      {/* Indicador visual: estes dados pertencem ao Cliente */}
                      {clientId && (
                        <div className="flex items-center gap-2 p-2.5 bg-teal-50 dark:bg-teal-950/20 border border-teal-200 dark:border-teal-800 rounded-lg">
                          <User className="h-4 w-4 text-teal-600 shrink-0" />
                          <p className="text-xs text-teal-700 dark:text-teal-300">
                            Estes dados pertencem à <strong>ficha do Cliente</strong> e são guardados em <code className="font-mono text-[10px] bg-teal-100 dark:bg-teal-900/40 px-1 rounded">/clients/{clientId.slice(0,8)}…</code>
                          </p>
                        </div>
                      )}
                      {/* Contactos */}
                      <Card className={`border-l-4 border-l-blue-500 ${editingCardId !== 'personal_contactos' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Contactos" cardKey="personal_contactos" icon={Phone} canEdit={canEditPersonal} />
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Email</Label>
                              <Input
                                type="email"
                                value={process?.client_email || ""}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setProcess({ ...process, client_email: val });
                                  setPersonalData(prev => ({ ...prev, email: val }));
                                }}
                                disabled={editingCardId !== 'personal_contactos' || !canEditPersonal}
                                placeholder="email@exemplo.com"
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Telefone</Label>
                              <Input
                                value={process?.client_phone || ""}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setProcess({ ...process, client_phone: val });
                                  setPersonalData(prev => ({ ...prev, telefone: val }));
                                }}
                                disabled={editingCardId !== 'personal_contactos' || !canEditPersonal}
                                placeholder="+351 000 000 000"
                                className="h-9"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* Identificação */}
                      <Card className={`border-l-4 border-l-amber-500 ${editingCardId !== 'personal_identificacao' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Identificação" cardKey="personal_identificacao" icon={CreditCard} canEdit={canEditPersonal} />
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1 md:col-span-2">
                              <Label className="text-xs text-muted-foreground">Nome Completo</Label>
                              <Input
                                value={personalData.nome_completo || process?.client_name || ""}
                                onChange={(e) => setPersonalData({ ...personalData, nome_completo: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className="h-9"
                                placeholder="Nome completo do cliente (pode ser diferente do nome do processo)"
                              />
                              <p className="text-[10px] text-muted-foreground">
                                O nome completo pode ser diferente do nome do processo
                              </p>
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-1">
                                  <Label className="text-xs text-muted-foreground">NIF</Label>
                                  <AIBadge {...(getFieldMetaFor("dados_pessoais.nif") || {})} />
                                </div>
                                {getConfidenceIndicator("nif") && (
                                  <Badge className={`text-[9px] px-1.5 py-0 ${getConfidenceIndicator("nif").badge}`}>
                                    IA {getConfidenceIndicator("nif").label}
                                  </Badge>
                                )}
                              </div>
                              <Input
                                value={personalData.nif || ""}
                                onChange={(e) => {
                                  const value = e.target.value;
                                  setPersonalData({ ...personalData, nif: value });
                                  // Validar NIF em tempo real
                                  const validation = validateNIF(value);
                                  setNifError(validation.error);
                                }}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                data-testid="personal-nif"
                                className={`h-9 ${nifError ? 'border-red-500 focus:ring-red-500' : ''} ${getConfidenceIndicator("nif")?.borderClass || ''}`}
                                placeholder="9 dígitos"
                              />
                              {nifError && (
                                <p className="text-xs text-red-500 mt-1">{nifError}</p>
                              )}
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nº Segurança Social (NISS)</Label>
                              <Input
                                value={personalData.niss || ""}
                                onChange={(e) => setPersonalData({ ...personalData, niss: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className="h-9"
                                placeholder="11 dígitos"
                              />
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-1">
                                  <Label className="text-xs text-muted-foreground">Nº Documento (CC)</Label>
                                  <AIBadge {...(getFieldMetaFor("dados_pessoais.documento_id") || {})} />
                                </div>
                                {getConfidenceIndicator("documento_id") && (
                                  <Badge className={`text-[9px] px-1.5 py-0 ${getConfidenceIndicator("documento_id").badge}`}>
                                    IA {getConfidenceIndicator("documento_id").label}
                                  </Badge>
                                )}
                              </div>
                              <Input
                                value={personalData.documento_id || ""}
                                onChange={(e) => setPersonalData({ ...personalData, documento_id: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className={`h-9 ${getConfidenceIndicator("documento_id")?.borderClass || ''}`}
                              />
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <Label className="text-xs text-muted-foreground">Validade CC <span className="text-red-500">*</span></Label>
                                {getConfidenceIndicator("cc_validity") && (
                                  <Badge className={`text-[9px] px-1.5 py-0 ${getConfidenceIndicator("cc_validity").badge}`}>
                                    IA {getConfidenceIndicator("cc_validity").label}
                                  </Badge>
                                )}
                              </div>
                              <Input
                                type="date"
                                value={formatDateForInput(personalData.data_validade_cc)}
                                onChange={(e) => setPersonalData({ ...personalData, data_validade_cc: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className={`h-9 ${getConfidenceIndicator("cc_validity")?.borderClass || ''}`}
                              />
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <Label className="text-xs text-muted-foreground">Data de Nascimento</Label>
                                {getConfidenceIndicator("birth_date") && (
                                  <Badge className={`text-[9px] px-1.5 py-0 ${getConfidenceIndicator("birth_date").badge}`}>
                                    IA {getConfidenceIndicator("birth_date").label}
                                  </Badge>
                                )}
                              </div>
                              <Input
                                type="date"
                                value={formatDateForInput(personalData.data_nascimento || personalData.birth_date)}
                                onChange={(e) => setPersonalData({ ...personalData, data_nascimento: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className={`h-9 ${getConfidenceIndicator("birth_date")?.borderClass || ''}`}
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Tipo de Compra</Label>
                              <Select
                                value={personalData.compra_tipo || ""}
                                onValueChange={(value) => setPersonalData({ ...personalData, compra_tipo: value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="primeira_habitacao">Primeira Habitação</SelectItem>
                                  <SelectItem value="segunda_habitacao">Segunda Habitação</SelectItem>
                                  <SelectItem value="investimento">Investimento</SelectItem>
                                  <SelectItem value="refinanciamento">Refinanciamento</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Estado Civil</Label>
                              <Select
                                value={personalData.estado_civil || personalData.marital_status || ""}
                                onValueChange={(value) => setPersonalData({ ...personalData, estado_civil: value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="solteiro">Solteiro(a)</SelectItem>
                                  <SelectItem value="casado">Casado(a)</SelectItem>
                                  <SelectItem value="casado_adquiridos">Casado(a) - Comunhão de Adquiridos</SelectItem>
                                  <SelectItem value="casado_geral">Casado(a) - Comunhão Geral</SelectItem>
                                  <SelectItem value="casado_separacao">Casado(a) - Separação de Bens</SelectItem>
                                  <SelectItem value="divorciado">Divorciado(a)</SelectItem>
                                  <SelectItem value="viuvo">Viúvo(a)</SelectItem>
                                  <SelectItem value="uniao_facto">União de Facto</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Sexo</Label>
                              <Select
                                value={personalData.sexo || ""}
                                onValueChange={(value) => setPersonalData({ ...personalData, sexo: value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="M">Masculino</SelectItem>
                                  <SelectItem value="F">Feminino</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Naturalidade</Label>
                              <Input
                                value={personalData.naturalidade || ""}
                                onChange={(e) => setPersonalData({ ...personalData, naturalidade: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nacionalidade</Label>
                              <Input
                                value={personalData.nacionalidade || personalData.nationality || ""}
                                onChange={(e) => setPersonalData({ ...personalData, nacionalidade: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Altura (m)</Label>
                              <Input
                                value={personalData.altura || ""}
                                onChange={(e) => setPersonalData({ ...personalData, altura: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Profissão</Label>
                              <Input
                                value={personalData.profissao || ""}
                                onChange={(e) => setPersonalData({ ...personalData, profissao: e.target.value })}
                                disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                className="h-9"
                                placeholder="Profissão do titular"
                              />
                            </div>
                            <div className="space-y-1 flex items-end pb-2">
                              <div className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  id="menor_35_anos"
                                  checked={personalData.menor_35_anos || false}
                                  onChange={(e) => setPersonalData({ ...personalData, menor_35_anos: e.target.checked })}
                                  disabled={editingCardId !== 'personal_identificacao' || !canEditPersonal}
                                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <Label htmlFor="menor_35_anos" className="text-xs text-muted-foreground cursor-pointer whitespace-nowrap">
                                  Menor de 35 anos
                                </Label>
                              </div>
                              <p className="text-[10px] text-muted-foreground">
                                Apoio ao estado (jovem até 35 anos)
                              </p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* Filiação */}
                      <Card className={`border-l-4 border-l-orange-500 ${editingCardId !== 'personal_filiacao' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Filiação" cardKey="personal_filiacao" icon={Users} canEdit={canEditPersonal} />
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nome do Pai</Label>
                              <Input
                                value={personalData.nome_pai || ""}
                                onChange={(e) => setPersonalData({ ...personalData, nome_pai: e.target.value })}
                                disabled={editingCardId !== 'personal_filiacao' || !canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nome da Mãe</Label>
                              <Input
                                value={personalData.nome_mae || ""}
                                onChange={(e) => setPersonalData({ ...personalData, nome_mae: e.target.value })}
                                disabled={editingCardId !== 'personal_filiacao' || !canEditPersonal}
                                className="h-9"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* Morada */}
                      <Card className={`border-l-4 border-l-teal-500 ${editingCardId !== 'personal_morada' ? 'read-only-card' : ''}`}>
                        <CardContent className="pt-4">
                          <CardHeaderWithEdit title="Morada" cardKey="personal_morada" icon={MapPin} canEdit={canEditPersonal} />
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1 sm:col-span-2">
                              <Label className="text-xs text-muted-foreground">Morada Fiscal</Label>
                              <Input
                                value={personalData.morada_fiscal || personalData.address || ""}
                                onChange={(e) => setPersonalData({ ...personalData, morada_fiscal: e.target.value })}
                                disabled={editingCardId !== 'personal_morada' || !canEditPersonal}
                                className="h-9"
                                placeholder="Rua, número, andar"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Código Postal</Label>
                              <Input
                                value={personalData.codigo_postal || ""}
                                onChange={(e) => setPersonalData({ ...personalData, codigo_postal: e.target.value })}
                                disabled={editingCardId !== 'personal_morada' || !canEditPersonal}
                                className="h-9"
                                placeholder="0000-000"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* 2º Titular — Componente com pesquisa e ficha */}
                      <SecondTitularCard process={process} onUpdate={fetchData} />
                      
                      {/* 2º Titular / Fiador */}
                      {(process?.co_buyers?.length > 0 || process?.co_applicants?.length > 0) && (
                        <Card className="border-l-4 border-l-indigo-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <Users className="h-4 w-4 text-indigo-500" />
                              2º Titular / Fiador
                              <Badge variant="secondary" className="ml-2">
                                {(process?.co_buyers?.length || 0) + (process?.co_applicants?.length || 0)} pessoa(s)
                              </Badge>
                            </h4>
                            <div className="space-y-3">
                              {/* Co-Buyers (do CPCV) */}
                              {Array.isArray(process?.co_buyers) && process.co_buyers.map((buyer, index) => (
                                <div key={`buyer-${index}`} className="p-3 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg border border-indigo-200 dark:border-indigo-800">
                                  <div className="flex items-center gap-2 mb-2">
                                    <Badge variant="outline" className="text-xs">
                                      Comprador {index + 1}
                                    </Badge>
                                    {buyer.estado_civil && (
                                      <Badge variant="secondary" className="text-xs">
                                        {safeString(buyer.estado_civil)}
                                      </Badge>
                                    )}
                                  </div>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                                    {buyer.nome && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Nome:</span>
                                        <p className="font-medium">{safeString(buyer.nome)}</p>
                                      </div>
                                    )}
                                    {buyer.nif && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">NIF:</span>
                                        <p className="font-medium">{safeString(buyer.nif)}</p>
                                      </div>
                                    )}
                                    {buyer.email && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Email:</span>
                                        <p className="font-medium">{safeString(buyer.email)}</p>
                                      </div>
                                    )}
                                    {buyer.telefone && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Telefone:</span>
                                        <p className="font-medium">{safeString(buyer.telefone)}</p>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ))}
                              
                              {/* Co-Applicants (do IRS/Simulação) */}
                              {Array.isArray(process?.co_applicants) && process.co_applicants.map((applicant, index) => (
                                <div key={`applicant-${index}`} className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200 dark:border-purple-800">
                                  <div className="flex items-center gap-2 mb-2">
                                    <Badge variant="outline" className="text-xs">
                                      {index === 0 ? "Titular" : "Cônjuge/Proponente " + (index + 1)}
                                    </Badge>
                                    {applicant.rendimento_mensal && (
                                      <Badge variant="secondary" className="text-xs">
                                        {safeNumber(applicant.rendimento_mensal).toLocaleString('pt-PT')}€/mês
                                      </Badge>
                                    )}
                                  </div>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                                    {applicant.nome && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Nome:</span>
                                        <p className="font-medium">{safeString(applicant.nome)}</p>
                                      </div>
                                    )}
                                    {applicant.nif && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">NIF:</span>
                                        <p className="font-medium">{safeString(applicant.nif)}</p>
                                      </div>
                                    )}
                                    {applicant.data_nascimento && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Data Nascimento:</span>
                                        <p className="font-medium">{safeString(applicant.data_nascimento)}</p>
                                      </div>
                                    )}
                                    {applicant.entidade_patronal && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Empresa:</span>
                                        <p className="font-medium">{safeString(applicant.entidade_patronal)}</p>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ))}
                              
                              {/* Rendimento Agregado */}
                              {financialData?.rendimento_agregado && (
                                <div className="mt-3 p-2 bg-green-50 dark:bg-green-900/20 rounded border border-green-200 dark:border-green-800">
                                  <p className="text-sm font-medium text-green-700 dark:text-green-400">
                                    Rendimento Agregado: {safeNumber(financialData.rendimento_agregado).toLocaleString('pt-PT')}€/mês
                                  </p>
                                </div>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      )}
                    </div>
    </>
  );
}
