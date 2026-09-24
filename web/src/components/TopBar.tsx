import { BookOpen, ReceiptText, Users, UtensilsCrossed } from "lucide-react";
import type { Menu, DiningSettings } from "../types";

export function TopBar({ menu, count, onMenu, onParty, onOrder, canOrder }: {
  menu: Menu | null; count: number; settings: DiningSettings; total?: number;
  onMenu: () => void; onParty: () => void; onOrder: () => void; canOrder: boolean;
}) {
  return <header className="topbar"><div className="topbar-inner">
    <div className="brand"><span className="brand-mark"><UtensilsCrossed size={23}/></span><div><p>Michelin<span className="brand-note">GOOD FOOD, TOGETHER.</span></p><span className="brand-caption">A place for everyone at the table</span></div></div>
    <nav className="nav-actions" aria-label="Meal controls">
      <button className="btn btn-quiet" onClick={onMenu} disabled={!menu}><BookOpen size={17}/><span>Menu</span></button>
      <button className="btn btn-quiet" onClick={onParty} disabled={!menu}><Users size={17}/><span>Your table<span className="guest-count"> · {count}</span></span></button>
      {canOrder && <button className="btn btn-paper header-ticket" onClick={onOrder}><ReceiptText size={17}/><span>Order ticket</span></button>}
    </nav>
  </div></header>;
}
