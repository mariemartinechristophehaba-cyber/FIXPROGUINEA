// @ts-nocheck
'use client';

import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings,
  Search, Bell, MapPin, AlertTriangle, ChevronRight, Menu, X, Filter,
  ChevronLeft, ChevronDown, Clock, Phone, MessageSquare,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useRouter, usePathname } from 'next/navigation';

// ---- Design tokens (v2 — contraste et profondeur renforces) --------------
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

const STATUSES = ['Nouveau', 'Assigne', 'En cours', 'Termine'];

const INTERVENTIONS = [
  { code: 'FP-2026-000012', client: 'Alpha Diallo', phone: '622 00 11 22', pb: 'Porte gatee', cat: 'Menuiserie', tech: 'Kadiatou Barry', techCat: 'Frigoriste', status: 1, dist: '1556 km', date: '25 aout, 21:03', mismatch: true },
  { code: 'FP-2026-000013', client: 'N\'Fansoumane Camara', phone: '628 33 44 55', pb: 'Robinet qui fuit', cat: 'Plomberie', tech: 'Kadiatou Barry', techCat: 'Frigoriste', status: 1, dist: '1556 km', date: '25 aout, 23:04', mismatch: true },
  { code: 'FP-2026-000014', client: 'Mariama Bah', phone: '664 55 66 77', pb: 'Climatiseur en panne', cat: 'Frigoriste', tech: 'Kadiatou Barry', techCat: 'Frigoriste', status: 2, dist: '0.8 km', date: '25 aout, 23:10', mismatch: false },
  { code: 'FP-2026-000015', client: 'Ousmane Kaba', phone: '621 77 88 99', pb: 'Coupure de courant', cat: 'Electricite', tech: 'Fatoumata Camara', techCat: 'Electricien', status: 3, dist: '1.4 km', date: '24 aout, 09:12', mismatch: false },
  { code: 'FP-2026-000016', client: 'Hawa Sylla', phone: '655 12 34 56', pb: 'Serrure bloquee', cat: 'Serrurier', tech: 'Aminata Conde', techCat: 'Serrurier', status: 0, dist: '2.1 km', date: '26 aout, 08:03', mismatch: false },
  { code: 'FP-2026-000017', client: 'Ibrahima Sow', phone: '623 65 43 21', pb: 'Fenetre cassee', cat: 'Menuiserie', tech: 'Ousmane Sylla', techCat: 'Menuisier', status: 2, dist: '3.0 km', date: '26 aout, 07:40', mismatch: false },
  { code: 'FP-2026-000018', client: 'Fatima Bangoura', phone: '666 98 76 54', pb: 'Chaudiere ne demarre plus', cat: 'Chauffagiste', tech: 'Mamadou Diallo', techCat: 'Chauffagiste', status: 1, dist: '4.2 km', date: '26 aout, 06:55', mismatch: false },
  { code: 'FP-2026-000019', client: 'Sekou Toure', phone: '620 11 22 33', pb: 'Prise electrique qui gresille', cat: 'Electricite', tech: 'Mariam Kourouma', techCat: 'Electricien', status: 3, dist: '1.9 km', date: '25 aout, 18:20', mismatch: false },
  { code: 'FP-2026-000020', client: 'Aissatou Barry', phone: '657 44 55 66', pb: 'Peinture facade', cat: 'Peinture', tech: '—', techCat: '—', status: 0, dist: '—', date: '26 aout, 08:41', mismatch: false },
  { code: 'FP-2026-000021', client: 'Mamadou Conde', phone: '628 99 88 77', pb: 'Fuite sous evier', cat: 'Plomberie', tech: 'Ibrahim Sory', techCat: 'Plombier', status: 2, dist: '2.6 km', date: '26 aout, 05:12', mismatch: false },
];

const CANON_PROFESSION = {
  'plomberie': 'plombier',
  'plombier': 'plombier',
  'electricite': 'electricien',
  'electricien': 'electricien',
  'frigoriste': 'frigoriste',
  'menuiserie': 'menuisier',
  'menuisier': 'menuisier',
  'chauffagiste': 'chauffagiste',
  'serrurier': 'serrurier',
  'peinture': 'peintre',
  'peintre': 'peintre',
  'maconnerie': 'macon',
  'maçonnerie': 'maçon',
  'macon': 'maçon',
  'maçon': 'maçon',
};

