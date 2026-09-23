/**
 * Ponte `node:test` → Vitest.
 *
 * PORQUÊ: os testes de utilitários (276, escritos para o corredor nativo do
 * Node) importam `describe`/`it` de `node:test`. Sob o Vitest esse import
 * devolveria o corredor do PRÓPRIO Node: os testes registavam-se noutro
 * motor e o Vitest não via nada — nem sequer falhava, o que é pior.
 *
 * O `vitest.config` aliasa `node:test` para este módulo (apenas no ambiente
 * de teste; o build não é afectado). Assim os 276 testes correm no motor novo
 * SEM uma única linha reescrita, e código novo pode importar directamente do
 * `vitest`. O `node:assert/strict` que eles usam funciona tal e qual — é um
 * builtin do Node e o Vitest corre em Node.
 */
export {
  describe,
  it,
  test,
  suite,
  beforeAll as before,
  afterAll as after,
  beforeEach,
  afterEach,
} from "vitest";

// `node:test` expõe `mock`; quem precisar de duplos usa `vi` do Vitest.
export { vi as mock } from "vitest";
