/**
 * «Envio para balcões» (Definições → Destinatários de Documentação): o Master passa.
 *
 * O cartão decidia com `user.role.match(/admin|ceo/i)` — `"master"` não casa, e o perfil global
 * recebia «Apenas administradores podem configurar destinatários.» Os pedidos eram `fetch` cru
 * (sem `X-Company-Id`/`X-Active-Role`); passam pelo cliente Axios. O componente é o REAL.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  default: {},
  getDocumentRecipients: vi.fn(),
  previewDocumentRecipientsTemplate: vi.fn(),
  updateSystemConfigSection: vi.fn(),
}));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("react-quill-new", () => ({ default: () => <div data-testid="quill" /> }));
vi.mock("react-quill-new/dist/quill.snow.css", () => ({}));

import DocumentRecipientsManager from "../DocumentRecipientsManager";

const CONFIG = {
  enabled: true,
  recipients: [{ name: "BCP Alvalade", email: "alvalade@bcp.pt", active: true }],
  email_template: "",
  default_to: "balcao@x.pt",
  default_to_name: "Balcão",
  default_to_emails: [],
};

const montar = (user) => render(<DocumentRecipientsManager token="t" user={user} />);
const AVISO = /apenas administradores podem configurar destinat/i;

beforeEach(() => {
  vi.clearAllMocks();
  api.getDocumentRecipients.mockResolvedValue({ data: CONFIG });
  globalThis.fetch = vi.fn();
});

describe("DocumentRecipientsManager — quem pode configurar", () => {
  it.each([["master"], ["admin"], ["ceo"]])("o perfil %s vê o editor e não o aviso", async (role) => {
    montar({ role });
    expect(await screen.findByText("BCP Alvalade")).toBeTruthy();
    expect(screen.queryByText(AVISO)).toBeNull();
  });

  it("contraprova: o consultor continua a receber o aviso e não vê os balcões", async () => {
    montar({ role: "consultor" });
    expect(await screen.findByText(AVISO)).toBeTruthy();
    expect(screen.queryByText("BCP Alvalade")).toBeNull();
  });

  it("quem tem Admin como perfil ADICIONAL também passa", async () => {
    montar({ role: "consultor", additional_roles: ["admin"] });
    expect(await screen.findByText("BCP Alvalade")).toBeTruthy();
  });

  it("lê a configuração pelo Axios e nunca pelo fetch cru", async () => {
    montar({ role: "master" });
    await screen.findByText("BCP Alvalade");
    await waitFor(() => expect(api.getDocumentRecipients).toHaveBeenCalledTimes(1));
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("guarda de fonte: nenhuma verificação de admin escrita à mão deixa o Master de fora", () => {
  it("nenhum componente decide por `role.match(/admin|ceo/)`", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const raiz = path.resolve(process.cwd(), "src");
    const ficheiros = [];
    const percorrer = (dir) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name);
        if (e.isDirectory()) { if (e.name !== "__tests__" && e.name !== "node_modules") percorrer(p); }
        else if (/\.(js|jsx)$/.test(e.name) && !/\.test\./.test(e.name)) ficheiros.push(p);
      }
    };
    percorrer(raiz);
    expect(ficheiros.length).toBeGreaterThan(50); // contraprova: o leitor leu mesmo
    const ofensores = ficheiros.filter((f) => /role\??\.match\(\/admin\|ceo/i.test(fs.readFileSync(f, "utf8")));
    expect(ofensores).toEqual([]);
  });
});
