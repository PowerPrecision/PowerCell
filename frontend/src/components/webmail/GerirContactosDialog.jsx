/**
 * Gestão dos contactos sugeridos (Bloco 2, Lote 12): ver, marcar favorito,
 * remover. Remover é ESCONDER no servidor (volta se o utilizador lhe escrever
 * de novo) — o texto di-lo, para ninguém esperar que o endereço seja apagado.
 */
import { useCallback, useEffect, useState } from "react";
import { Star, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { getEmailContacts, hideEmailContact, saveEmailContact } from "../../services/api";
import { rotuloDoContacto } from "../../utils/emailContacts";

const LIMITE = 50;

const GerirContactosDialog = ({ open, onOpenChange }) => {
  const [pesquisa, setPesquisa] = useState("");
  const [contactos, setContactos] = useState([]);
  const [estado, setEstado] = useState("a_carregar");

  const carregar = useCallback(async (q) => {
    setEstado("a_carregar");
    try {
      const { data } = await getEmailContacts(q, LIMITE);
      setContactos(Array.isArray(data?.contacts) ? data.contacts : []);
      setEstado("pronto");
    } catch {
      setEstado("erro");
    }
  }, []);

  useEffect(() => {
    if (open) carregar(pesquisa);
  }, [open, pesquisa, carregar]);

  const alternarFavorito = async (c) => {
    try {
      await saveEmailContact({ address: c.address, favorite: !c.favorite });
      await carregar(pesquisa);
    } catch {
      toast.error("Não foi possível actualizar o contacto.");
    }
  };

  const remover = async (c) => {
    try {
      await hideEmailContact(c.address);
      setContactos((lista) => lista.filter((x) => x.address !== c.address));
    } catch {
      toast.error("Não foi possível remover o contacto.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="gerir-contactos">
        <DialogHeader>
          <DialogTitle>Contactos</DialogTitle>
          <DialogDescription>
            Os endereços a que já escreveu nesta empresa. Remover tira-o das sugestões;
            volta a aparecer se lhe escrever de novo.
          </DialogDescription>
        </DialogHeader>
        <Input
          aria-label="Pesquisar contactos"
          placeholder="Pesquisar por nome ou endereço"
          value={pesquisa}
          onChange={(e) => setPesquisa(e.target.value)}
        />
        {estado === "erro" && (
          <p role="alert" className="text-sm text-destructive">
            Não foi possível carregar os contactos.
          </p>
        )}
        {estado === "pronto" && contactos.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="sem-contactos">
            Ainda não há contactos {pesquisa ? "com esse nome" : "guardados"}.
          </p>
        )}
        <ul className="max-h-72 space-y-1 overflow-y-auto">
          {contactos.map((c) => (
            <li key={c.address} className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm">
              <span className="min-w-0 flex-1 truncate">{rotuloDoContacto(c)}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                aria-pressed={Boolean(c.favorite)}
                aria-label={`${c.favorite ? "Retirar dos favoritos" : "Marcar como favorito"}: ${c.address}`}
                onClick={() => alternarFavorito(c)}
              >
                <Star className={`h-4 w-4 ${c.favorite ? "fill-current" : ""}`} aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                aria-label={`Remover ${c.address}`}
                onClick={() => remover(c)}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
};

export default GerirContactosDialog;
