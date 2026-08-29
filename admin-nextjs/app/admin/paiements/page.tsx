// @ts-nocheck
'use client';

import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings, MessageSquare,
  Search, Bell, Phone, Mail, CreditCard, Calendar, FileText,
  ChevronRight, Menu, X, ChevronDown, ChevronUp,
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

const FILTER_TABS = ['Tous', 'Completes', 'En attente', 'Echoues'];

const MOCK = [
  { id: 1, client_name: 'Amadou Diallo', artisan_name: 'Fatou Camara', request_title: 'Fuite sous evier', amount: 125000, commission_amount: 12500, status: 'completed', method: 'cash', created_at: '2026-08-14T10:00:00' },
  { id: 2, client_name: 'Amadou Diallo', artisan_name: 'Ibrahim Sylla', request_title: 'Porte cassee', amount: 95000, commission_amount: 9500, status: 'pending', method: 'mobile_money', created_at: '2026-08-15T10:00:00' },
];

function formatCurrency(value) {
  const n = parseFloat(value || 0);
  return `${n.toLocaleString('fr-FR')} GNF`;
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleDateString('fr-FR', { month: 'short' }).replace('.', '');
  return `${d.getDate()} ${month} ${d.getFullYear()}`;
}

function statusLabel(status) {
  if (status === 'completed') return 'Complete';
  if (status === 'pending') return 'En attente';
  if (status === 'failed' || status === 'cancelled') return 'Echoue';
  return status;
}

function statusColor(status) {
  if (status === 'completed') return { bg: C.greenBg, color: C.green };
  if (status === 'pending') return { bg: C.amberBg, color: C.amber };
  return { bg: C.redBg, color: C.red };
}

function methodLabel(method) {
  if (method === 'mobile_money') return 'Mobile Money';
  if (method === 'card') return 'Carte';
  if (method === 'cash') return 'Espèces';
  return method || '—';
}

function Initials({ name, size = 32, bg = C.brand }) {
  const initials = name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
  return (
    <div
      className='fx-display flex items-center justify-center rounded-full text-white shrink-0'
      style={{ width: size, height: size, background: bg, fontSize: size * 0.36, fontWeight: 700 }}
    >
      {initials}
    </div>
  );
}

function Badge({ color, bg, children }) {
  return (
    <span className='fx-body font-semibold text-[11px] rounded-full px-2.5 py-1' style={{ background: bg, color, border: `1px solid ${color}33` }}>
      {children}
    </span>
  );
}

const SORTABLE = [
  { key: 'client_name', label: 'Client' },
  { key: 'amount', label: 'Montant' },
  { key: 'status', label: 'Statut' },
  { key: 'method', label: 'Methode' },
  { key: 'created_at', label: 'Date' },
];

