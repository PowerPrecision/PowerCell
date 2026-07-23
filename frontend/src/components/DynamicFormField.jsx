/**
 * DynamicFormField — Renders a form field dynamically from config.
 *
 * Receives a field config object (from DEFAULT_FORM_CONFIG via /api/public/form-config)
 * and renders the appropriate input based on field_type. Styling matches the existing
 * PublicClientForm.js fields exactly (same Tailwind classes, Label/Input/Select components,
 * FieldHint/FieldError helpers).
 *
 * Supports:
 *   - text, email, tel, number, date → <Input>
 *   - textarea → <Textarea>
 *   - select → shadcn <Select>
 *   - checkbox → multi-select pill buttons (for arrays) or toggle pill (for booleans)
 *   - radio → Sim/Não button pair (for simple yes/no) or radio buttons
 *
 * @param {Object} props
 * @param {Object} props.field - Config: { field_key, label, field_type, options, is_required, placeholder, hint, depends_on, data_path }
 * @param {*}      props.value - Current field value
 * @param {Function} props.onChange - (field_key, value) => void
 * @param {string} [props.error] - Optional error message
 * @param {boolean} [props.disabled] - Optional disabled state
 * @param {string} [props.className] - Optional wrapper CSS class
 */
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Info, AlertCircle } from "lucide-react";
import { cn } from "../lib/utils";

// Reuse the same helper components as PublicClientForm
function FieldHint({ children }) {
  return (
  <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1">
    <Info className="h-3 w-3 mt-0.5 flex-shrink-0" />
    <span>{children}</span>
  </p>
  );
}

function FieldError({ children }) {
  return (
  <p className="text-xs text-red-600 mt-1 flex items-start gap-1 font-medium">
    <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
    <span>{children}</span>
  </p>
  );
}

function RequiredLabel({ htmlFor, children, required: isRequired = true }) {
  return (
  <Label htmlFor={htmlFor}>
    {children}
    {isRequired && (
      <>
        {" "}<span className="text-red-600 font-semibold">*</span>
        <span className="text-red-600 text-[10px] ml-1 font-medium">(obrigatório)</span>
      </>
    )}
  </Label>
  );
}

