"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/", label: "Overview", mark: "OV" },
  { href: "/opportunities", label: "Opportunities", mark: "OP" },
  { href: "/signals", label: "Signals", mark: "SG" },
  { href: "/research", label: "Research", mark: "RS" },
  { href: "/operations", label: "Operations", mark: "OS" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Opportunity Research OS home">
          <span className="brand-glyph" aria-hidden="true">
            OR
          </span>
          <span>
            <strong>Opportunity</strong>
            <small>Research OS</small>
          </span>
        </Link>
        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                className={active ? "nav-link is-active" : "nav-link"}
                href={item.href}
                key={item.href}
              >
                <span className="nav-mark">{item.mark}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className="pulse-dot" />
          <span>
            Research cycle
            <small>Runs every 6 hours</small>
          </span>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="topbar-kicker">Evidence control room</span>
            <strong>Decide what deserves to exist.</strong>
          </div>
          <div className="topbar-actions">
            <kbd>⌘ K</kbd>
            <button className="avatar" type="button" aria-label="Open account menu">
              GF
            </button>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
