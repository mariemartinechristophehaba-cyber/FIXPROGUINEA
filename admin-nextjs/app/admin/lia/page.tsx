// @ts-nocheck
'use client';

import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings, MessageSquare,
  Bell, Search, ChevronRight, Menu, X,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useRouter, usePathname } from 'next/navigation';

const C = {
  bg: '#EEF0F5',
  surface: '#FFFFFF',
  surfaceAlt: '#F4F5FA',
  border: '#DDE1EA',
  borderStrong: '#C6CBD9',
  ink: '#0A0E1F',
  inkMuted: '#585F73',
  brand: '#16265E',
  brandLight: '#2C4CB0',
  brandDark: '#0E1A44',
  amber: '#DB8A1F',
  amberBg: '#FBF0DD',
  green: '#0F7A52',
  greenBg: '#E1F3EA',
  red: '#B3271D',
  redBg: '#FBE5E3',
  blueBg: '#E4EAFB',
};

const SHADOW_SM = '0 1px 2px rgba(10,14,31,0.04), 0 2px 8px -2px rgba(10,14,31,0.06)';
const SHADOW_MD = '0 2px 4px rgba(10,14,31,0.05), 0 8px 20px -6px rgba(10,14,31,0.10)';

const FONT_STYLE = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .fx-display { font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.01em; }
  .fx-body { font-family: 'Inter', sans-serif; }
  .fx-mono { font-family: 'JetBrains Mono', monospace; font-feature-settings: 'tnum'; }
  .fx-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
  .fx-scroll::-webkit-scrollbar-thumb { background: ${C.borderStrong}; border-radius: 4px; }
  .fx-row:hover { background: ${C.surfaceAlt} !important; }
  .fx-navlink:hover { background: rgba(255,255,255,0.08); }
`;

const NAV = [
  { label: 'Tableau de bord', icon: LayoutDashboard, href: '/admin/dashboard' },
  { label: 'Interventions', icon: Wrench, href: '/admin/interventions' },
  { label: 'Techniciens', icon: Users, href: '/admin/techniciens' },
  { label: 'Clients', icon: UserRound, href: '/admin/clients' },
  { label: 'Categories', icon: Grid3x3, href: '/admin/categories' },
  { label: 'Paiements', icon: Wallet, href: '/admin/paiements' },
  { label: 'Conversations IA', icon: MessageSquare, href: '/admin/lia' },
  { label: 'Parametres', icon: Settings, href: '/admin/parametres' },
];

const FILTER_TABS = ['Tous', 'Ouverts', 'En cours', 'Fermes'];

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleDateString('fr-FR', { month: 'short' }).replace('.', '');
  return `${d.getDate()} ${month} ${d.getFullYear()}, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function statusLabel(status) {
  if (status === 'open') return 'Ouvert';
  if (status === 'handling') return 'En cours';
  if (status === 'closed') return 'Ferme';
  return status;
}

function statusColor(status) {
  if (status === 'open') return { bg: C.amberBg, color: C.amber };
  if (status === 'handling') return { bg: C.blueBg, color: C.brandLight };
  return { bg: C.greenBg, color: C.green };
}

function Badge({ color, bg, children }) {
  return (
    <span className='fx-body font-semibold text-[11px] rounded-full px-2.5 py-1' style={{ background: bg, color, border: `1px solid ${color}33` }}>
      {children}
    </span>
  );
}

