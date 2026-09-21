/**
 * Guarda: o envio de documentação tem de ir pelo cliente Axios.
 *
 * INCIDENTE 2026-09-21. `SendDocumentationModal` enviava com `fetch` cru,
 * passando só `Content-Type` e `Authorization`. O interceptor que injecta
 * `X-Company-Id` (e `X-Active-Role`) vive no cliente Axios, pelo que esses
 * cabeçalhos não seguiam.
 *
 * Sem `X-Company-Id`, o backend faz `get_active_company_id_async` cair em
 * `user.company` — que é o NOME da empresa, não o id. A procura da
 * configuração de email por `company_id` falha, cai numa sub-configuração
 * antiga e o envio sai com a password errada: `535 Incorrect
 * authentication data`. O email de teste, que vai por Axios, funcionava
 * com a mesma conta — foi essa assimetria que denunciou o problema.
 *
 * Correr com: node --test frontend/src/components/sendDocumentation.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AQUI = dirname(fileURLToPath(import.meta.url));
const FONTE = readFileSync(join(AQUI, "SendDocumentationModal.js"), "utf8");

describe("SendDocumentationModal — envio", () => {
  it("usa o cliente Axios, que injecta X-Company-Id", () => {
    assert.ok(
      FONTE.includes("api.post(") &&
        FONTE.includes("/emails/send-documentation/"),
      "o envio tem de ir por `api.post`, não por `fetch`"
    );
  });

  it("NÃO envia a documentação com fetch cru", () => {
    assert.ok(
      !/fetch\([^)]*send-documentation/.test(FONTE),
      "voltar a `fetch` perde os cabeçalhos de empresa e o envio usa a " +
        "configuração de email errada"
    );
  });

  it("importa o cliente Axios", () => {
    assert.ok(
      /import\s+api\s+from\s+["']\.\.\/services\/api["']/.test(FONTE),
      "sem o import, `api.post` não existe"
    );
  });
});

describe("Cliente Axios", () => {
  const API = readFileSync(join(AQUI, "..", "services", "api.js"), "utf8");

  it("injecta X-Company-Id nos pedidos", () => {
    // É esta injecção que o `fetch` cru contornava.
    assert.ok(
      API.includes("X-Company-Id"),
      "se o interceptor deixar de injectar o cabeçalho, o envio volta a " +
        "resolver a configuração errada"
    );
  });
});