const LABEL_PROFESSION = {
  'plombier': 'Plomberie',
  'electricien': 'Electricite',
  'frigoriste': 'Froid',
  'menuisier': 'Menuiserie',
  'chauffagiste': 'Chauffagiste',
  'serrurier': 'Serrurier',
  'peintre': 'Peinture',
  'maçon': 'Maçonnerie',
  'macon': 'Maçonnerie',
};

function label(cat) {
  if (!cat) return 'Autre';
  const key = CANON_PROFESSION[cat.toLowerCase()];
  if (key) return LABEL_PROFESSION[key] || key.charAt(0).toUpperCase() + key.slice(1);
  return cat.charAt(0).toUpperCase() + cat.slice(1);
}

function statusIndex(status) {
  if (status === 'completed') return 3;
  if (status === 'in_progress' || status === 'on_the_way') return 2;
  if (status === 'assigned' || status === 'quote_proposed' || status === 'quote_accepted' || status === 'pending') return 1;
  return 0;
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleDateString('fr-FR', { month: 'short' }).replace('.', '');
  const day = d.getDate();
  const hour = d.getHours().toString().padStart(2, '0');
  const min = d.getMinutes().toString().padStart(2, '0');
  return `${day} ${month}, ${hour}:${min}`;
}

function toFloat(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}

