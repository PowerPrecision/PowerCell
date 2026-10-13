/**
 * A permissão de IA calculada pelo SERVIDOR chega ao gestor de ficheiros.
 *
 * O gestor (`S3FileManager`) já tem o seu teste de botões; o que ninguém provava é que o
 * `pode_usar_ia_documentos` do detalhe do processo atravessa o separador e o painel até lá.
 * Sem esta ligação o gate novo existia e o botão continuava escondido à equipa da rede
 * satélite — um componente certo ligado a nada.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const recebido = vi.hoisted(() => ({ props: null }));

vi.mock("../../../S3FileManager", () => ({
  default: (props) => {
    recebido.props = props;
    return <div data-testid="gestor-falso" />;
  },
}));
vi.mock("../../../DriveLinks", () => ({ default: () => null }));
vi.mock("../../../PortalDocumentRequests", () => ({ default: () => null }));
vi.mock("../../../../contexts/AuthContext", () => ({
  useAuth: () => ({ effectiveRole: "consultor", user: { id: "u-1", role: "consultor" } }),
}));

import DocumentsTab from "../DocumentsTab";

function montar(process, extra = {}) {
  recebido.props = null;
  render(
    <DocumentsTab
      hasAnyRole={() => false}
      user={{ id: "u-1", role: "consultor" }}
      id="proc-1"
      process={process}
      setDocumentsRefreshKey={() => {}}
      documentsRefreshKey={0}
      {...extra}
    />,
  );
  return screen.getByTestId("gestor-falso");
}

describe("DocumentsTab — permissão de IA do servidor", () => {
  it("passa `true` ao gestor de ficheiros", () => {
    montar({ client_name: "Ana", pode_usar_ia_documentos: true });
    expect(recebido.props.podeUsarIA).toBe(true);
  });

  it("passa `false` quando o servidor recusa", () => {
    montar({ client_name: "Ana", pode_usar_ia_documentos: false });
    expect(recebido.props.podeUsarIA).toBe(false);
  });

  it("sem a flag (processo ainda a carregar ou sessão antiga) passa undefined, não false", () => {
    montar({ client_name: "Ana" });
    expect(recebido.props.podeUsarIA).toBeUndefined();
  });

  it("o processo fechado continua a chegar como somente leitura", () => {
    montar({ client_name: "Ana", pode_usar_ia_documentos: true }, { processoFechado: true });
    expect(recebido.props.readOnly).toBe(true);
    expect(recebido.props.podeUsarIA).toBe(true);
  });
});
