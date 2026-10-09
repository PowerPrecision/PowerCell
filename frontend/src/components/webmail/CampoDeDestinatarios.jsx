/**
 * Campo de destinatários com sugestão de contactos já usados (Bloco 2, Lote 12).
 *
 * É um `<input>` de texto livre (vários endereços separados por vírgula) com
 * uma lista de sugestões por baixo: ao focar mostra os mais usados, ao escrever
 * filtra pelo ÚLTIMO pedaço. Escolher um contacto substitui só esse pedaço.
 *
 * Duas regras que não se podem perder:
 *  - as sugestões são um EXTRA: um pedido que falha (ou chega tarde) nunca
 *    impede de escrever, e uma resposta velha nunca substitui a nova;
 *  - a lista usa `onMouseDown` + `preventDefault` — com `onClick` o `blur` do
 *    input fecha a lista antes de o clique chegar, e a escolha perdia-se.
 */
import { useEffect, useId, useRef, useState } from "react";

import { Input } from "../ui/input";
import { useDebounce } from "../../hooks/useDebounce";
import { getEmailContacts } from "../../services/api";
import {
  rotuloDoContacto,
  substituirUltimoToken,
  sugestoesParaOCampo,
  ultimoToken,
} from "../../utils/emailContacts";

/**
 * @param {object} props
 * @param {string} props.value
 * @param {(valor: string) => void} props.onChange
 * @param {string} [props.placeholder]
 * @param {string} [props.ariaLabel]
 */
const CampoDeDestinatarios = ({ value, onChange, placeholder, ariaLabel }) => {
  const idDaLista = useId();
  const [aberto, setAberto] = useState(false);
  const [contactos, setContactos] = useState([]);
  const [activo, setActivo] = useState(-1);
  const pedido = useRef(0);

  const pesquisa = useDebounce(ultimoToken(value), 200);

  useEffect(() => {
    if (!aberto) return undefined;
    const este = ++pedido.current;
    getEmailContacts(pesquisa)
      .then(({ data }) => {
        if (este !== pedido.current) return;
        setContactos(Array.isArray(data?.contacts) ? data.contacts : []);
        setActivo(-1);
      })
      .catch(() => {
        if (este === pedido.current) setContactos([]);
      });
    return () => {
      pedido.current += 1;
    };
  }, [aberto, pesquisa]);

  const sugestoes = sugestoesParaOCampo(contactos, value);
  const visivel = aberto && sugestoes.length > 0;

  const escolher = (contacto) => {
    onChange(substituirUltimoToken(value, contacto.address));
    setActivo(-1);
  };

  const aoTeclar = (e) => {
    if (!visivel) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActivo((i) => (i + 1) % sugestoes.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActivo((i) => (i <= 0 ? sugestoes.length - 1 : i - 1));
    } else if (e.key === "Enter" && activo >= 0) {
      e.preventDefault();
      escolher(sugestoes[activo]);
    } else if (e.key === "Escape") {
      e.stopPropagation();
      setAberto(false);
    }
  };

  return (
    <div className="relative flex-1">
      <Input
        role="combobox"
        aria-expanded={visivel}
        aria-controls={idDaLista}
        aria-autocomplete="list"
        aria-label={ariaLabel}
        autoComplete="off"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setAberto(true)}
        onBlur={() => setAberto(false)}
        onKeyDown={aoTeclar}
      />
      {visivel && (
        <ul
          id={idDaLista}
          role="listbox"
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-56 overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
        >
          {sugestoes.map((c, i) => (
            <li
              key={c.address}
              role="option"
              aria-selected={i === activo}
              className={`cursor-pointer rounded-sm px-2 py-1.5 text-sm ${
                i === activo ? "bg-accent text-accent-foreground" : "hover:bg-muted"
              }`}
              onMouseDown={(e) => {
                e.preventDefault();
                escolher(c);
              }}
            >
              {c.favorite && <span aria-hidden="true">★ </span>}
              {rotuloDoContacto(c)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default CampoDeDestinatarios;
