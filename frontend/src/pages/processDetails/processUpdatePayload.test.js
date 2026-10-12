/**
 * Unit tests for process update payload sanitizers / optimistic merge.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  sanitizeProcessUpdatePayload,
  sanitizeClientUpdatePayload,
  mergeProcessOptimistic,
  contactosAGravar,
  FORBIDDEN_PROCESS_UPDATE_KEYS,
} from './processUpdatePayload.js';

describe('sanitizeProcessUpdatePayload', () => {
  it('strips forbidden keys including documents / onedrive_links', () => {
    const out = sanitizeProcessUpdatePayload({
      notes: 'ok',
      documents: [],
      onedrive_links: [{ id: 1 }],
      attachments: [],
      personal_data: { nif: '123456789' },
    });
    assert.strictEqual(out.notes, 'ok');
    assert.deepStrictEqual(out.personal_data, { nif: '123456789' });
    assert.strictEqual(out.documents, undefined);
    assert.strictEqual(out.onedrive_links, undefined);
    assert.strictEqual(out.attachments, undefined);
  });

  it('omits empty wipe-sensitive arrays by default', () => {
    const out = sanitizeProcessUpdatePayload({
      monitored_emails: [],
      co_buyers: [],
      labels: [],
      status: 'em_analise',
    });
    assert.strictEqual(out.monitored_emails, undefined);
    assert.strictEqual(out.co_buyers, undefined);
    assert.strictEqual(out.labels, undefined);
    assert.strictEqual(out.status, 'em_analise');
  });

  it('allows empty labels when allowEmptyArrays includes labels', () => {
    const out = sanitizeProcessUpdatePayload(
      { labels: [], notes: 'x' },
      { allowEmptyArrays: ['labels'] }
    );
    assert.deepStrictEqual(out.labels, []);
    assert.strictEqual(out.notes, 'x');
  });

  it('keeps observations and notes (Pacote DP)', () => {
    const out = sanitizeProcessUpdatePayload({
      observations: 'nota livre',
      notes: 'nota livre',
    });
    assert.strictEqual(out.observations, 'nota livre');
    assert.strictEqual(out.notes, 'nota livre');
  });

  it('keeps non-empty arrays', () => {
    const out = sanitizeProcessUpdatePayload({
      monitored_emails: ['a@b.pt'],
      labels: ['urgente'],
    });
    assert.deepStrictEqual(out.monitored_emails, ['a@b.pt']);
    assert.deepStrictEqual(out.labels, ['urgente']);
  });

  it('lists expected forbidden keys', () => {
    assert.ok(FORBIDDEN_PROCESS_UPDATE_KEYS.includes('documents'));
    assert.ok(FORBIDDEN_PROCESS_UPDATE_KEYS.includes('onedrive_links'));
  });
});

describe('sanitizeClientUpdatePayload', () => {
  it('drops empty contacto fields that would wipe server data', () => {
    const out = sanitizeClientUpdatePayload({
      nome: 'Ana',
      contacto: { email: '', telefone: '912345678' },
    });
    assert.strictEqual(out.nome, 'Ana');
    assert.deepStrictEqual(out.contacto, { telefone: '912345678' });
  });

  it('omits contacto entirely when both empty', () => {
    const out = sanitizeClientUpdatePayload({
      contacto: { email: '  ', telefone: '' },
      dados_pessoais: { nif: '123' },
    });
    assert.strictEqual(out.contacto, undefined);
    assert.deepStrictEqual(out.dados_pessoais, { nif: '123' });
  });
});

describe('mergeProcessOptimistic', () => {
  it('deep-merges personal_data instead of replacing', () => {
    const merged = mergeProcessOptimistic(
      { personal_data: { nif: '111', nome: 'A' }, status: 'x' },
      { personal_data: { nif: '222' }, notes: 'n' }
    );
    assert.deepStrictEqual(merged.personal_data, { nif: '222', nome: 'A' });
    assert.strictEqual(merged.status, 'x');
    assert.strictEqual(merged.notes, 'n');
  });
});


describe('sanitizeClientUpdatePayload — apagar contactos de propósito', () => {
  it('um contacto vazio SEM pedido explícito continua a ser descartado (a rede de segurança)', () => {
    const out = sanitizeClientUpdatePayload({ contacto: { email: '', telefone: '' } });
    assert.strictEqual(out.contacto, undefined);
  });

  it('com clearContactFields o email vazio segue como "" e o telefone não é tocado', () => {
    const out = sanitizeClientUpdatePayload(
      { contacto: { email: '  ', telefone: '912345678' } },
      { clearContactFields: ['email'] },
    );
    assert.deepStrictEqual(out.contacto, { email: '', telefone: '912345678' });
  });

  it('um campo NÃO listado continua protegido mesmo com outro listado', () => {
    const out = sanitizeClientUpdatePayload(
      { contacto: { email: '', telefone: '' } },
      { clearContactFields: ['telefone'] },
    );
    assert.deepStrictEqual(out.contacto, { telefone: '' });
  });

  it('ignora nomes que não são contactos limpáveis', () => {
    const out = sanitizeClientUpdatePayload(
      { nome: '', contacto: { email: 'a@b.pt' } },
      { clearContactFields: ['nome', 'nif'] },
    );
    assert.strictEqual(out.nome, undefined);
    assert.deepStrictEqual(out.contacto, { email: 'a@b.pt' });
  });

  it('um valor preenchido nunca é apagado por estar na lista', () => {
    const out = sanitizeClientUpdatePayload(
      { contacto: { email: ' novo@b.pt ' } },
      { clearContactFields: ['email'] },
    );
    assert.deepStrictEqual(out.contacto, { email: 'novo@b.pt' });
  });
});

describe('contactosAGravar', () => {
  const base = { email: 'ana@x.pt', telefone: '912345678' };

  it('com valores, envia-os ao cliente e ao processo e não limpa nada', () => {
    const r = contactosAGravar({ editingCardId: 'personal_contactos', ...base });
    assert.deepStrictEqual(r.contacto, { email: 'ana@x.pt', telefone: '912345678' });
    assert.deepStrictEqual(r.processo, { client_email: 'ana@x.pt', client_phone: '912345678' });
    assert.deepStrictEqual(r.limpar, []);
  });

  it('a editar o cartão de contactos, o email apagado vai como vazio explícito', () => {
    const r = contactosAGravar({ editingCardId: 'personal_contactos', ...base, email: '' });
    assert.strictEqual(r.contacto.email, '');
    assert.strictEqual(r.processo.client_email, '');
    assert.deepStrictEqual(r.limpar, ['email']);
    assert.strictEqual(r.contacto.telefone, '912345678');
  });

  it('só espaços conta como apagado', () => {
    const r = contactosAGravar({ editingCardId: 'personal_contactos', ...base, telefone: '   ' });
    assert.deepStrictEqual(r.limpar, ['telefone']);
  });

  it('null/undefined contam como apagado (no cartão de contactos)', () => {
    const r = contactosAGravar({ editingCardId: 'personal_contactos', email: null, telefone: undefined });
    assert.deepStrictEqual(r.limpar, ['email', 'telefone']);
  });

  it('a gravar OUTRO cartão, um contacto vazio nunca é enviado', () => {
    for (const cartao of ['personal_identificacao', 'financial_rendimentos', null, undefined]) {
      const r = contactosAGravar({ editingCardId: cartao, email: '', telefone: '' });
      assert.deepStrictEqual(r.contacto, {});
      assert.deepStrictEqual(r.processo, {});
      assert.deepStrictEqual(r.limpar, []);
    }
  });

  it('a gravar outro cartão, os contactos preenchidos seguem como antes', () => {
    const r = contactosAGravar({ editingCardId: 'personal_morada', ...base });
    assert.deepStrictEqual(r.processo, { client_email: 'ana@x.pt', client_phone: '912345678' });
  });
});