export default function FixProPaiementsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [filter, setFilter] = useState('Tous');
  const [search, setSearch] = useState('');
  const [paiements, setPaiements] = useState(MOCK);
  const [selected, setSelected] = useState(MOCK[0]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState('created_at');
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    api.paiements()
      .then((rows) => {
        const mapped = rows.map((r) => ({
          ...r,
          amount: parseFloat(r.amount || 0),
          commission_amount: parseFloat(r.commission_amount || 0),
        }));
        if (mapped.length) {
          setPaiements(mapped);
          setSelected(mapped[0]);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(key === 'client_name');
    }
  };

  const filtered = paiements.filter((p) => {
    if (search && !p.client_name?.toLowerCase().includes(search.toLowerCase()) && !p.artisan_name?.toLowerCase().includes(search.toLowerCase()) && !p.request_title?.toLowerCase().includes(search.toLowerCase())) return false;
    if (filter === 'Completes' && p.status !== 'completed') return false;
    if (filter === 'En attente' && p.status !== 'pending') return false;
    if (filter === 'Echoues' && p.status !== 'failed' && p.status !== 'cancelled') return false;
    return true;
  }).sort((a, b) => {
    let av = a[sortKey];
    let bv = b[sortKey];
    if (typeof av === 'string') {
      av = av.toLowerCase();
      bv = (bv || '').toLowerCase();
    }
    if (av === null || av === undefined) av = '';
    if (bv === null || bv === undefined) bv = '';
    if (av < bv) return sortAsc ? -1 : 1;
    if (av > bv) return sortAsc ? 1 : -1;
    return 0;
  });

  const totalAmount = paiements.reduce((acc, p) => acc + p.amount, 0);
  const totalCommission = paiements.reduce((acc, p) => acc + p.commission_amount, 0);
  const completed = paiements.filter((p) => p.status === 'completed').length;
  const pending = paiements.filter((p) => p.status === 'pending').length;

  return (
    <div className='fx-body w-full min-h-[760px] flex' style={{ background: C.bg, color: C.ink }}>
      <style dangerouslySetInnerHTML={{ __html: FONT_STYLE }} />

      <aside
        className={`fixed top-0 left-0 z-20 h-screen transition-transform duration-200 ${navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
        style={{ width: 220, background: C.brandDark, boxShadow: SHADOW_MD }}
      >
        <div className='flex items-center gap-2 px-5 py-5' style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div className='flex items-center justify-center rounded-lg' style={{ width: 28, height: 28, background: C.brandLight }}>
            <Wrench size={15} color='#fff' />
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

      <main className='flex-1 min-w-0 flex flex-col h-screen overflow-y-auto lg:ml-[220px]'>
        <div
          className='flex items-center gap-4 px-5 lg:px-8 py-4 sticky top-0 z-10'
          style={{ background: 'rgba(238,240,245,0.92)', backdropFilter: 'blur(6px)', borderBottom: `1px solid ${C.border}` }}
        >
          <button className='lg:hidden' onClick={() => setNavOpen(true)}><Menu size={20} /></button>
          <div>
            <h1 className='fx-display font-bold text-[19px]'>Paiements</h1>
            <p className='fx-body text-[12.5px]' style={{ color: C.inkMuted }}>{paiements.length} transactions</p>
          </div>
          <div
            className='hidden md:flex items-center gap-2 ml-4 px-3 py-2 rounded-lg flex-1 max-w-xs'
            style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}
          >
            <Search size={15} color={C.inkMuted} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder='Rechercher un client, un technicien...'
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
                3
              </span>
            </button>
            <Initials name='Mamadou Bah' size={30} />
          </div>
        </div>

        <div className='p-5 lg:p-8 flex flex-col gap-5 fx-scroll overflow-y-auto'>
          <div className='grid grid-cols-2 md:grid-cols-4 gap-3'>
            {[
              { label: 'Montant total', value: formatCurrency(totalAmount) },
              { label: 'Commissions', value: formatCurrency(totalCommission), color: C.amber },
              { label: 'Completes', value: completed, color: C.green },
              { label: 'En attente', value: pending, color: C.amber },
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
                {f === 'Tous' ? `${f} · ${paiements.length}` : f}
              </button>
            ))}
          </div>

          <div className='grid grid-cols-1 xl:grid-cols-3 gap-5'>
            <div className='xl:col-span-2 rounded-2xl overflow-hidden' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
              <div className='fx-scroll overflow-x-auto'>
                <table className='w-full'>
                  <thead>
                    <tr className='text-left' style={{ borderBottom: `2px solid ${C.border}` }}>
                      {SORTABLE.map(({ key, label }) => (
                        <th
                          key={key}
                          onClick={() => handleSort(key)}
                          className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3 cursor-pointer select-none'
                          style={{ color: C.inkMuted }}
                        >
                          <div className='flex items-center gap-1'>
                            {label}
                            {sortKey === key && (sortAsc ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                          </div>
                        </th>
                      ))}
                      <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={7} className='px-4 py-8 text-center fx-body text-[13px]' style={{ color: C.inkMuted }}>Chargement...</td>
                      </tr>
                    )}
                    {!loading && filtered.map((p) => {
                      const st = statusColor(p.status);
                      return (
                        <tr
                          key={p.id}
                          onClick={() => setSelected(p)}
                          className='fx-row cursor-pointer transition-colors'
                          style={{
                            borderTop: `1px solid ${C.border}`,
                            background: selected?.id === p.id ? C.surfaceAlt : 'transparent',
                          }}
                        >
                          <td className='px-4 py-3.5 text-[13px] font-medium'>
                            <div>
                              {p.client_name || '—'}
                              <div className='text-[11px] font-normal' style={{ color: C.inkMuted }}>{p.artisan_name || '—'}</div>
                            </div>
                          </td>
                          <td className='px-4 py-3.5 fx-mono font-semibold text-[12px]' style={{ color: C.ink }}>{formatCurrency(p.amount)}</td>
                          <td className='px-4 py-3.5'>
                            <Badge color={st.color} bg={st.bg}>{statusLabel(p.status)}</Badge>
                          </td>
                          <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{methodLabel(p.method)}</td>
                          <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{formatDate(p.created_at)}</td>
                          <td className='px-4 py-3.5'><ChevronRight size={14} color={C.inkMuted} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className='rounded-2xl p-5 flex flex-col gap-4 h-fit' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
              {selected && (
                <>
                  <div className='flex items-start justify-between'>
                    <div className='flex items-center gap-3'>
                      <Initials name={selected.client_name} size={40} bg={selected.status === 'completed' ? C.green : C.amber} />
                      <div>
                        <h3 className='fx-display font-bold text-[16px]'>{selected.client_name || '—'}</h3>
                        <p className='fx-body text-[12px]' style={{ color: C.inkMuted }}>{selected.request_title || '—'}</p>
                      </div>
                    </div>
                    <Badge color={statusColor(selected.status).color} bg={statusColor(selected.status).bg}>{statusLabel(selected.status)}</Badge>
                  </div>

                  <div className='flex flex-col gap-2 text-[12.5px] font-medium' style={{ color: C.inkMuted }}>
                    <div className='flex items-center gap-2'><CreditCard size={13} /> {methodLabel(selected.method)}</div>
                    <div className='flex items-center gap-2'><Calendar size={13} /> {formatDate(selected.created_at)}</div>
                    <div className='flex items-center gap-2'><FileText size={13} /> {selected.reference || '—'}</div>
                  </div>

                  <div className='grid grid-cols-2 gap-3'>
                    <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                      <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>Montant</p>
                      <p className='fx-display text-[18px] font-bold'>{formatCurrency(selected.amount)}</p>
                    </div>
                    <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                      <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>Commission</p>
                      <p className='fx-display text-[18px] font-bold' style={{ color: C.amber }}>{formatCurrency(selected.commission_amount)}</p>
                    </div>
                  </div>

                  <div>
                    <p className='fx-body font-semibold text-[11.5px] mb-1.5' style={{ color: C.inkMuted }}>Technicien</p>
                    <p className='fx-body text-[13px]' style={{ color: C.ink }}>{selected.artisan_name || 'Non assigne'}</p>
                  </div>

                  <p className='fx-mono text-[10px]' style={{ color: C.inkMuted }}>ID transaction #{String(selected.id).padStart(6, '0')}</p>
                </>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
