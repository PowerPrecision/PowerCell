/**
 * A nota/instrução que a equipa escreveu num pedido de documento
 * (Bloco 3, ponto 17).
 *
 * Aparecia numa linha de texto cinzento-claro cortada com `truncate`: uma
 * instrução como «tem de estar legalizada e ter menos de 3 meses» ficava
 * ilegível — e o cliente só vê o que consegue ler. Aqui mostra-se inteira,
 * com as quebras de linha que a equipa escreveu, e com contraste.
 *
 * Só aceita TEXTO: o servidor devolve sempre string (`nota_do_pedido`). Um
 * objecto não se serializa para o ecrã — esconde-se.
 *
 * @param {object} props
 * @param {*} props.nota A nota do pedido.
 * @param {string} [props.className]
 */
export default function NotaDoPedido({ nota, className = "" }) {
  const texto = typeof nota === "string" ? nota.trim() : "";
  if (!texto) return null;
  return (
    <p
      data-testid="nota-do-pedido"
      className={`mt-1 whitespace-pre-line break-words rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-900 ${className}`}
    >
      {texto}
    </p>
  );
}
