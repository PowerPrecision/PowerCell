/**
 * Unit tests for process update payload sanitizers / optimistic merge.
 */
import {
  sanitizeProcessUpdatePayload,
  sanitizeClientUpdatePayload,
  mergeProcessOptimistic,
  FORBIDDEN_PROCESS_UPDATE_KEYS,
} from './processUpdatePayload';

describe('sanitizeProcessUpdatePayload', () => {
  it('strips forbidden keys including documents / onedrive_links', () => {
    const out = sanitizeProcessUpdatePayload({
      notes: 'ok',
      documents: [],
      onedrive_links: [{ id: 1 }],
      attachments: [],
      personal_data: { nif: '123456789' },
    });
    expect(out.notes).toBe('ok');
    expect(out.personal_data).toEqual({ nif: '123456789' });
    expect(out.documents).toBeUndefined();
    expect(out.onedrive_links).toBeUndefined();
    expect(out.attachments).toBeUndefined();
  });

  it('omits empty wipe-sensitive arrays by default', () => {
    const out = sanitizeProcessUpdatePayload({
      monitored_emails: [],
      co_buyers: [],
      labels: [],
      status: 'em_analise',
    });
    expect(out.monitored_emails).toBeUndefined();
    expect(out.co_buyers).toBeUndefined();
    expect(out.labels).toBeUndefined();
    expect(out.status).toBe('em_analise');
  });

  it('allows empty labels when allowEmptyArrays includes labels', () => {
    const out = sanitizeProcessUpdatePayload(
      { labels: [], notes: 'x' },
      { allowEmptyArrays: ['labels'] }
    );
    expect(out.labels).toEqual([]);
    expect(out.notes).toBe('x');
  });

  it('keeps non-empty arrays', () => {
    const out = sanitizeProcessUpdatePayload({
      monitored_emails: ['a@b.pt'],
      labels: ['urgente'],
    });
    expect(out.monitored_emails).toEqual(['a@b.pt']);
    expect(out.labels).toEqual(['urgente']);
  });

  it('lists expected forbidden keys', () => {
    expect(FORBIDDEN_PROCESS_UPDATE_KEYS).toContain('documents');
    expect(FORBIDDEN_PROCESS_UPDATE_KEYS).toContain('onedrive_links');
  });
});

describe('sanitizeClientUpdatePayload', () => {
  it('drops empty contacto fields that would wipe server data', () => {
    const out = sanitizeClientUpdatePayload({
      nome: 'Ana',
      contacto: { email: '', telefone: '912345678' },
    });
    expect(out.nome).toBe('Ana');
    expect(out.contacto).toEqual({ telefone: '912345678' });
  });

  it('omits contacto entirely when both empty', () => {
    const out = sanitizeClientUpdatePayload({
      contacto: { email: '  ', telefone: '' },
      dados_pessoais: { nif: '123' },
    });
    expect(out.contacto).toBeUndefined();
    expect(out.dados_pessoais).toEqual({ nif: '123' });
  });
});

describe('mergeProcessOptimistic', () => {
  it('deep-merges personal_data instead of replacing', () => {
    const merged = mergeProcessOptimistic(
      { personal_data: { nif: '111', nome: 'A' }, status: 'x' },
      { personal_data: { nif: '222' }, notes: 'n' }
    );
    expect(merged.personal_data).toEqual({ nif: '222', nome: 'A' });
    expect(merged.status).toBe('x');
    expect(merged.notes).toBe('n');
  });
});
