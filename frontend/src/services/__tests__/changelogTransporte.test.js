/** O que SAI para o servidor ao marcar uma atualização como Premium. */
import { afterEach, describe, expect, it, vi } from "vitest";

import api, { generateChangelogAI, setChangelogPremium } from "../api";

afterEach(() => vi.restoreAllMocks());

describe("setChangelogPremium", () => {
  it("faz PATCH ao recurso certo com o booleano", async () => {
    const patch = vi.spyOn(api, "patch").mockResolvedValue({ data: {} });
    await setChangelogPremium("abc123", true);
    expect(patch).toHaveBeenCalledWith("/system/changelog/abc123/premium", { is_premium: true });
    await setChangelogPremium("abc123", false);
    expect(patch).toHaveBeenLastCalledWith("/system/changelog/abc123/premium", { is_premium: false });
  });
});

describe("generateChangelogAI", () => {
  it("envia o corpo tal como recebe (is_premium só vai se o chamador o puser)", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    await generateChangelogAI({ source_type: "worklog" });
    expect(post).toHaveBeenCalledWith("/system/changelog/generate-ai", { source_type: "worklog" });
  });
});
