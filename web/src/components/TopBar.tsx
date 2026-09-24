import { UtensilsCrossed } from "lucide-react";
import type { Menu } from "../types";

export function TopBar({ menu, count, onMenu, onParty }: { menu: Menu | null; count: number; onMenu: () => void; onParty: () => void }) {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="brand">
          <span className="brand-mark">
            <UtensilsCrossed size={17} />
          </span>
          <p>Michelin</p>
        </div>
        <nav className="nav-actions" aria-label="Meal controls">
          <button className="btn btn-quiet" onClick={onMenu} disabled={!menu}>
            Menu
          </button>
          <button className="btn btn-quiet" onClick={onParty} disabled={!menu}>
            Your table
            {count > 0 && <span className="guest-count">{count}</span>}
          </button>
        </nav>
      </div>
    </header>
  );
}
