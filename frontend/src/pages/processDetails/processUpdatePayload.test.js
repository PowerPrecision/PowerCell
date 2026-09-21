/**
 * Unit tests for process update payload sanitizers / optimistic merge.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  sanitizeProcessUpdatePayload,
  sanitizeClientUpdatePayload,
  mergeProcessOptimistic,
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
