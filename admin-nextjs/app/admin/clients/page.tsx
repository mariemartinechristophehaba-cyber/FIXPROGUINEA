// @ts-nocheck
'use client';

import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings, MessageSquare,
  Search, Bell, Phone, Mail, MapPin, Calendar, FileText, Copy,
  ChevronRight, ChevronDown, ChevronUp, Menu, X,
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

const FILTER_TABS = ['Tous', 'Avec demandes', 'Sans demande'];

const MOCK = [
  { id: 1, full_name: 'Amadou Diallo', phone: '+224620000001', email: 'amadou@fixpro.gn', address: 'Conakry', created_at: '2026-08-14T10:00:00', request_count: 4, last_request: '2026-08-25T10:00:00' },
  { id: 2, full_name: 'N\'Fansoumane Camara', phone: '+224620000002', email: 'nfansoumane@fixpro.gn', address: 'Kaloum', created_at: '2026-08-15T10:00:00', request_count: 2, last_request: '2026-08-24T10:00:00' },
  { id: 3, full_name: 'Ousmane Kaba', phone: '+224621778899', email: 'ousmane@fixpro.gn', address: 'Dixinn', created_at: '2026-08-16T10:00:00', request_count: 1, last_request: '2026-08-24T09:12:00' },
];

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleDateString('fr-FR', { month: 'short' }).replace('.', '');
  return `${d.getDate()} ${month} ${d.getFullYear()}`;
}

function formatShortDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleDateString('fr-FR', { month: 'short' }).replace('.', '');
  return `${d.getDate()} ${month}`;
}

function statusLabel(status) {
  if (status === 'completed') return 'Termine';
  if (status === 'in_progress' || status === 'on_the_way') return 'En cours';
  if (status === 'assigned' || status === 'quote_proposed' || status === 'quote_accepted' || status === 'pending') return 'Assigne';
  return 'Nouveau';
}

function statusColor(status) {
  if (status === 'completed') return { bg: C.greenBg, color: C.green };
  if (status === 'in_progress' || status === 'on_the_way') return { bg: C.blueBg, color: C.brandLight };
  if (status === 'assigned' || status === 'quote_proposed' || status === 'quote_accepted' || status === 'pending') return { bg: C.amberBg, color: C.amber };
  return { bg: C.surfaceAlt, color: C.inkMuted };
}

function labelProfession(p) {
  if (!p) return 'Autre';
  return p.charAt(0).toUpperCase() + p.slice(1);
}