export default function FixProLiaPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [filter, setFilter] = useState('Tous');
  const [search, setSearch] = useState('');
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    const status = { 'Tous': 'all', 'Ouverts': 'open', 'En cours': 'handling', 'Fermes': 'closed' }[filter];
    const q = search ? `&q=${encodeURIComponent(search)}` : '';
    api.liaLogs(`status=${status}${q}`)
      .then(setLogs)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [filter, search]);

  const handleTake = (id) => {
    api.takeLiaLog(id)
      .then(load)
      .catch(console.error);
  };

  const handleClose = (id) => {
    api.closeLiaLog(id)
      .then(load)
      .catch(console.error);
  };

  const counts = {
    total: logs.length,
    open: logs.filter((l) => l.status === 'open').length,
    handling: logs.filter((l) => l.status === 'handling').length,
    closed: logs.filter((l) => l.status === 'closed').length,
  };

  return (
    <div className='fx-body w-full min-h-[760px] flex' style={{ background: C.bg, color: C.ink }}>
      <style dangerouslySetInnerHTML={{ __html: FONT_STYLE }} />

      <aside
        className={`fixed lg:static z-20 h-full lg:h-auto transition-transform duration-200 ${navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
        style={{ width: 220, background: C.brandDark, boxShadow: SHADOW_MD }}
      >
        <div className='flex items-center gap-2 px-5 py-5' style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div className='flex items-center justify-center rounded-lg' style={{ width: 28, height: 28, background: C.brandLight }}>
            <MessageSquare size={15} color='#fff' />
          </div>
          <span className='fx-display font-bold text-white text-[16px]'>FixPro <span style={{ color: C.amber }}>Admin</span></span>
          <button className='ml-auto lg:hidden text-white' onClick={() => setNavOpen(false)}><X size={18} /></button>
        </div>
        <nav className='px-3 mt-3 flex flex-col gap-0.5'>
          {NAV.map(({ label, icon: Icon, href }) => {
            const active = pathname === href || pathname.startsWith(href + '/');
            return (
              <button
                key={label}
                onClick={() => router.push(href)}
                className='fx-navlink flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors'
                style={{
                  background: active ? C.brandLight : 'transparent',
                  color: active ? '#fff' : 'rgba(255,255,255,0.68)',
                  boxShadow: active ? '0 2px 6px rgba(44,76,176,0.4)' : 'none',
                  fontWeight: active ? 600 : 500,
                }}
              >
                <Icon size={16} strokeWidth={active ? 2.4 : 2} />
                <span className='fx-body text-[13px]'>{label}</span>
                {active && <ChevronRight size={13} className='ml-auto' />}
              </button>
            );
          })}
        </nav>
      </aside>
      {navOpen && <div className='fixed inset-0 bg-black/40 z-10 lg:hidden' onClick={() => setNavOpen(false)} />}

      <main className='flex-1 min-w-0 flex flex-col'>
        <div
          className='flex items-center gap-4 px-5 lg:px-8 py-4 sticky top-0 z-10'
          style={{ background: 'rgba(238,240,245,0.92)', backdropFilter: 'blur(6px)', borderBottom: `1px solid ${C.border}` }}
        >
          <button className='lg:hidden' onClick={() => setNavOpen(true)}><Menu size={20} /></button>
          <div>
            <h1 className='fx-display font-bold text-[19px]'>Conversations IA</h1>
            <p className='fx-body text-[12.5px]' style={{ color: C.inkMuted }}>{logs.length} echanges</p>
          </div>
          <div
            className='hidden md:flex items-center gap-2 ml-4 px-3 py-2 rounded-lg flex-1 max-w-xs'
            style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}
          >
            <Search size={15} color={C.inkMuted} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder='Rechercher un message...'
              className='fx-body text-[13px] bg-transparent outline-none w-full'
            />
          </div>
          <div className='ml-auto flex items-center gap-4'>
            <button className='relative'>
              <Bell size={19} color={C.inkMuted} />
              <span
                className='absolute -top-1 -right-1 rounded-full text-white flex items-center justify-center fx-mono font-semibold'
                style={{ width: 15, height: 15, fontSize: 9, background: C.red, boxShadow: '0 0 0 2px ' + C.bg }}
              >
                {counts.open || 0}
              </span>
            </button>
          </div>
        </div>

        <div className='p-5 lg:p-8 flex flex-col gap-5 fx-scroll overflow-y-auto'>
          <div className='grid grid-cols-2 md:grid-cols-4 gap-3'>
            {[
              { label: 'Total', value: counts.total },
              { label: 'Ouverts', value: counts.open, color: C.amber },
              { label: 'En cours', value: counts.handling, color: C.brandLight },
              { label: 'Fermes', value: counts.closed, color: C.green },
            ].map((k) => (
              <div key={k.label} className='rounded-xl p-4' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}>
                <p className='fx-body text-[12px]' style={{ color: C.inkMuted }}>{k.label}</p>
                <p className='fx-display text-[18px] font-bold mt-0.5' style={{ color: k.color || C.ink }}>{k.value}</p>
              </div>
            ))}
          </div>

          <div className='flex flex-wrap gap-2 items-center'>
            {FILTER_TABS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className='fx-body font-semibold text-[12.5px] rounded-full px-3.5 py-1.5 transition-colors'
                style={{
                  background: filter === f ? C.brand : C.surface,
                  color: filter === f ? '#fff' : C.ink,
                  border: `1px solid ${filter === f ? C.brand : C.border}`,
                  boxShadow: filter === f ? SHADOW_SM : 'none',
                }}
              >
                {f}
              </button>
            ))}
          </div>

          <div className='rounded-2xl overflow-hidden' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
            <div className='fx-scroll overflow-x-auto'>
              <table className='w-full'>
                <thead>
                  <tr className='text-left' style={{ borderBottom: `2px solid ${C.border}` }}>
                    <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>Client</th>
                    <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>Message</th>
                    <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>Reponse</th>
                    <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>Statut</th>
                    <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>Date</th>
                    <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}></th>
                  </tr>
                </thead>
                <tbody>
                  {loading && (
                    <tr>
                      <td colSpan={6} className='px-4 py-8 text-center fx-body text-[13px]' style={{ color: C.inkMuted }}>Chargement...</td>
                    </tr>
                  )}
                  {!loading && logs.map((l) => {
                    const st = statusColor(l.status);
                    return (
                      <tr
                        key={l.id}
                        className='fx-row transition-colors'
                        style={{ borderTop: `1px solid ${C.border}` }}
                      >
                        <td className='px-4 py-3.5 text-[13px] font-medium'>
                          <div>{l.client_name || 'Visiteur'}</div>
                          <div className='text-[10.5px] fx-mono' style={{ color: C.inkMuted }}>{l.session_id?.slice(-8) || '—'}</div>
                        </td>
                        <td className='px-4 py-3.5 fx-body text-[12.5px]' style={{ maxWidth: 240 }}>{l.message}</td>
                        <td className='px-4 py-3.5 fx-body text-[12.5px]' style={{ color: C.inkMuted, maxWidth: 240 }}>{l.reply}</td>
                        <td className='px-4 py-3.5'><Badge color={st.color} bg={st.bg}>{statusLabel(l.status)}</Badge></td>
                        <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{formatDate(l.created_at)}</td>
                        <td className='px-4 py-3.5'>
                          <div className='flex gap-2'>
                            {l.status !== 'handling' && (
                              <button
                                onClick={() => handleTake(l.id)}
                                className='fx-body font-semibold text-[10.5px] rounded px-2 py-1'
                                style={{ background: C.brand, color: '#fff' }}
                              >
                                Prendre
                              </button>
                            )}
                            {l.status !== 'closed' && (
                              <button
                                onClick={() => handleClose(l.id)}
                                className='fx-body font-semibold text-[10.5px] rounded px-2 py-1'
                                style={{ background: C.green, color: '#fff' }}
                              >
                                Fermer
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
