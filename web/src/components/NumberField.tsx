import { useEffect, useState, type InputHTMLAttributes } from "react";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> {
  value: number;
  onChange: (n: number) => void;
}

/** A number input you can clear and retype. The text being typed stays local; the number goes
 *  up only when the text parses, and the text snaps back to the number when the field loses
 *  focus. A plain controlled input turns an empty field into 0 and then shows "04". */
export function NumberField({ value, onChange, onFocus, onBlur, ...rest }: Props) {
  const [draft, setDraft] = useState(String(value));
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setDraft(String(value));
  }, [value, focused]);
  return (
    <input
      {...rest}
      type="number"
      inputMode={rest.inputMode ?? "decimal"}
      value={draft}
      onFocus={(e) => {
        setFocused(true);
        onFocus?.(e);
      }}
      onBlur={(e) => {
        setFocused(false);
        setDraft(String(value));
        onBlur?.(e);
      }}
      onChange={(e) => {
        const text = e.target.value;
        setDraft(text);
        if (text.trim() === "") return;
        const n = Number(text);
        if (Number.isFinite(n)) onChange(n);
      }}
    />
  );
}