function Initials({ name, size = 32, bg = C.brand }) {
  const initials = name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
  return (
    <div
      className='fx-display flex items-center justify-center rounded-full text-white shrink-0'
      style={{
        width: size, height: size,
        background: bg,
        fontSize: size * 0.36, fontWeight: 700,
        boxShadow: '0 1px 2px rgba(10,14,31,0.15)',
      }}
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

function Copyable({ value, icon: Icon }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    if (!value || value === '—') return;
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className='flex items-center gap-2 group cursor-pointer' onClick={handleCopy}>
      {Icon && <Icon size={13} />}
      <span>{value}</span>
      <Copy size={12} color={copied ? C.green : C.inkMuted} className='opacity-0 group-hover:opacity-100 transition-opacity' />
      {copied && <span className='fx-body text-[10px]' style={{ color: C.green }}>copie</span>}
    </div>
  );
}

const SORTABLE = [
  { key: 'full_name', label: 'Client' },
  { key: 'phone', label: 'Telephone' },
  { key: 'request_count', label: 'Demandes' },
  { key: 'last_request', label: 'Derniere demande' },
  { key: 'created_at', label: 'Inscription' },
];

export default function FixProClientsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [filter, setFilter] = useState('Tous');
  const [search, setSearch] = useState('');
  const [clients, setClients] = useState(MOCK);
  const [demandes, setDemandes] = useState([]);
  const [selected, setSelected] = useState(MOCK[0]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState('created_at');
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    Promise.all([api.clients(), api.demandes()])
      .then(([clientRows, demandeRows]) => {
        const mapped = clientRows.map((r) => ({
          ...r,
          request_count: parseInt(r.request_count || 0, 10),
        }));
        if (mapped.length) {
          setClients(mapped);
          setSelected(mapped[0]);
        }
        setDemandes(demandeRows);
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
      setSortAsc(true);
    }
  };

  const filtered = clients.filter((c) => {
    if (search && !c.full_name.toLowerCase().includes(search.toLowerCase()) && !c.phone.includes(search)) return false;
    if (filter === 'Avec demandes' && c.request_count === 0) return false;
    if (filter === 'Sans demande' && c.request_count > 0) return false;
    return true;
  }).sort((a, b) => {
    let av = a[sortKey];
    let bv = b[sortKey];
    if (typeof av === 'string') {
      av = av.toLowerCase();
      bv = bv.toLowerCase();
    }
    if (av === null || av === undefined) av = '';
    if (bv === null || bv === undefined) bv = '';
    if (av < bv) return sortAsc ? -1 : 1;
    if (av > bv) return sortAsc ? 1 : -1;
    return 0;
  });

  const clientRequests = demandes.filter((d) => d.client_id === selected?.id).slice(0, 6);

  const counts = {
    total: clients.length,
    withRequests: clients.filter((c) => c.request_count > 0).length,
    withoutRequests: clients.filter((c) => c.request_count === 0).length,
  };

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
            <h1 className='fx-display font-bold text-[19px]'>Clients</h1>
            <p className='fx-body text-[12.5px]' style={{ color: C.inkMuted }}>{counts.total} clients inscrits</p>
          </div>
          <div
            className='hidden md:flex items-center gap-2 ml-4 px-3 py-2 rounded-lg flex-1 max-w-xs'
            style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}
          >
            <Search size={15} color={C.inkMuted} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder='Rechercher un client...'
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
          <div className='grid grid-cols-2 md:grid-cols-3 gap-3'>
            {[
              { label: 'Inscrits', value: counts.total, color: C.ink },
              { label: 'Avec demandes', value: counts.withRequests, color: C.green },
              { label: 'Sans demande', value: counts.withoutRequests, color: C.inkMuted },
            ].map((k) => (
              <div key={k.label} className='rounded-xl p-4' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}>
                <p className='fx-body text-[12px]' style={{ color: C.inkMuted }}>{k.label}</p>
                <p className='fx-display text-[22px] font-bold mt-0.5' style={{ color: k.color }}>{k.value}</p>
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
                {f === 'Tous' ? `${f} · ${clients.length}` : f}
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
                    {!loading && filtered.map((c) => (
                      <tr
                        key={c.id}
                        onClick={() => setSelected(c)}
                        className='fx-row cursor-pointer transition-colors'
                        style={{
                          borderTop: `1px solid ${C.border}`,
                          background: selected?.id === c.id ? C.surfaceAlt : 'transparent',
                        }}
                      >
                        <td className='px-4 py-3.5 text-[13px] font-medium'>
                          <div className='flex items-center gap-2'>
                            <Initials name={c.full_name} size={26} bg={c.request_count ? C.brandLight : C.inkMuted} />
                            <div>
                              {c.full_name}
                              <div className='text-[11px] font-normal' style={{ color: C.inkMuted }}>{c.email || '—'}</div>
                            </div>
                          </div>
                        </td>
                        <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{c.phone}</td>
                        <td className='px-4 py-3.5'>
                          {c.request_count > 0 ? (
                            <Badge color={C.brandLight} bg={C.blueBg}>{c.request_count} demande{c.request_count > 1 ? 's' : ''}</Badge>
                          ) : (
                            <Badge color={C.inkMuted} bg={C.surfaceAlt}>Aucune</Badge>
                          )}
                        </td>
                        <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{formatShortDate(c.last_request)}</td>
                        <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{formatShortDate(c.created_at)}</td>
                        <td className='px-4 py-3.5'><ChevronRight size={14} color={C.inkMuted} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className='rounded-2xl p-5 flex flex-col gap-4 h-fit' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
              {selected && (
                <>
                  <div className='flex items-start justify-between'>
                    <div className='flex items-center gap-3'>
                      <Initials name={selected.full_name} size={48} bg={selected.request_count ? C.brandLight : C.inkMuted} />
                      <div>
                        <h3 className='fx-display font-bold text-[16px]'>{selected.full_name}</h3>
                        <p className='fx-body text-[12px]' style={{ color: C.inkMuted }}>{selected.email || '—'}</p>
                      </div>
                    </div>
                    {selected.request_count > 0 ? (
                      <Badge color={C.brandLight} bg={C.blueBg}>{selected.request_count} demande{selected.request_count > 1 ? 's' : ''}</Badge>
                    ) : (
                      <Badge color={C.inkMuted} bg={C.surfaceAlt}>Aucune</Badge>
                    )}
                  </div>

                  <div className='flex flex-col gap-2 text-[12.5px] font-medium' style={{ color: C.inkMuted }}>
                    <Copyable value={selected.phone} icon={Phone} />
                    <Copyable value={selected.email} icon={Mail} />
                    <div className='flex items-center gap-2'><MapPin size={13} /> {selected.address || '—'}</div>
                    <div className='flex items-center gap-2'><Calendar size={13} /> Inscrit le {formatDate(selected.created_at)}</div>
                  </div>

                  <div className='grid grid-cols-2 gap-3'>
                    <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                      <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>Demandes</p>
                      <p className='fx-display text-[20px] font-bold'>{selected.request_count}</p>
                    </div>
                    <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                      <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>Derniere demande</p>
                      <p className='fx-display text-[20px] font-bold'>{formatDate(selected.last_request)}</p>
                    </div>
                  </div>

                  <div>
                    <p className='fx-body font-semibold text-[11.5px] mb-1.5' style={{ color: C.inkMuted }}>Dernieres demandes</p>
                    <div className='flex flex-col gap-2'>
                      {clientRequests.length === 0 && (
                        <p className='fx-body text-[12px]' style={{ color: C.inkMuted }}>Aucune demande pour ce client.</p>
                      )}
                      {clientRequests.map((d) => {
                        const st = statusColor(d.status);
                        return (
                          <div
                            key={d.id}
                            onClick={() => router.push('/admin/interventions')}
                            className='rounded-lg p-2.5 cursor-pointer transition-colors'
                            style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
                          >
                            <div className='flex items-center justify-between'>
                              <p className='fx-mono font-medium text-[10.5px]' style={{ color: C.inkMuted }}>{d.reference || `FP-${String(d.id).padStart(6, '0')}`}</p>
                              <Badge color={st.color} bg={st.bg}>{statusLabel(d.status)}</Badge>
                            </div>
                            <p className='fx-body text-[12.5px] font-medium mt-0.5' style={{ color: C.ink }}>{d.title}</p>
                            <div className='flex items-center justify-between mt-1'>
                              <span className='fx-body text-[11px]' style={{ color: C.inkMuted }}>{labelProfession(d.category)} {d.artisan_name ? `· ${d.artisan_name}` : ''}</span>
                              <span className='fx-body text-[10px]' style={{ color: C.inkMuted }}>{formatShortDate(d.created_at)}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <p className='fx-mono text-[10px]' style={{ color: C.inkMuted }}>ID client #{String(selected.id).padStart(6, '0')}</p>
                </>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
