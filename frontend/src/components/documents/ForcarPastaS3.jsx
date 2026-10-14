import { useState } from "react";
import { FolderPlus, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "../ui/button";
import { forceCreateS3Folder } from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";

/**
 * «Forçar criação de pasta» — a válvula de quem abre uma ficha sem pasta no armazenamento.
 *
 * Apresentação + uma chamada: o servidor decide TUDO (derivar do id, recriar no mesmo caminho,
 * substituir um ponteiro inutilizável) e responde `created` / `recreated` / `already_exists`.
 * Aqui só se diz o que aconteceu. O pedido pode falhar (S3 em baixo, rede) sem partir a página:
 * o erro fica ao lado do botão, que continua disponível para tentar outra vez.
 *
 * @param {string}   id         id do processo OU do cliente (o servidor resolve)
 * @param {function} [onFeito]  chamada depois de uma resposta de sucesso (recarregar a lista)
 * @param {boolean}  [compacto] sem moldura, para encaixar numa linha de cartão vazio
 */
export default function ForcarPastaS3({ id, onFeito, compacto = false }) {
  const [aCriar, setACriar] = useState(false);
  const [erro, setErro] = useState("");

  const forcar = async () => {
    if (!id || aCriar) return;
    setACriar(true);
    setErro("");
    try {
      const { data } = await forceCreateS3Folder(id);
      if (data?.already_exists) toast.info("A pasta já existe no armazenamento.");
      else if (data?.recreated) toast.success("Pasta recriada no armazenamento.");
      else toast.success("Pasta criada no armazenamento.");
      if (onFeito) await onFeito(data);
    } catch (e) {
      // Sem resposta (ligação cortada) não há `detail`: diz-se na mesma, em vez de um botão mudo.
      setErro(
        e?.response
          ? extractErrorMessage(e.response.data?.detail, "Não foi possível criar a pasta.")
          : "Não foi possível contactar o servidor. Tente novamente dentro de instantes.",
      );
    } finally {
      setACriar(false);
    }
  };

  return (
    <div
      data-testid="forcar-pasta-s3"
      className={compacto ? "flex flex-col items-start gap-1" : "flex flex-col gap-2 border-b bg-muted/40 px-4 py-3"}
    >
      {!compacto && (
        <p className="text-sm text-muted-foreground">
          Esta ficha ainda não tem pasta no armazenamento de documentos.
        </p>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-2"
        onClick={forcar}
        disabled={aCriar}
        data-testid="forcar-pasta-s3-btn"
      >
        {aCriar ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FolderPlus className="h-4 w-4" aria-hidden="true" />}
        Forçar criação de pasta
      </Button>
      {erro && (
        <p role="alert" data-testid="forcar-pasta-s3-erro" className="text-xs text-destructive">
          {erro}
        </p>
      )}
    </div>
  );
}