export default function DynamicFormField({
  field,
  value,
  onChange,
  error,
  disabled = false,
  className,
}) {
  const {
    field_key,
    label,
    field_type,
    options = [],
    is_required,
    placeholder,
    hint,
  } = field;

  const inputErrorClass = error
    ? "border-red-500 focus-visible:ring-red-500 bg-red-50"
    : "";

  // ── TEXT / EMAIL / TEL / NUMBER / DATE ──────────────────────
  if (["text", "email", "tel", "number", "date"].includes(field_type)) {
    return (
      <div className={cn("space-y-2", className)}>
        {is_required ? (
          <RequiredLabel htmlFor={field_key} required={is_required}>
            {label}
          </RequiredLabel>
        ) : (
          <Label htmlFor={field_key}>{label}</Label>
        )}
        <Input
          id={field_key}
          name={field_key}
          type={field_type === "tel" ? "tel" : field_type}
          value={value || ""}
          onChange={(e) => {
            // For number-like fields, allow normal typing
            onChange(field_key, e.target.value);
          }}
          placeholder={placeholder || ""}
          disabled={disabled}
          className={cn(inputErrorClass)}
          data-testid={`dynamic-${field_key}`}
        />
        {hint && <FieldHint>{hint}</FieldHint>}
        {error && <FieldError>{error}</FieldError>}
      </div>
    );
  }

  // ── TEXTAREA ────────────────────────────────────────────────
  if (field_type === "textarea") {
    return (
      <div className={cn("space-y-2", className)}>
        <Label htmlFor={field_key}>{label}</Label>
        <Textarea
          id={field_key}
          name={field_key}
          value={value || ""}
          onChange={(e) => onChange(field_key, e.target.value)}
          placeholder={placeholder || ""}
          rows={3}
          disabled={disabled}
          className={cn(inputErrorClass)}
          data-testid={`dynamic-${field_key}`}
        />
        {hint && <FieldHint>{hint}</FieldHint>}
        {error && <FieldError>{error}</FieldError>}
      </div>
    );
  }

  // ── SELECT ──────────────────────────────────────────────────
  if (field_type === "select") {
    return (
      <div className={cn("space-y-2", className)}>
        {is_required ? (
          <RequiredLabel htmlFor={field_key} required={is_required}>
            {label}
          </RequiredLabel>
        ) : (
          <Label htmlFor={field_key}>{label}</Label>
        )}
        <Select
          value={value || ""}
          onValueChange={(v) => onChange(field_key, v)}
          disabled={disabled}
        >
          <SelectTrigger
            className={cn(inputErrorClass)}
            data-testid={`dynamic-${field_key}`}
          >
            <SelectValue placeholder={placeholder || "Selecione"} />
          </SelectTrigger>
          <SelectContent>
            {(options || []).map((opt) => {
              // Support both {value, label} objects and plain strings
              const optValue = typeof opt === "object" ? opt.value : opt;
              const optLabel = typeof opt === "object" ? opt.label : opt;
              return (
                <SelectItem key={optValue} value={optValue}>
                  {optLabel}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
        {hint && <FieldHint>{hint}</FieldHint>}
        {error && <FieldError>{error}</FieldError>}
      </div>
    );
  }

  // ── CHECKBOX (multi-select pills for arrays, toggle for booleans) ──
  if (field_type === "checkbox") {
    // Determine if this is a boolean single checkbox or a multi-select
    const isSingleBoolean =
      field_key === "menor_35_anos" ||
      field_key === "ja_tem_casa_escolhida" ||
      field_key === "consent_data" ||
      field_key === "consent_contact";

    if (isSingleBoolean) {
      return (
        <div className={cn("space-y-2", className)}>
          <div className="flex items-start space-x-3">
            <input
              type="checkbox"
              id={field_key}
              name={field_key}
              checked={!!value}
              onChange={(e) => onChange(field_key, e.target.checked)}
              disabled={disabled}
              className="mt-1 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
              data-testid={`dynamic-${field_key}`}
            />
            <div className="space-y-1">
              <Label htmlFor={field_key} className="text-sm font-medium cursor-pointer">
                {label}
              </Label>
              {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
            </div>
          </div>
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // Multi-select pill buttons (for arrays like bancos_creditos, caracteristicas, etc.)
    const arr = Array.isArray(value) ? value : [];

    return (
      <div className={cn("space-y-2", className)}>
        {is_required ? (
          <RequiredLabel htmlFor={field_key} required={is_required}>
            {label}
          </RequiredLabel>
        ) : (
          <Label>{label}</Label>
        )}
        <div className="flex flex-wrap gap-2">
          {(options || []).map((opt) => {
            const optValue = typeof opt === "object" ? opt.value : opt;
            const optLabel = typeof opt === "object" ? opt.label : opt;
            const checked = arr.includes(optValue);
            return (
              <button
                key={optValue}
                type="button"
                onClick={() => {
                  const updated = checked
                    ? arr.filter((v) => v !== optValue)
                    : [...arr, optValue];
                  onChange(field_key, updated);
                }}
                disabled={disabled}
                className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                  checked
                    ? "ring-2 ring-offset-1 ring-primary scale-105 bg-primary text-primary-foreground border-primary"
                    : "opacity-60 hover:opacity-80 bg-transparent text-foreground border-border"
                }`}
                data-testid={`dynamic-${field_key}-${String(optValue).toLowerCase().replace(/\s+/g, '-')}`}
              >
                {checked && <span className="mr-1">&#10003;</span>}
                {optLabel}
              </button>
            );
          })}
        </div>
        {hint && <FieldHint>{hint}</FieldHint>}
        {error && <FieldError>{error}</FieldError>}
      </div>
    );
  }

  // ── RADIO ────────────────────────────────────────────────────
  if (field_type === "radio") {
    // For generic radio options, render pill-style buttons
    return (
      <div className={cn("space-y-2", className)}>
        {is_required ? (
          <RequiredLabel htmlFor={field_key} required={is_required}>
            {label}
          </RequiredLabel>
        ) : (
          <Label>{label}</Label>
        )}
        <div className="flex flex-wrap gap-2">
          {(options || []).map((opt) => {
            const optValue = typeof opt === "object" ? opt.value : opt;
            const optLabel = typeof opt === "object" ? opt.label : opt;
            const selected = value === optValue;
            return (
              <button
                key={optValue}
                type="button"
                onClick={() => onChange(field_key, optValue)}
                disabled={disabled}
                className={`px-4 py-2 rounded-lg text-sm font-medium border-2 transition-all ${
                  selected
                    ? "ring-2 ring-offset-1 ring-primary scale-105 bg-primary text-primary-foreground border-primary"
                    : "opacity-70 hover:opacity-100 bg-transparent text-foreground border-border hover:border-primary"
                }`}
                data-testid={`dynamic-${field_key}-${String(optValue).toLowerCase().replace(/\s+/g, '-')}`}
              >
                {selected && <span className="mr-1">&#10003;</span>}
                {optLabel}
              </button>
            );
          })}
        </div>
        {hint && <FieldHint>{hint}</FieldHint>}
        {error && <FieldError>{error}</FieldError>}
      </div>
    );
  }

  // ── FALLBACK: text input ─────────────────────────────────────
  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={field_key}>{label}</Label>
      <Input
        id={field_key}
        name={field_key}
        value={value || ""}
        onChange={(e) => onChange(field_key, e.target.value)}
        placeholder={placeholder || ""}
        disabled={disabled}
        className={cn(inputErrorClass)}
        data-testid={`dynamic-${field_key}`}
      />
      {hint && <FieldHint>{hint}</FieldHint>}
      {error && <FieldError>{error}</FieldError>}
    </div>
  );
}
