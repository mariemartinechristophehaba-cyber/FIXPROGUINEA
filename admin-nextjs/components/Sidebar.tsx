'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Wrench, ClipboardList, Cpu, Settings, Menu, X, LogOut } from 'lucide-react';

const nav = [
  { href: '/admin/', label: 'Tableau de bord', icon: LayoutDashboard },
  { href: '/admin/techniciens/', label: 'Techniciens', icon: Wrench },
  { href: '/admin/demandes/', label: 'Demandes', icon: ClipboardList },
  { href: '/admin/generateur/', label: 'Generateur', icon: Cpu },
  { href: '/admin/parametres/', label: 'Parametres', icon: Settings },
];

export default function Sidebar() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  const handleLogout = async () => {
    try {
      await fetch('/api/admin/logout', { method: 'POST' });
    } catch {
      // on redirige quand meme
    }
    window.location.href = '/admin/login';
  };

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-surface border border-border rounded"
        aria-label="Menu"
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>

      <aside
        className={`fixed lg:static inset-y-0 left-0 z-40 w-[220px] bg-surface border-r border-border transform transition-transform duration-200 ${
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="h-full flex flex-col">
          <div className="p-6 border-b border-border">
            <h1 className="text-lg font-medium tracking-tight">FixPro <span className="text-muted">Admin</span></h1>
          </div>
          <nav className="flex-1 p-4 space-y-1">
            {nav.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href || pathname.startsWith(item.href.replace(/\/$/, ''));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    active ? 'bg-white/10 text-white' : 'text-muted hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon size={18} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="p-4 border-t border-border">
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 px-3 py-2 text-sm text-muted hover:text-white transition-colors w-full"
            >
              <LogOut size={18} />
              Deconnexion
            </button>
          </div>
        </div>
      </aside>

      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}
    </>
  );
}