function isValidCoord(lat, lon) {
  return lat !== null && lon !== null && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const toRad = (x) => (x * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function distanceFor(row) {
  const clientLat = toFloat(row.latitude);
  const clientLon = toFloat(row.longitude);
  const artLat = toFloat(row.artisan_lat);
  const artLon = toFloat(row.artisan_lon);
  if (isValidCoord(clientLat, clientLon) && isValidCoord(artLat, artLon)) {
    return `${haversine(clientLat, clientLon, artLat, artLon).toFixed(1)} km`;
  }
  return '—';
}

function isMismatch(row) {
  const cat = (row.category || '').toLowerCase();
  const prof = (row.artisan_profession || '').toLowerCase();
  if (!cat || !prof) return false;
  return CANON_PROFESSION[cat] !== CANON_PROFESSION[prof];
}

function mapDemandes(rows) {
  return rows.map((r) => ({
    code: r.reference || `FP-${String(r.id).padStart(6, '0')}`,
    client: r.client_name || '—',
    phone: r.client_phone || '—',
    pb: r.title || '—',
    cat: label(r.category),
    tech: r.artisan_name || '—',
    techCat: r.artisan_profession ? label(r.artisan_profession) : '—',
    status: statusIndex(r.status),
    dist: distanceFor(r),
    date: formatDate(r.updated_at),
    mismatch: isMismatch(r),
  }));
}

function Initials({ name, size = 30, bg = C.brand }) {
  const initials = name === '—' ? '?' : name.split(' ').map((w) => w[0]).slice(0, 2).join('');
  return (
    <div
      className='fx-display flex items-center justify-center rounded-full text-white shrink-0'
      style={{
        width: size, height: size,
        background: name === '—' ? C.inkMuted : bg,
        fontSize: size * 0.36, fontWeight: 700,
        boxShadow: '0 1px 2px rgba(10,14,31,0.15)',
      }}
    >
      {initials}
    </div>
  );
}

function StatusTicket({ index, mismatch }) {
  return (
    <div className='flex items-center gap-1'>
      {STATUSES.map((s, i) => (
        <React.Fragment key={s}>
          <div
            className='rounded-full'
            style={{
              width: 7, height: 7,
              background: i <= index ? (mismatch ? C.red : C.brandLight) : C.borderStrong,
              boxShadow: i <= index ? '0 0 0 2px ' + (mismatch ? C.redBg : '#E4EAFB') : 'none',
            }}
          />
          {i < STATUSES.length - 1 && (
            <div style={{ width: 11, height: 1.5, background: i < index ? (mismatch ? C.red : C.brandLight) : C.borderStrong, borderRadius: 1 }} />
          )}
        </React.Fragment>
      ))}
      <span className='fx-body font-semibold ml-1 text-[10.5px]' style={{ color: mismatch ? C.red : C.inkMuted }}>
        {STATUSES[index]}
      </span>
    </div>
  );
}

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

export default function FixProInterventionsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState('Tous');
  const [interventions, setInterventions] = useState(INTERVENTIONS);
  const [selected, setSelected] = useState(INTERVENTIONS[0]);

  useEffect(() => {
    api.demandes()
      .then((rows) => {
        const mapped = mapDemandes(rows);
        if (mapped.length) {
          setInterventions(mapped);
          setSelected(mapped[0]);
        }
      })
      .catch(console.error);
  }, []);

  const counts = STATUSES.map((s, i) => ({ label: s, n: interventions.filter((x) => x.status === i).length }));
  const filtered = statusFilter === 'Tous' ? interventions : interventions.filter((x) => STATUSES[x.status] === statusFilter);

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
            <h1 className='fx-display font-bold text-[19px]'>Interventions</h1>
            <p className='fx-body text-[12.5px]' style={{ color: C.inkMuted }}>{interventions.length} interventions au total</p>
          </div>
          <div
            className='hidden md:flex items-center gap-2 ml-4 px-3 py-2 rounded-lg flex-1 max-w-xs'
            style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}
          >
            <Search size={15} color={C.inkMuted} />
            <input placeholder='Rechercher un client, une reference...' className='fx-body text-[13px] bg-transparent outline-none w-full' />
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
          <div className='flex flex-wrap gap-2'>
            <button
              onClick={() => setStatusFilter('Tous')}
              className='fx-body font-semibold text-[12.5px] rounded-full px-3.5 py-1.5 transition-colors'
              style={{
                background: statusFilter === 'Tous' ? C.brand : C.surface,
                color: statusFilter === 'Tous' ? '#fff' : C.ink,
                border: `1px solid ${statusFilter === 'Tous' ? C.brand : C.border}`,
                boxShadow: statusFilter === 'Tous' ? SHADOW_SM : 'none',
              }}
            >
              Tous · {interventions.length}
            </button>
            {counts.map((c) => (
              <button
                key={c.label}
                onClick={() => setStatusFilter(c.label)}
                className='fx-body font-semibold text-[12.5px] rounded-full px-3.5 py-1.5 transition-colors'
                style={{
                  background: statusFilter === c.label ? C.brand : C.surface,
                  color: statusFilter === c.label ? '#fff' : C.ink,
                  border: `1px solid ${statusFilter === c.label ? C.brand : C.border}`,
                  boxShadow: statusFilter === c.label ? SHADOW_SM : 'none',
                }}
              >
                {c.label} · {c.n}
              </button>
            ))}

            <div className='ml-auto flex items-center gap-2'>
              <button
                className='fx-body font-medium text-[12.5px] rounded-lg px-3 py-1.5 flex items-center gap-1.5'
                style={{ background: C.surface, border: `1px solid ${C.border}`, color: C.ink, boxShadow: SHADOW_SM }}
              >
                <Filter size={13} /> Categorie <ChevronDown size={13} />
              </button>
              <button
                className='fx-body font-medium text-[12.5px] rounded-lg px-3 py-1.5 flex items-center gap-1.5'
                style={{ background: C.surface, border: `1px solid ${C.border}`, color: C.ink, boxShadow: SHADOW_SM }}
              >
                Technicien <ChevronDown size={13} />
              </button>
            </div>
          </div>

          <div className='grid grid-cols-1 xl:grid-cols-3 gap-5'>
            <div className='xl:col-span-2 rounded-2xl overflow-hidden' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
              <div className='fx-scroll overflow-x-auto'>
                <table className='w-full'>
                  <thead>
                    <tr className='text-left' style={{ borderBottom: `2px solid ${C.border}` }}>
                      {['Ref.', 'Client', 'Categorie', 'Technicien', 'Statut', 'Date', ''].map((h) => (
                        <th key={h} className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((row) => (
                      <tr
                        key={row.code}
                        onClick={() => setSelected(row)}
                        className='fx-row cursor-pointer transition-colors'
                        style={{
                          borderTop: `1px solid ${C.border}`,
                          background: selected?.code === row.code ? C.surfaceAlt : 'transparent',
                        }}
                      >
                        <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{row.code}</td>
                        <td className='px-4 py-3.5 text-[13px] font-medium'>
                          {row.client}
                          <div className='text-[11px] font-normal mt-0.5' style={{ color: C.inkMuted }}>{row.pb}</div>
                        </td>
                        <td className='px-4 py-3.5'>
                          <span className='fx-body font-semibold text-[11px] rounded-full px-2.5 py-1' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>{row.cat}</span>
                        </td>
                        <td className='px-4 py-3.5 text-[12.5px] font-medium'>
                          <div className='flex items-center gap-1.5'>
                            <Initials name={row.tech} size={22} bg={row.mismatch ? C.red : C.brandLight} />
                            <span>{row.tech}</span>
                            {row.mismatch && <AlertTriangle size={12} color={C.red} />}
                          </div>
                        </td>
                        <td className='px-4 py-3.5'><StatusTicket index={row.status} mismatch={row.mismatch} /></td>
                        <td className='px-4 py-3.5 fx-mono font-medium text-[11px]' style={{ color: C.inkMuted }}>{row.date}</td>
                        <td className='px-4 py-3.5'><ChevronRight size={14} color={C.inkMuted} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className='flex items-center justify-between px-4 py-3.5' style={{ borderTop: `1px solid ${C.border}`, background: C.surfaceAlt }}>
                <span className='fx-body font-medium text-[12px]' style={{ color: C.inkMuted }}>Page 1 sur 4</span>
                <div className='flex items-center gap-1.5'>
                  <button className='rounded-lg p-1.5' style={{ border: `1px solid ${C.border}`, background: C.surface }}><ChevronLeft size={14} /></button>
                  <button className='rounded-lg p-1.5' style={{ border: `1px solid ${C.border}`, background: C.surface }}><ChevronRight size={14} /></button>
                </div>
              </div>
            </div>

            <div className='rounded-2xl p-5 flex flex-col gap-4 h-fit' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
              {selected && (
                <>
                  <div className='flex items-start justify-between'>
                    <div>
                      <p className='fx-mono font-medium text-[11px]' style={{ color: C.inkMuted }}>{selected.code}</p>
                      <h3 className='fx-display font-bold text-[16px] mt-0.5'>{selected.client}</h3>
                    </div>
                    <span className='fx-body font-semibold text-[11px] rounded-full px-2.5 py-1' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>{selected.cat}</span>
                  </div>

                  <p className='fx-body text-[13px] font-medium' style={{ color: C.ink }}>{selected.pb}</p>

                  <div className='flex flex-col gap-2 text-[12.5px] font-medium' style={{ color: C.inkMuted }}>
                    <div className='flex items-center gap-2'><Phone size={13} /> {selected.phone}</div>
                    <div className='flex items-center gap-2'><Clock size={13} /> {selected.date}</div>
                    <div className='flex items-center gap-2'><MapPin size={13} /> {selected.dist}</div>
                  </div>

                  {selected.mismatch && (
                    <div className='rounded-xl p-3 flex gap-2' style={{ background: C.redBg, border: `1px solid ${C.red}33` }}>
                      <AlertTriangle size={15} color={C.red} className='shrink-0 mt-0.5' />
                      <p className='fx-body font-medium text-[12px]' style={{ color: C.red }}>
                        Technicien assigne ({selected.techCat}) hors de la categorie demandee ({selected.cat}).
                      </p>
                    </div>
                  )}

                  <div>
                    <p className='fx-body font-semibold text-[11.5px] mb-1.5' style={{ color: C.inkMuted }}>Technicien assigne</p>
                    <div className='flex items-center gap-2 rounded-lg p-2' style={{ border: `1px solid ${C.border}`, background: C.surfaceAlt }}>
                      <Initials name={selected.tech} size={26} bg={selected.mismatch ? C.red : C.brandLight} />
                      <div className='min-w-0 flex-1'>
                        <p className='fx-body font-semibold text-[12.5px] truncate'>{selected.tech}</p>
                        <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>{selected.techCat}</p>
                      </div>
                      <ChevronDown size={14} color={C.inkMuted} />
                    </div>
                  </div>

                  <StatusTicket index={selected.status} mismatch={selected.mismatch} />

                  <div className='flex gap-2 mt-1'>
                    <button className='flex-1 fx-body font-semibold text-[12.5px] rounded-lg py-2.5' style={{ background: C.brand, color: '#fff', boxShadow: '0 2px 6px rgba(22,38,94,0.3)' }}>
                      Reassigner
                    </button>
                    <button className='flex-1 fx-body font-semibold text-[12.5px] rounded-lg py-2.5 flex items-center justify-center gap-1.5' style={{ border: `1px solid ${C.border}`, color: C.ink, background: C.surface }}>
                      <MessageSquare size={13} /> Message
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
