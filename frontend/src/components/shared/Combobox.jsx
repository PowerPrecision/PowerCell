/**
 * Combobox pesquisável: ESCOLHE-SE de uma lista, nunca se escreve o valor (QA-6).
 *
 * A caixa de pesquisa só FILTRA as opções (ou, com `onPesquisar`, pede ao servidor as que
 * casam). O valor que sai por `onChange` é sempre o de uma opção existente — por isso quem o
 * usa para identificar uma ficha não pode gravar um nome digitado à mão.
 *
 * @param {Object} props
 * @param {Array<{value: string, label: string, hint?: string}>} props.opcoes
 * @param {string|null} props.value                  — valor da opção escolhida (ou null)
 * @param {Function} props.onChange                  — (value: string|null) => void
 * @param {string} [props.placeholder]
 * @param {string} [props.placeholderDaPesquisa]
 * @param {string} [props.textoSemResultados]
 * @param {string} [props.ariaLabel]
 * @param {boolean} [props.aCarregar]                — mostra «A carregar…» dentro da lista
 * @param {Function} [props.onPesquisar]             — (texto) => void; passa a pesquisa para o servidor
 * @param {Function} [props.onAbrir]                 — chamado ao abrir (carrega a pedido)
 */
import React, { useState } from "react";
import { Check, ChevronsUpDown, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export default function Combobox({
  opcoes,
  value,
  onChange,
  placeholder = "Escolher…",
  placeholderDaPesquisa = "Pesquisar…",
  textoSemResultados = "Sem resultados.",
  ariaLabel,
  aCarregar = false,
  onPesquisar,
  onAbrir,
  className,
}) {
  const [aberto, setAberto] = useState(false);
  const lista = Array.isArray(opcoes) ? opcoes : [];
  const escolhida = lista.find((o) => o.value === value) || null;
  const pesquisaNoServidor = typeof onPesquisar === "function";

  const aoMudarAberto = (proximo) => {
    setAberto(proximo);
    if (proximo && typeof onAbrir === "function") onAbrir();
  };

  return (
    <div className={cn("flex items-center gap-1", className)}>
      <Popover open={aberto} onOpenChange={aoMudarAberto}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={aberto}
            aria-label={ariaLabel}
            className="min-w-[16rem] justify-between font-normal"
          >
            <span className={cn("truncate", !escolhida && "text-muted-foreground")}>
              {escolhida ? escolhida.label : placeholder}
            </span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" aria-hidden="true" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[22rem] p-0" align="start">
          {/* Com pesquisa no servidor a lista já vem filtrada: o cmdk não volta a filtrar. */}
          <Command shouldFilter={!pesquisaNoServidor}>
            <CommandInput
              placeholder={placeholderDaPesquisa}
              onValueChange={pesquisaNoServidor ? onPesquisar : undefined}
            />
            <CommandList>
              {aCarregar ? (
                <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  A carregar…
                </div>
              ) : (
                <CommandEmpty>{textoSemResultados}</CommandEmpty>
              )}
              <CommandGroup>
                {lista.map((opcao) => (
                  <CommandItem
                    key={opcao.value}
                    value={`${opcao.label} ${opcao.hint || ""} ${opcao.value}`}
                    onSelect={() => {
                      onChange(opcao.value);
                      setAberto(false);
                    }}
                  >
                    <Check
                      className={cn("mr-2 h-4 w-4", opcao.value === value ? "opacity-100" : "opacity-0")}
                      aria-hidden="true"
                    />
                    <span className="truncate">{opcao.label}</span>
                    {opcao.hint ? (
                      <span className="ml-auto pl-2 text-xs text-muted-foreground">{opcao.hint}</span>
                    ) : null}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {escolhida ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => onChange(null)}
          aria-label="Limpar escolha"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  );
}
