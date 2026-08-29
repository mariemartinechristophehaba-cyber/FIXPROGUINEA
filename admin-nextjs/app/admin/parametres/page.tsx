// @ts-nocheck
'use client';

import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings, MessageSquare,
  Bell, Shield, Database, Mail, Percent, Globe, AlertCircle,
  ChevronRight, Menu, X, ExternalLink,
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

function SettingCard({ icon: Icon, label, value, color, hint }) {
  return (
    <div className='rounded-2xl p-5 flex flex-col gap-2' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}>
      <div className='flex items-center gap-2' style={{ color: color || C.inkMuted }}>
        <Icon size={16} />
        <span className='fx-body font-semibold text-[12px] uppercase tracking-wider'>{label}</span>
      </div>
      <p className='fx-display font-bold text-[18px] break-words' style={{ color: C.ink }}>{value}</p>
      {hint && <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>{hint}</p>}
    </div>
  );
}

export default function FixProParametresPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [params, setParams] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.parametres()
      .then(setParams)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const commissionPct = params ? `${Math.round(params.commission_rate * 100)}%` : '—';
  const envLabel = params ? (params.environment === 'production' ? 'Production' : 'Developpement') : '—';
  const dbLabel = params ? (params.database_url === 'configure' ? 'PostgreSQL / Supabase' : 'SQLite local') : '—';

  return (
    <div className='fx-body w-full min-h-[760px] flex' style={{ background: C.bg, color: C.ink }}>
      <style dangerouslySetInnerHTML={{ __html: FONT_STYLE }} />

      <aside
        className={`fixed top-0 left-0 z-20 h-screen transition-transform duration-200 ${navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
        style={{ width: 220, background: C.brandDark, boxShadow: SHADOW_MD }}
      >
        <div className='flex items-center gap-2 px-5 py-5' style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div className='flex items-center justify-center rounded-lg' style={{ width: 28, height: 28, background: C.brandLight }}>
            <Settings size={15} color='#fff' />
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
            <h1 className='fx-display font-bold text-[19px]'>Parametres</h1>
            <p className='fx-body text-[12.5px]' style={{ color: C.inkMuted }}>Configuration de la plateforme</p>
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
          {loading && <div className='p-8 text-center' style={{ color: C.inkMuted }}>Chargement...</div>}

          {!loading && (
            <>
              <div className='grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4'>
                <SettingCard icon={Percent} label='Commission FixPro' value={commissionPct} color={C.amber} hint='Prelevement sur chaque intervention' />
                <SettingCard icon={Globe} label='Environnement' value={envLabel} color={C.brandLight} />
                <SettingCard icon={Database} label='Base de donnees' value={dbLabel} color={C.green} />
                <SettingCard icon={Shield} label='Niveau de logs' value={params?.log_level || '—'} color={C.inkMuted} />
                <SettingCard icon={Mail} label='Email admin' value={params?.admin_email || 'Non configure'} color={C.red} />
                <SettingCard icon={Globe} label='URL admin' value={params?.admin_dashboard_url || '—'} color={C.brandLight} hint='Redirection du /admin Flask' />
              </div>

              <div className='rounded-2xl p-5' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}>
                <h2 className='fx-display font-bold text-[16px] mb-3'>Modifier la configuration</h2>
                <p className='fx-body text-[13px] mb-4' style={{ color: C.inkMuted }}>
                  Les variables d'environnement (BASE, ADMIN_API_KEY, SECRET_KEY, DATABASE_URL, FIXPRO_COMMISSION_RATE)
                  sont definies dans le tableau de bord Vercel du projet backend.
                </p>
                <a
                  href='https://vercel.com/dashboard'
                  target='_blank'
                  rel='noopener noreferrer'
                  className='inline-flex items-center gap-2 fx-body font-semibold text-[13px] rounded-lg px-4 py-2.5'
                  style={{ background: C.brand, color: '#fff', boxShadow: SHADOW_SM }}
                >
                  Ouvrir Vercel <ExternalLink size={14} />
                </a>
              </div>

              <div className='rounded-2xl p-5' style={{ background: C.amberBg, border: `1px solid ${C.amber}33`, boxShadow: SHADOW_SM }}>
                <div className='flex items-start gap-3'>
                  <AlertCircle size={20} color={C.amber} />
                  <div>
                    <h3 className='fx-display font-bold text-[14px]' style={{ color: C.ink }}>Notes de securite</h3>
                    <ul className='fx-body text-[12.5px] mt-1 list-disc list-inside' style={{ color: C.inkMuted }}>
                      <li>Ne partage jamais ADMIN_API_KEY dans le code.</li>
                      <li>SECRET_KEY doit etre fixe en production.</li>
                      <li>En production, le fichier systeme est en lecture seule.</li>
                    </ul>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
