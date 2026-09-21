import { BookOpen, ChevronDown, ReceiptText, SlidersHorizontal, UtensilsCrossed, Users } from "lucide-react";
import type { Menu, DiningSettings } from "../types";
import { currencySymbol, money } from "../lib/format";

export function TopBar({ menu, count, settings, total, onMenu, onParty, onOrder, canOrder }: {
  menu: Menu | null; count: number; settings: DiningSettings; total?: number;
  onMenu: () => void; onParty: () => void; onOrder: () => void; canOrder: boolean;
}) {
  return <header className="topbar"><div className="topbar-inner">
    <div className="brand"><span className="brand-mark"><UtensilsCrossed size={22}/></span><div><p>Michelin<span className="brand-note">FOR THE TABLE</span></p>
      <button className="restaurant-link" onClick={onMenu}><BookOpen size={13}/>{menu?.restaurant_name ?? "Choose a restaurant"}<ChevronDown size={13}/></button>
    </div></div>
    <div className="nav-actions"><span className="nav-total">{count} diners <span>·</span> {money(total ?? settings.budget * count, currencySymbol(menu?.currency ?? "USD"))}{total == null ? " budget" : " total"}</span>
      <button className="btn btn-quiet" onClick={onParty} aria-label="Party & budget"><SlidersHorizontal size={16}/><span className="desktop-label">Party & budget</span><Users size={16} className="mobile-label"/></button>
      <button className="btn btn-paper" onClick={onOrder} disabled={!canOrder}><ReceiptText size={16}/><span>Order ticket</span></button>
    </div>
  </div></header>;
}
