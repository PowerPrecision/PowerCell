/**
 * UploadNaBancada — adicionar ficheiros ao processo SEM sair da bancada do Index.
 *
 * Botão (caminho acessível por teclado) + zona de arrastar e largar sobre a lista de documentos. Os ficheiros
 * seguem um a um para o MESMO endpoint de upload do CRM (`POST /documents/client/{id}/upload`), que decide o
 * desvio (pasta `Index` + fila da IA) e deixa o ficheiro marcado como carregado pelo Index — é o que «Apagar
 * metadados» depois limpa. Quem carrega é o indexador atribuído, e esse gesto conta como trabalho (arranca o
 * tratamento / adia o alarme de estagnação): isso é decidido no servidor.
 *
 * REGRAS: (1) uma única lista de tipos (`TIPOS_ACEITES`) para o botão e para o arrastar — em dois sítios divergem;
 * (2) **nunca sobrepõe**: um nome que já existe ganha ` (2)` (`nomesLivresDoLote`); (3) uma recusa diz o motivo
 * do servidor, ficheiro a ficheiro, e não impede os restantes; (4) no fim chama `onConcluido(n)` para a página
 * refrescar a lista.
 */
import { useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";

import { Button } from "../ui/button";
import Dropzone from "../shared/Dropzone";
import { uploadProcessS3File } from "../../services/api";
import { nomesLivresDoLote } from "../../utils/nomesDeFicheiro";
import { mensagemDeErro } from "../../utils/indexRevisao";

export const TIPOS_ACEITES = ".pdf,.jpg,.jpeg,.png";
const CATEGORIA_POR_OMISSAO = "Outros"; // a IA categoriza à entrada; o nome da categoria não decide nada aqui

export function UploadNaBancada({ processId, nomesExistentes = [], onConcluido, desactivado = false, children }) {
  const entrada = useRef(null);
  const [aEnviar, setAEnviar] = useState(false);
  const [resultado, setResultado] = useState(null); // { feitos, falhas: [{ nome, motivo }], recusados }

  const enviar = async (ficheiros) => {
    if (!ficheiros?.length || aEnviar) return;
    setAEnviar(true);
    setResultado(null);
    const nomes = nomesLivresDoLote(ficheiros.map((f) => f.name), nomesExistentes);
    const falhas = [];
    let feitos = 0;
    for (let i = 0; i < ficheiros.length; i += 1) {
      const formData = new FormData();
      formData.append("file", ficheiros[i]);
      formData.append("category", CATEGORIA_POR_OMISSAO);
      if (nomes[i] !== ficheiros[i].name) formData.append("custom_filename", nomes[i]);
      try {
        await uploadProcessS3File(processId, formData);
        feitos += 1;
      } catch (erro) {
        falhas.push({ nome: ficheiros[i].name, motivo: mensagemDeErro(erro) });
      }
    }
    setResultado((anterior) => ({ feitos, falhas, recusados: anterior?.recusados || null }));
    setAEnviar(false);
    if (feitos > 0) onConcluido?.(feitos);
  };

  const aoEscolher = (evento) => {
    const escolhidos = Array.from(evento.target.files || []);
    evento.target.value = ""; // permite escolher o mesmo ficheiro outra vez
    enviar(escolhidos);
  };

  return (
    <Dropzone
      onFicheiros={enviar}
      onRecusados={(_, mensagem) => setResultado({ feitos: 0, falhas: [], recusados: mensagem })}
      accept={TIPOS_ACEITES}
      disabled={desactivado || aEnviar}
      testId="upload-bancada-zona"
      rotulo="Largue os ficheiros para os adicionar ao processo"
    >
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={entrada}
            type="file"
            multiple
            accept={TIPOS_ACEITES}
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            data-testid="upload-bancada-entrada"
            onChange={aoEscolher}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={desactivado || aEnviar}
            onClick={() => entrada.current?.click()}
            data-testid="upload-bancada-botao"
          >
            {aEnviar ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Upload className="mr-1.5 h-4 w-4" aria-hidden="true" />
            )}
            Adicionar ficheiros
          </Button>
          <span className="text-xs text-muted-foreground">PDF, JPG ou PNG — também pode arrastá-los para aqui.</span>
        </div>

        <div aria-live="polite" data-testid="upload-bancada-estado">
          {resultado?.feitos > 0 && (
            <p className="text-sm text-[hsl(var(--success))]">
              {resultado.feitos === 1 ? "1 ficheiro adicionado." : `${resultado.feitos} ficheiros adicionados.`}
            </p>
          )}
          {resultado?.recusados && <p className="text-sm text-[hsl(var(--warning))]">{resultado.recusados}</p>}
          {resultado?.falhas?.length > 0 && (
            <ul className="space-y-0.5 text-sm text-destructive">
              {resultado.falhas.map((f) => (
                <li key={f.nome}>
                  «{f.nome}» não foi adicionado: {f.motivo}
                </li>
              ))}
            </ul>
          )}
        </div>
        {children}
      </div>
    </Dropzone>
  );
}

export default UploadNaBancada;
