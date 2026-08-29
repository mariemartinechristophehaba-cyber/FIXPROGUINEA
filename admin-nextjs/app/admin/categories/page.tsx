// @ts-nocheck
'use client';

import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings, MessageSquare,
  Search, Bell, Briefcase, Wrench as WrenchIcon, Snowflake, Hammer, Plug,
  ChevronRight, Menu, X,
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
  .fx-card:hover { transform: translateY(-2px); box-shadow: ${SHADOW_MD}; }
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

const ICONS = {
  plomberie: WrenchIcon,
  electricite: Plug,
  froid: Snowflake,
  menuiserie: Hammer,
};

const NAMES = {
  plomberie: 'Plomberie',
  electricite: 'Electricite',
  froid: 'Froid',
  menuiserie: 'Menuiserie',
  autre: 'Autre',
};

const COLORS = {
  plomberie: '#2C4CB0',
  electricite: '#DB8A1F',
  froid: '#1BA3CC',
  menuiserie: '#8B5CF6',
  autre: '#585F73',
};

const MOCK = [
  { name: 'plomberie', artisan_count: 1, request_count: 2, completed_count: 1 },
  { name: 'electricite', artisan_count: 1, request_count: 1, completed_count: 0 },
  { name: 'froid', artisan_count: 0, request_count: 1, completed_count: 0 },
  { name: 'menuiserie', artisan_count: 1, request_count: 1, completed_count: 1 },
];

function label(name) {
  return NAMES[name] || name.charAt(0).toUpperCase() + name.slice(1);
}

function categoryColor(name) {
  return COLORS[name] || COLORS.autre;
}

function CategoryIcon({ name, size = 22 }) {
  const Icon = ICONS[name] || Briefcase;
  return <Icon size={size} color='#fff' />;
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

export default function FixProCategoriesPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [categories, setCategories] = useState(MOCK);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.categories()
      .then((rows) => {
        const mapped = rows.map((r) => ({
          ...r,
          request_count: parseInt(r.request_count || 0, 10),
          completed_count: parseInt(r.completed_count || 0, 10),
          artisan_count: parseInt(r.artisan_count || 0, 10),
        }));
        if (mapped.length) setCategories(mapped);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const filtered = categories.filter((c) => label(c.name).toLowerCase().includes(search.toLowerCase()));

  const totalRequests = categories.reduce((acc, c) => acc + c.request_count, 0);
  const totalCompleted = categories.reduce((acc, c) => acc + c.completed_count, 0);
  const totalArtisans = categories.reduce((acc, c) => acc + c.artisan_count, 0);
  const globalRate = totalRequests ? Math.round((totalCompleted / totalRequests) * 100) : 0;

  return (
    <div className='fx-body w-full min-h-[760px] flex' style={{ background: C.bg, color: C.ink }}>
      <style dangerouslySetInnerHTML={{ __html: FONT_STYLE }} />

      <aside
        className={`fixed top-0 left-0 z-20 h-screen flex flex-col overflow-hidden transition-transform duration-200 ${navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
        style={{ width: 220, background: C.brandDark, boxShadow: SHADOW_MD }}
      >
        <div className='flex items-center gap-2 px-5 py-5' style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div className='flex items-center justify-center rounded-lg' style={{ width: 28, height: 28, background: C.brandLight }}>
            <Wrench size={15} color='#fff' />
          </div>
          <span className='fx-display font-bold text-white text-[16px]'>FixPro <span style={{ color: C.amber }}>Admin</span></span>
          <button className='ml-auto lg:hidden text-white' onClick={() => setNavOpen(false)}><X size={18} /></button>
        </div>
        <nav className='px-3 mt-3 flex-1 overflow-y-auto flex flex-col gap-0.5'>
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
            <h1 className='fx-display font-bold text-[19px]'>Categories</h1>
            <p className='fx-body text-[12.5px]' style={{ color: C.inkMuted }}>{categories.length} categories actives</p>
          </div>
          <div
            className='hidden md:flex items-center gap-2 ml-4 px-3 py-2 rounded-lg flex-1 max-w-xs'
            style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}
          >
            <Search size={15} color={C.inkMuted} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder='Rechercher une categorie...'
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
              { label: 'Demandes', value: totalRequests },
              { label: 'Terminees', value: totalCompleted, color: C.green },
              { label: 'Techniciens', value: totalArtisans, color: C.brandLight },
              { label: 'Taux de reso.', value: `${globalRate}%`, color: C.amber },
            ].map((k) => (
              <div key={k.label} className='rounded-xl p-4' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}>
                <p className='fx-body text-[12px]' style={{ color: C.inkMuted }}>{k.label}</p>
                <p className='fx-display text-[22px] font-bold mt-0.5' style={{ color: k.color || C.ink }}>{k.value}</p>
              </div>
            ))}
          </div>

          {loading && (
            <div className='p-8 text-center fx-body text-[13px]' style={{ color: C.inkMuted }}>Chargement...</div>
          )}

          {!loading && (
            <div className='grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4'>
              {filtered.map((c) => {
                const color = categoryColor(c.name);
                const rate = c.request_count ? Math.round((c.completed_count / c.request_count) * 100) : 0;
                return (
                  <div
                    key={c.name}
                    className='fx-card rounded-2xl p-5 transition-all cursor-pointer'
                    style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}
                    onClick={() => router.push('/admin/interventions')}
                  >
                    <div className='flex items-start justify-between'>
                      <div className='flex items-center gap-3'>
                        <div className='flex items-center justify-center rounded-lg' style={{ width: 40, height: 40, background: color }}>
                          <CategoryIcon name={c.name} size={22} />
                        </div>
                        <div>
                          <h3 className='fx-display font-bold text-[16px]'>{label(c.name)}</h3>
                          <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>{c.artisan_count} technicien{c.artisan_count > 1 ? 's' : ''}</p>
                        </div>
                      </div>
                      <ChevronRight size={16} color={C.inkMuted} />
                    </div>

                    <div className='grid grid-cols-3 gap-3 mt-4'>
                      <div className='rounded-lg p-2.5' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                        <p className='fx-body text-[10px]' style={{ color: C.inkMuted }}>Demandes</p>
                        <p className='fx-display font-bold text-[16px]'>{c.request_count}</p>
                      </div>
                      <div className='rounded-lg p-2.5' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                        <p className='fx-body text-[10px]' style={{ color: C.inkMuted }}>Terminees</p>
                        <p className='fx-display font-bold text-[16px]'>{c.completed_count}</p>
                      </div>
                      <div className='rounded-lg p-2.5' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                        <p className='fx-body text-[10px]' style={{ color: C.inkMuted }}>Taux</p>
                        <p className='fx-display font-bold text-[16px]' style={{ color: rate >= 80 ? C.green : rate >= 40 ? C.amber : C.red }}>{rate}%</p>
                      </div>
                    </div>

                    <div className='mt-4 w-full rounded-full h-2' style={{ background: C.border }}>
                      <div className='h-full rounded-full' style={{ width: `${rate}%`, background: color }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
