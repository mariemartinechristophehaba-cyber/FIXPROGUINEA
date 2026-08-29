// @ts-nocheck
'use client';

import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings, MessageSquare,
  Search, Bell, MapPin, AlertTriangle, ArrowUpRight, ArrowDownRight,
  ChevronRight, Circle, Menu, X
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { api } from '@/lib/api';
import { useRouter, usePathname } from 'next/navigation';

const C = {
  bg: '#F4F5F8',
  surface: '#FFFFFF',
  surfaceAlt: '#ECEFF5',
  border: '#E1E4EC',
  ink: '#10162B',
  inkMuted: '#6B7284',
  brand: '#1E3A8A',
  brandLight: '#2F4FB8',
  brandDark: '#152B69',
  amber: '#F0A63A',
  amberBg: '#FDF3E1',
  green: '#16815A',
  greenBg: '#E6F5EE',
  red: '#C4392F',
  redBg: '#FBEAE8',
};

const FONT_STYLE = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
  .fx-display { font-family: 'Space Grotesk', sans-serif; }
  .fx-body { font-family: 'Inter', sans-serif; }
  .fx-mono { font-family: 'JetBrains Mono', monospace; }
  .fx-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
  .fx-scroll::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 4px; }
`;

const CATEGORIES = [
  { name: 'Plomberie', count: 34 },
  { name: 'Électricité', count: 29 },
  { name: 'Frigoriste', count: 21 },
  { name: 'Menuiserie', count: 18 },
  { name: 'Chauffagiste', count: 9 },
  { name: 'Serrurier', count: 12 },
  { name: 'Peinture', count: 3 },
  { name: 'Maçonnerie', count: 2 },
];

const STATUSES = ['Nouveau', 'Assigné', 'En cours', 'Terminé'];

const INTERVENTIONS = [
  { code: 'FP-2026-000012', client: 'Alpha Diallo', pb: 'Porte gâtée', cat: 'Menuiserie', tech: 'Kadiatou Barry', techCat: 'Frigoriste', status: 1, dist: '1556 km', mismatch: true },
  { code: 'FP-2026-000013', client: 'N\'Fansoumane Camara', pb: 'Robinet qui fuit', cat: 'Plomberie', tech: 'Kadiatou Barry', techCat: 'Frigoriste', status: 1, dist: '1556 km', mismatch: true },
  { code: 'FP-2026-000014', client: 'Mariama Bah', pb: 'Climatiseur en panne', cat: 'Frigoriste', tech: 'Kadiatou Barry', techCat: 'Frigoriste', status: 2, dist: '0.8 km', mismatch: false },
  { code: 'FP-2026-000015', client: 'Ousmane Kaba', pb: 'Coupure de courant', cat: 'Électricité', tech: 'Fatoumata Camara', techCat: 'Électricien', status: 3, dist: '1.4 km', mismatch: false },
  { code: 'FP-2026-000016', client: 'Hawa Sylla', pb: 'Serrure bloquée', cat: 'Serrurier', tech: 'Aminata Conde', techCat: 'Serrurier', status: 0, dist: '2.1 km', mismatch: false },
  { code: 'FP-2026-000017', client: 'Ibrahima Sow', pb: 'Fenêtre cassée', cat: 'Menuiserie', tech: 'Ousmane Sylla', techCat: 'Menuisier', status: 2, dist: '3.0 km', mismatch: false },
];

const TECHNICIANS = [
  { name: 'Fatoumata Camara', cat: 'Électricien', online: true },
  { name: 'Kadiatou Barry', cat: 'Frigoriste', online: true },
  { name: 'Ousmane Sylla', cat: 'Menuisier', online: true },
  { name: 'Ibrahim Sory', cat: 'Plombier', online: false },
  { name: 'Aminata Conde', cat: 'Serrurier', online: true },
  { name: 'Mamadou Diallo', cat: 'Chauffagiste', online: false },
];

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

function Initials({ name, size = 34, bg = C.brand }) {
  const initials = name.split(' ').map((w) => w[0]).slice(0, 2).join('');
  return (
    <div
      className='fx-display flex items-center justify-center rounded-full text-white shrink-0'
      style={{ width: size, height: size, background: bg, fontSize: size * 0.38, fontWeight: 600 }}
    >
      {initials}
    </div>
  );
}

function StatusTicket({ index, mismatch }) {
  return (
    <div className='flex items-center gap-1.5'>
      {STATUSES.map((s, i) => (
        <React.Fragment key={s}>
          <div
            className='rounded-full'
            style={{
              width: 7,
              height: 7,
              background: i <= index ? (mismatch ? C.red : C.brand) : C.border,
            }}
            title={s}
          />
          {i < STATUSES.length - 1 && (
            <div
              style={{
                width: 14,
                height: 1,
                background: i < index ? (mismatch ? C.red : C.brand) : C.border,
                borderTop: i >= index ? `1px dashed ${C.border}` : 'none',
              }}
            />
          )}
        </React.Fragment>
      ))}
      <span className='fx-body ml-1.5 text-[11px]' style={{ color: mismatch ? C.red : C.inkMuted }}>
        {STATUSES[index]}
      </span>
    </div>
  );
}

function KpiCard({ label, value, delta, positive, sub }) {
  return (
    <div
      className='rounded-2xl p-5 flex flex-col gap-2'
      style={{ background: C.surface, border: `1px solid ${C.border}` }}
    >
      <span className='fx-body text-[13px]' style={{ color: C.inkMuted }}>{label}</span>
      <div className='flex items-end justify-between'>
        <span className='fx-display text-[26px] leading-none' style={{ color: C.ink }}>{value}</span>
        {delta && (
          <span
            className='fx-mono flex items-center gap-0.5 text-[12px] rounded-full px-1.5 py-0.5'
            style={{
              color: positive ? C.green : C.red,
              background: positive ? C.greenBg : C.redBg,
            }}
          >
            {positive ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {delta}
          </span>
        )}
      </div>
      {sub && <span className='fx-body text-[12px]' style={{ color: C.inkMuted }}>{sub}</span>}
    </div>
  );
}

export default function FixProAdminDashboard() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api.dashboard().then(setData).catch(console.error);
  }, []);

  const dashboard = data || {};

  return (
    <div className='fx-body w-full min-h-[720px] flex' style={{ background: C.bg, color: C.ink }}>
      <style dangerouslySetInnerHTML={{ __html: FONT_STYLE }} />

      <aside
        className={`fixed top-0 left-0 z-20 h-screen flex flex-col overflow-hidden transition-transform duration-200 ${
          navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
        style={{ width: 236, background: C.brandDark }}
      >
        <div className='flex items-center gap-2 px-5 py-5'>
          <div
            className='flex items-center justify-center rounded-lg'
            style={{ width: 30, height: 30, background: C.brandLight }}
          >
            <Wrench size={16} color='#fff' />
          </div>
          <span className='fx-display text-white text-[17px]'>FixPro <span style={{ color: C.amber }}>Admin</span></span>
          <button className='ml-auto lg:hidden text-white' onClick={() => setNavOpen(false)}>
            <X size={18} />
          </button>
        </div>

        <nav className='px-3 mt-3 flex-1 overflow-y-auto flex flex-col gap-0.5'>
          {NAV.map(({ label, icon: Icon, href }) => {
            const active = pathname === href || pathname.startsWith(href + '/');
            return (
              <button
                key={label}
                onClick={() => router.push(href)}
                className='flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors'
                style={{
                  background: active ? 'rgba(255,255,255,0.1)' : 'transparent',
                  color: active ? '#fff' : 'rgba(255,255,255,0.62)',
                }}
              >
                <Icon size={17} />
                <span className='fx-body text-[13.5px]'>{label}</span>
                {active && <ChevronRight size={14} className='ml-auto' />}
              </button>
            );
          })}
        </nav>

        <div
          className='mx-3 mt-6 rounded-xl p-3.5'
          style={{ background: 'rgba(255,255,255,0.06)' }}
        >
          <span className='fx-body text-[12px]' style={{ color: 'rgba(255,255,255,0.55)' }}>
            Guinée · Conakry
          </span>
          <p className='fx-body text-[12.5px] mt-1' style={{ color: 'rgba(255,255,255,0.85)' }}>
            {dashboard.kpis?.techniciens_total !== undefined ? dashboard.kpis.techniciens_total : '—'} techniciens inscrits · {dashboard.kpis?.techniciens_actifs !== undefined ? dashboard.kpis.techniciens_actifs : '—'} actifs cette semaine
          </p>
        </div>
      </aside>

      {navOpen && (
        <div className='fixed inset-0 bg-black/30 z-10 lg:hidden' onClick={() => setNavOpen(false)} />
      )}

      <main className='flex-1 min-w-0 flex flex-col h-screen overflow-y-auto lg:ml-[220px]'>
        <div
          className='flex items-center gap-4 px-5 lg:px-8 py-4 sticky top-0 z-10'
          style={{ background: C.bg, borderBottom: `1px solid ${C.border}` }}
        >
          <button className='lg:hidden' onClick={() => setNavOpen(true)}>
            <Menu size={20} />
          </button>
          <div>
            <h1 className='fx-display text-[19px]'>Tableau de bord</h1>
            <p className='fx-body text-[12.5px]' style={{ color: C.inkMuted }}>Vue d'ensemble · 25 août 2026</p>
          </div>

          <div
            className='hidden md:flex items-center gap-2 ml-4 px-3 py-2 rounded-lg flex-1 max-w-xs'
            style={{ background: C.surface, border: `1px solid ${C.border}` }}
          >
            <Search size={15} color={C.inkMuted} />
            <input
              placeholder='Rechercher une intervention, un technicien…'
              className='fx-body text-[13px] bg-transparent outline-none w-full'
              style={{ color: C.ink }}
            />
          </div>

          <div className='ml-auto flex items-center gap-4'>
            <button className='relative'>
              <Bell size={19} color={C.inkMuted} />
              <span
                className='absolute -top-1 -right-1 rounded-full text-white flex items-center justify-center fx-mono'
                style={{ width: 15, height: 15, fontSize: 9, background: C.red }}
              >
                3
              </span>
            </button>
            <div className='flex items-center gap-2'>
              <Initials name={dashboard.admin || 'Mamadou Bah'} size={32} />
              <span className='fx-body text-[13px] hidden md:block'>{dashboard.admin || 'Mamadou Bah'}</span>
            </div>
          </div>
        </div>

        <div className='p-5 lg:p-8 flex flex-col gap-6 fx-scroll overflow-y-auto'>
          <div className='grid grid-cols-2 lg:grid-cols-4 gap-4'>
            <KpiCard label='Interventions ce mois' value={dashboard.kpis?.interventions_ce_mois !== undefined ? String(dashboard.kpis.interventions_ce_mois) : '—'} sub='vs. mois dernier' />
            <KpiCard label='Revenu (commissions)' value={dashboard.kpis?.revenu_commissions_gnf !== undefined ? `${(dashboard.kpis.revenu_commissions_gnf / 1_000_000).toFixed(1).replace('.', ',')} M GNF` : '—'} sub={`≈ ${dashboard.kpis?.revenu_commissions_usd !== undefined ? String(dashboard.kpis.revenu_commissions_usd) : '—'} USD`} />
            <KpiCard label='Techniciens actifs' value={`${dashboard.kpis?.techniciens_actifs !== undefined ? dashboard.kpis.techniciens_actifs : '—'} / ${dashboard.kpis?.techniciens_total !== undefined ? dashboard.kpis.techniciens_total : '—'}`} sub={"taux d'activation"} />
            <KpiCard label='Taux de résolution' value={dashboard.kpis?.taux_resolution !== undefined ? `${dashboard.kpis.taux_resolution}%` : '—'} sub='interventions terminées' />
          </div>

          <div className='grid grid-cols-1 lg:grid-cols-3 gap-5'>
            <div
              className='lg:col-span-2 rounded-2xl p-5'
              style={{ background: C.surface, border: `1px solid ${C.border}` }}
            >
              <div className='flex items-center justify-between mb-1'>
                <h2 className='fx-display text-[15px]'>Interventions par catégorie</h2>
                <span className='fx-body text-[12px]' style={{ color: C.inkMuted }}>30 derniers jours</span>
              </div>
              <div style={{ height: 240 }}>
                <ResponsiveContainer width='100%' height='100%'>
                  <BarChart data={dashboard.categories || CATEGORIES} margin={{ left: -20, top: 10 }}>
                    <CartesianGrid vertical={false} stroke={C.border} />
                    <XAxis
                      dataKey='name'
                      tick={{ fontSize: 11, fill: C.inkMuted, fontFamily: 'Inter' }}
                      axisLine={{ stroke: C.border }}
                      tickLine={false}
                    />
                    <YAxis tick={{ fontSize: 11, fill: C.inkMuted, fontFamily: 'Inter' }} axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ fill: C.surfaceAlt }}
                      contentStyle={{ borderRadius: 10, border: `1px solid ${C.border}`, fontFamily: 'Inter', fontSize: 12 }}
                    />
                    <Bar dataKey='count' fill={C.brand} radius={[5, 5, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {dashboard.alert ? (
              <div
                className='rounded-2xl p-5 flex flex-col gap-3'
                style={{ background: C.amberBg, border: `1px solid ${C.amber}55` }}
              >
                <div className='flex items-center gap-2'>
                  <AlertTriangle size={16} color={C.amber} />
                  <h2 className='fx-display text-[14px]'>À vérifier</h2>
                </div>
                <p className='fx-body text-[13px] leading-relaxed' style={{ color: C.ink }}>
                  <strong>{dashboard.alert.name}</strong> ({dashboard.alert.cat}) a été assignée à {dashboard.alert.count} intervention{dashboard.alert.count > 1 ? 's' : ''} hors de sa
                  catégorie cette semaine — {dashboard.alert.categories}. Logique de routage à contrôler.
                </p>
                <button
                  className='fx-body text-[12.5px] rounded-lg px-3 py-2 self-start mt-1'
                  style={{ background: C.amber, color: '#fff' }}
                >
                  Voir les interventions concernées
                </button>
              </div>
            ) : (
              <div
                className='rounded-2xl p-5 flex flex-col gap-3'
                style={{ background: C.surface, border: `1px solid ${C.border}` }}
              >
                <h2 className='fx-display text-[14px]'>Routage</h2>
                <p className='fx-body text-[13px] leading-relaxed' style={{ color: C.inkMuted }}>
                  Aucune anomalie de routage détectée cette semaine.
                </p>
              </div>
            )}
          </div>

          <div className='grid grid-cols-1 lg:grid-cols-3 gap-5'>
            <div
              className='lg:col-span-2 rounded-2xl overflow-hidden'
              style={{ background: C.surface, border: `1px solid ${C.border}` }}
            >
              <div className='flex items-center justify-between px-5 py-4' style={{ borderBottom: `1px solid ${C.border}` }}>
                <h2 className='fx-display text-[15px]'>Interventions récentes</h2>
                <button className='fx-body text-[12.5px]' style={{ color: C.brand }}>Voir tout</button>
              </div>
              <div className='fx-scroll overflow-x-auto'>
                <table className='w-full'>
                  <thead>
                    <tr className='text-left'>
                      {['Réf.', 'Client', 'Catégorie', 'Technicien', 'Statut', 'Distance', ''].map((h) => (
                        <th key={h} className='fx-body text-[11px] uppercase tracking-wide px-5 py-2' style={{ color: C.inkMuted }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(dashboard.interventions || INTERVENTIONS).map((row: any) => (
                      <tr key={row.code} style={{ borderTop: `1px solid ${C.border}` }}>
                        <td className='px-5 py-3 fx-mono text-[12px]' style={{ color: C.inkMuted }}>{row.code}</td>
                        <td className='px-5 py-3 text-[13px]'>
                          {row.client}
                          <div className='text-[11.5px]' style={{ color: C.inkMuted }}>{row.pb}</div>
                        </td>
                        <td className='px-5 py-3'>
                          <span
                            className='fx-body text-[11.5px] rounded-full px-2 py-1'
                            style={{ background: C.surfaceAlt, color: C.ink }}
                          >
                            {row.cat}
                          </span>
                        </td>
                        <td className='px-5 py-3 text-[13px]'>
                          <div className='flex items-center gap-2'>
                            <Initials name={row.tech} size={22} bg={row.mismatch ? C.red : C.brandLight} />
                            <span>{row.tech}</span>
                            {row.mismatch && <AlertTriangle size={13} color={C.red} />}
                          </div>
                        </td>
                        <td className='px-5 py-3'><StatusTicket index={row.status} mismatch={row.mismatch} /></td>
                        <td className='px-5 py-3 fx-mono text-[12px] flex items-center gap-1' style={{ color: C.inkMuted }}>
                          <MapPin size={11} /> {row.dist}
                        </td>
                        <td className='px-5 py-3'>
                          <button className='fx-body text-[12px]' style={{ color: C.brand }}>Réassigner</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div
              className='rounded-2xl p-5'
              style={{ background: C.surface, border: `1px solid ${C.border}` }}
            >
              <h2 className='fx-display text-[15px] mb-4'>Techniciens en ligne</h2>
              <div className='flex flex-col gap-3.5'>
                {(dashboard.technicians || TECHNICIANS).map((t: any) => (
                  <div key={t.name} className='flex items-center gap-3'>
                    <div className='relative'>
                      <Initials name={t.name} size={30} bg={t.online ? C.brand : C.inkMuted} />
                      <Circle
                        size={9}
                        fill={t.online ? C.green : C.border}
                        color={t.online ? C.green : C.border}
                        className='absolute -bottom-0.5 -right-0.5'
                        style={{ background: C.surface, borderRadius: '50%' }}
                      />
                    </div>
                    <div className='min-w-0'>
                      <p className='fx-body text-[13px] truncate'>{t.name}</p>
                      <p className='fx-body text-[11.5px]' style={{ color: C.inkMuted }}>{t.cat}</p>
                    </div>
                    <span
                      className='fx-body text-[11px] ml-auto rounded-full px-2 py-0.5'
                      style={{
                        color: t.online ? C.green : C.inkMuted,
                        background: t.online ? C.greenBg : C.surfaceAlt,
                      }}
                    >
                      {t.online ? 'En ligne' : 'Hors ligne'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
