import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getEmailContacts: vi.fn(), saveEmailContact: vi.fn(), hideEmailContact: vi.fn() }));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import CampoDeDestinatarios from "../CampoDeDestinatarios";
import GerirContactosDialog from "../GerirContactosDialog";

// Valores diferentes das omissões: com [] ou "" um erro de leitura passava.
const ANA = { address: "ana.costa@x.pt", name: "Ana Costa", favorite: true, use_count: 7 };
const RUI = { address: "rui@x.pt", name: "", favorite: false, use_count: 3 };

function Controlado({ inicial = "" }) {
  const [valor, setValor] = useState(inicial);
  return (
    <>
      <CampoDeDestinatarios ariaLabel="Para" value={valor} onChange={setValor} />
      <output data-testid="valor">{valor}</output>
    </>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getEmailContacts.mockResolvedValue({ data: { contacts: [ANA, RUI] } });
});

describe("CampoDeDestinatarios", () => {
  it("ao focar mostra os contactos mais usados", async () => {
    render(<Controlado />);
    await userEvent.click(screen.getByRole("combobox", { name: "Para" }));

    expect(await screen.findByRole("option", { name: /Ana Costa <ana.costa@x.pt>/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /rui@x.pt/ })).toBeInTheDocument();
  });

  it("escolher um contacto substitui só o último pedaço", async () => {
    render(<Controlado inicial="paulo@x.pt, ru" />);
    await userEvent.click(screen.getByRole("combobox", { name: "Para" }));
    await userEvent.click(await screen.findByRole("option", { name: /rui@x.pt/ }));

    expect(screen.getByTestId("valor")).toHaveTextContent("paulo@x.pt, rui@x.pt,");
  });

  it("pesquisa pelo último pedaço que se está a escrever", async () => {
    render(<Controlado inicial="paulo@x.pt, ru" />);
    await userEvent.click(screen.getByRole("combobox", { name: "Para" }));
    await waitFor(() => expect(api.getEmailContacts).toHaveBeenCalledWith("ru"));
  });

  it("não volta a sugerir quem já está no campo", async () => {
    render(<Controlado inicial="rui@x.pt, a" />);
    await userEvent.click(screen.getByRole("combobox", { name: "Para" }));
    await screen.findByRole("option", { name: /Ana Costa/ });
    expect(screen.queryByRole("option", { name: /rui@x.pt/ })).not.toBeInTheDocument();
  });

  it("o teclado escolhe: seta para baixo + Enter", async () => {
    render(<Controlado />);
    await userEvent.click(screen.getByRole("combobox", { name: "Para" }));
    await screen.findByRole("option", { name: /Ana Costa/ });

    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    expect(screen.getByTestId("valor")).toHaveTextContent("rui@x.pt,");
  });

  it("Escape fecha a lista sem mexer no texto", async () => {
    render(<Controlado inicial="an" />);
    await userEvent.click(screen.getByRole("combobox", { name: "Para" }));
    await screen.findByRole("listbox");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.getByTestId("valor")).toHaveTextContent("an");
  });

  it("um pedido que falha não impede de escrever nem mostra erro", async () => {
    api.getEmailContacts.mockRejectedValue(new Error("rede"));
    render(<Controlado />);
    const campo = screen.getByRole("combobox", { name: "Para" });
    await userEvent.click(campo);
    await userEvent.type(campo, "ola@x.pt");

    expect(screen.getByTestId("valor")).toHaveTextContent("ola@x.pt");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it.each([[undefined], [null], [{}], [{ contacts: {} }]])(
    "uma resposta sem a forma esperada (%j) não rebenta",
    async (data) => {
      api.getEmailContacts.mockResolvedValue({ data });
      render(<Controlado />);
      await userEvent.click(screen.getByRole("combobox", { name: "Para" }));
      await act(async () => {});
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    },
  );

  it("a resposta velha não substitui a nova", async () => {
    let resolverPrimeira;
    api.getEmailContacts
      .mockReturnValueOnce(new Promise((r) => { resolverPrimeira = r; }))
      .mockResolvedValue({ data: { contacts: [RUI] } });
    render(<Controlado />);
    const campo = screen.getByRole("combobox", { name: "Para" });
    await userEvent.click(campo);
    await userEvent.type(campo, "r");
    await screen.findByRole("option", { name: /rui@x.pt/ });

    await act(async () => { resolverPrimeira({ data: { contacts: [ANA] } }); });
    expect(screen.queryByRole("option", { name: /Ana Costa/ })).not.toBeInTheDocument();
  });
});

describe("GerirContactosDialog", () => {
  it("lista, marca favorito e remove", async () => {
    api.saveEmailContact.mockResolvedValue({ data: {} });
    api.hideEmailContact.mockResolvedValue({ data: {} });
    render(<GerirContactosDialog open onOpenChange={() => {}} />);

    expect(await screen.findByText(/Ana Costa <ana.costa@x.pt>/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Marcar como favorito: rui@x.pt" }));
    expect(api.saveEmailContact).toHaveBeenCalledWith({ address: "rui@x.pt", favorite: true });

    await userEvent.click(screen.getByRole("button", { name: "Remover rui@x.pt" }));
    expect(api.hideEmailContact).toHaveBeenCalledWith("rui@x.pt");
    await waitFor(() => expect(screen.queryByText("rui@x.pt")).not.toBeInTheDocument());
  });

  it("o favorito já marcado oferece retirar", async () => {
    render(<GerirContactosDialog open onOpenChange={() => {}} />);
    expect(await screen.findByRole("button", { name: "Retirar dos favoritos: ana.costa@x.pt" })).toHaveAttribute("aria-pressed", "true");
  });

  it("sem contactos di-lo; com erro avisa", async () => {
    api.getEmailContacts.mockResolvedValueOnce({ data: { contacts: [] } });
    const { unmount } = render(<GerirContactosDialog open onOpenChange={() => {}} />);
    expect(await screen.findByTestId("sem-contactos")).toBeInTheDocument();
    unmount();

    api.getEmailContacts.mockRejectedValueOnce(new Error("x"));
    render(<GerirContactosDialog open onOpenChange={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/carregar os contactos/);
  });
});
