/**
 * «Forçar criação de pasta» — o pedido que SAI (Lote 6, ponto 4).
 *
 * Os testes de ecrã falseiam esta função; este mede o que ela de facto envia: um POST ao id, SEM
 * corpo (o caminho nunca viaja — deriva do id no servidor) e com `skipErrorToast` (o erro lê-se ao
 * lado do botão, não num toast solto).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import api, { forceCreateS3Folder } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("forceCreateS3Folder", () => {
  it("POST /documents/client/{id}/init-folders, sem corpo e com skipErrorToast", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { success: true } });

    await forceCreateS3Folder("cli-1");

    expect(post).toHaveBeenCalledTimes(1);
    const [url, corpo, config] = post.mock.calls[0];
    expect(url).toBe("/documents/client/cli-1/init-folders");
    expect(corpo).toBeNull();
    expect(config).toMatchObject({ skipErrorToast: true });
  });
});
