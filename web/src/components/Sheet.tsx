import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

/** A drawer from the right. Every panel uses it, so the menu, the table and the ticket behave alike. */
export function Sheet({ title, onClose, children, wide = false }: {
  title: string; onClose: () => void; children: ReactNode; wide?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (!panel.current?.contains(document.activeElement)) return;
      if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); close.current(); }
      if (e.key === "Tab") {
        const nodes = [...panel.current.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]')].filter(el => el.getClientRects().length);
        const first = nodes[0], last = nodes.at(-1);
        if (!first) { e.preventDefault(); return; }
        if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prevOverflow; if (previous?.isConnected) previous.focus(); };
  }, []);
  return <div className="overlay" onClick={onClose}>
    <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()} className={`dialog ${wide ? "dialog-wide" : ""}`}>
      <div className="dialog-heading"><h2>{title}</h2><button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><X size={20}/></button></div>
      {children}
    </div>
  </div>;
}
