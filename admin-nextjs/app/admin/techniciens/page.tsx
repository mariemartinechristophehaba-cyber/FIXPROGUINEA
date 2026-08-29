// @ts-nocheck
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings,
  MessageSquare, Star, FileText, Bell, Search, MapPin, Phone, Mail,
  ChevronRight, Menu, X, MoreHorizontal, Filter, Download, Plus,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useRouter, usePathname } from 'next/navigation';

const C = {
  bg: '#F4F6F9',
  surface: '#FFFFFF',
  surfaceAlt: '#F8F9FC',
  border: '#E2E8F0',
  borderStrong: '#CBD5E1',
  ink: '#0F172A',
  inkMuted: '#64748B',
  brand: '#1E3A8A',
  brandLight: '#2563EB',
  brandDark: '#0F172A',
  green: '#16A34A',
  greenBg: '#DCFCE7',
  greenText: '#15803D',
  amber: '#D97706',
  amberBg: '#FEF3C7',
  amberText: '#92400E',
  red: '#DC2626',
  redBg: '#FEE2E2',
  redText: '#991B1B',
  blue: '#2563EB',
  blueLight: '#E0E7FF',
};

const SHADOW_SM = '0 1px 2px rgba(15,23,42,0.04), 0 2px 8px -2px rgba(15,23,42,0.06)';
const SHADOW_MD = '0 4px 12px rgba(15,23,42,0.08)';

const FONT_STYLE = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  .fx-body { font-family: 'Inter', sans-serif; }
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

const TABS = ['Tous', 'Actifs', 'En mission', 'En attente', 'Suspendus', 'Inactifs'];
const DETAIL_TABS = ['Informations', 'Missions', 'Documents', 'Paiements', 'Notes'];

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
}

function getStatus(t) {
  if (!t.is_active) return { label: 'Inactif', color: C.inkMuted, bg: '#F1F5F9' };
  if (t.account_status === 'SUSPENDED') return { label: 'Suspendu', color: C.redText, bg: C.redBg };
  if (t.availability_status === 'occupe' || t.availability_status === 'en_mission') return { label: 'En mission', color: C.amberText, bg: C.amberBg };
  if (t.availability_status === 'hors_ligne') return { label: 'En attente', color: C.inkMuted, bg: '#F1F5F9' };
  if (t.availability_status === 'en_ligne' || !t.availability_status) return { label: 'Actif', color: C.greenText, bg: C.greenBg };
  return { label: 'Actif', color: C.greenText, bg: C.greenBg };
}

function Avatar({ name, size = 36, src }) {
  const initials = (name || 'X')
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  return src ? (
    <img src={src} alt={name} className='rounded-full object-cover' style={{ width: size, height: size }} />
  ) : (
    <div
      className='rounded-full flex items-center justify-center text-white fx-body font-bold'
      style={{ width: size, height: size, background: C.brandLight, fontSize: size * 0.35 }}
    >
      {initials}
    </div>
  );
}

function Stars({ value }) {
  return (
    <div className='flex items-center gap-0.5'>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} size={12} fill={i <= Math.round(value) ? '#F59E0B' : 'transparent'} color={i <= Math.round(value) ? '#F59E0B' : C.borderStrong} />
      ))}
    </div>
  );
}

export default function TechniciensPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [techniciens, setTechniciens] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('Tous');
  const [detailTab, setDetailTab] = useState('Informations');
  const [search, setSearch] = useState('');

  useEffect(() => {
    api.techniciens()
      .then((rows) => {
        const mapped = rows.map((r) => ({
          ...r,
          avg_rating: parseFloat(r.avg_rating || 0),
          completed: parseInt(r.completed || 0, 10),
          doc_count: parseInt(r.doc_count || 0, 10),
          review_count: parseInt(r.review_count || 0, 10),
        }));
        setTechniciens(mapped);
        setSelected(mapped[0] || null);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const filtered = useMemo(() => {
    let rows = techniciens;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter((t) =>
        (t.full_name || '').toLowerCase().includes(q) ||
        (t.profession || '').toLowerCase().includes(q) ||
        (t.phone || '').includes(q)
      );
    }
    if (activeTab !== 'Tous') {
      rows = rows.filter((t) => getStatus(t).label === activeTab);
    }
    return rows;
  }, [techniciens, search, activeTab]);

  const counts = useMemo(() => ({
    total: techniciens.length,
    actifs: techniciens.filter((t) => getStatus(t).label === 'Actif').length,
    enMission: techniciens.filter((t) => getStatus(t).label === 'En mission').length,
    enAttente: techniciens.filter((t) => getStatus(t).label === 'En attente').length,
    suspendus: techniciens.filter((t) => getStatus(t).label === 'Suspendu').length,
    inactifs: techniciens.filter((t) => getStatus(t).label === 'Inactif').length,
  }), [techniciens]);

  const kpis = [
    { label: 'Total techniciens', value: counts.total, delta: '+12 ce mois', color: C.ink },
    { label: 'Actifs', value: counts.actifs, delta: '81.3% du total', color: C.green },
    { label: 'En mission', value: counts.enMission, delta: '14.8% du total', color: C.amber },
    { label: 'En attente', value: counts.enAttente, delta: '3.9% du total', color: C.brandLight },
    { label: 'Suspendus', value: counts.suspendus, delta: '3.1% du total', color: C.red },
    { label: 'Inactifs', value: counts.inactifs, delta: '0.8% du total', color: C.inkMuted },
  ];

  return (
    <div className='fx-body w-full min-h-screen flex' style={{ background: C.bg, color: C.ink }}>
      <style dangerouslySetInnerHTML={{ __html: FONT_STYLE }} />

      <aside
        className={`fixed top-0 left-0 z-20 h-screen flex flex-col overflow-hidden transition-transform duration-200 ${navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
        style={{ width: 260, background: '#0B1221', boxShadow: SHADOW_MD }}
      >
        <div className='flex items-center gap-3 px-5 py-5' style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div className='flex items-center justify-center rounded-lg' style={{ width: 34, height: 34, background: C.brandLight }}>
            <Wrench size={17} color='#fff' />
          </div>
          <span className='font-bold text-white text-[17px]'>FixPro</span>
        </div>
        <nav className='px-3 mt-4 flex-1 overflow-y-auto flex flex-col gap-1'>
          {NAV.map(({ label, icon: Icon, href }) => {
            const active = pathname === href || pathname.startsWith(href + '/');
            return (
              <button
                key={label}
                onClick={() => router.push(href)}
                className='flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors'
                style={{
                  background: active ? C.brandLight : 'transparent',
                  color: active ? '#fff' : 'rgba(255,255,255,0.65)',
                  fontWeight: active ? 600 : 500,
                }}
              >
                <Icon size={18} strokeWidth={active ? 2.4 : 2} />
                <span className='text-[13.5px]'>{label}</span>
              </button>
            );
          })}
        </nav>
        <div className='px-5 py-4' style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <div className='flex items-center gap-3'>
            <Avatar name='Admin Super' size={38} />
            <div>
              <p className='text-white text-[13px] font-semibold'>Admin Super</p>
              <p className='text-white/60 text-[11px]'>Administrateur</p>
            </div>
          </div>
        </div>
      </aside>
      {navOpen && <div className='fixed inset-0 bg-black/40 z-10 lg:hidden' onClick={() => setNavOpen(false)} />}

      <main className='flex-1 min-w-0 flex flex-col h-screen overflow-y-auto lg:ml-[260px]'>
        <header
          className='flex items-center justify-between gap-4 px-6 lg:px-8 py-4 sticky top-0 z-10'
          style={{ background: C.surface, borderBottom: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}
        >
          <div className='flex items-center gap-4'>
            <button className='lg:hidden' onClick={() => setNavOpen(true)}><Menu size={20} /></button>
            <div>
              <h1 className='font-bold text-[20px]'>Techniciens</h1>
              <p className='text-[12.5px]' style={{ color: C.inkMuted }}>Gerez tous vos techniciens et leurs activites</p>
            </div>
          </div>
          <div className='flex items-center gap-4'>
            <div
              className='hidden md:flex items-center gap-2 px-3 py-2 rounded-lg'
              style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
            >
              <Search size={16} color={C.inkMuted} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder='Rechercher (nom, telephone, specialite, email...)'
                className='text-[13px] bg-transparent outline-none w-64'
              />
            </div>
            <button
              className='hidden md:flex items-center gap-2 text-[12.5px] font-semibold px-3 py-2 rounded-lg'
              style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
            >
              <Filter size={14} /> Filtres avances
            </button>
            <button className='relative'>
              <Bell size={20} color={C.inkMuted} />
              <span className='absolute -top-1 -right-1 rounded-full text-white flex items-center justify-center' style={{ width: 16, height: 16, fontSize: 9, background: C.red }}>
                3
              </span>
            </button>
            <Avatar name='Admin Super' size={36} />
          </div>
        </header>

        <div className='p-6 lg:p-8 flex flex-col gap-5'>
          <div className='grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4'>
            {kpis.map((k) => (
              <div key={k.label} className='rounded-xl p-4' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}>
                <p className='text-[12px]' style={{ color: C.inkMuted }}>{k.label}</p>
                <p className='text-[24px] font-bold mt-1' style={{ color: k.color }}>{k.value}</p>
                <p className='text-[11px]' style={{ color: C.inkMuted }}>{k.delta}</p>
              </div>
            ))}
          </div>

          <div className='flex flex-wrap items-center gap-2'>
            {TABS.map((t) => {
              const active = activeTab === t;
              return (
                <button
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className='text-[12.5px] font-semibold rounded-full px-4 py-1.5 transition-colors'
                  style={{
                    background: active ? C.brand : C.surface,
                    color: active ? '#fff' : C.ink,
                    border: `1px solid ${active ? C.brand : C.border}`,
                  }}
                >
                  {t}
                </button>
              );
            })}
            <div className='ml-auto flex items-center gap-2'>
              <button className='flex items-center gap-2 text-[12.5px] font-semibold px-3 py-2 rounded-lg' style={{ background: C.surface, border: `1px solid ${C.border}` }}>
                <Plus size={14} /> Ajouter un technicien
              </button>
              <button className='flex items-center gap-2 text-[12.5px] font-semibold px-3 py-2 rounded-lg' style={{ background: C.surface, border: `1px solid ${C.border}` }}>
                <Download size={14} /> Exporter
              </button>
            </div>
          </div>

          <div className='grid grid-cols-1 xl:grid-cols-3 gap-5'>
            <div className='xl:col-span-2 rounded-2xl overflow-hidden' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
              <div className='overflow-x-auto'>
                <table className='w-full'>
                  <thead>
                    <tr style={{ borderBottom: `2px solid ${C.border}` }}>
                      {['Technicien', 'Specialite', 'Telephone', "Zone d'intervention", 'Statut', 'Missions', 'Note', 'Inscrit le', 'Actions'].map((h) => (
                        <th key={h} className='text-left font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={9} className='px-4 py-8 text-center text-[13px]' style={{ color: C.inkMuted }}>Chargement...</td>
                      </tr>
                    )}
                    {!loading && filtered.map((t) => {
                      const status = getStatus(t);
                      return (
                        <tr
                          key={t.id}
                          onClick={() => setSelected(t)}
                          className='cursor-pointer transition-colors hover:bg-[#F8FAFC]'
                          style={{
                            borderTop: `1px solid ${C.border}`,
                            background: selected?.id === t.id ? C.surfaceAlt : 'transparent',
                          }}
                        >
                          <td className='px-4 py-3.5'>
                            <div className='flex items-center gap-3'>
                              <Avatar name={t.full_name} size={36} src={t.photo_url} />
                              <div>
                                <p className='font-semibold text-[13px]'>{t.full_name}</p>
                                <p className='text-[11px]' style={{ color: C.inkMuted }}>{t.email}</p>
                              </div>
                            </div>
                          </td>
                          <td className='px-4 py-3.5'>
                            <span className='font-semibold text-[11px] rounded-full px-2.5 py-1' style={{ background: C.blueLight, color: C.brand }}>
                              {t.profession ? t.profession.charAt(0).toUpperCase() + t.profession.slice(1) : '—'}
                            </span>
                          </td>
                          <td className='px-4 py-3.5 text-[12.5px]' style={{ color: C.inkMuted }}>{t.phone}</td>
                          <td className='px-4 py-3.5 text-[12.5px]' style={{ color: C.inkMuted }}>{t.zone_intervention || t.address || 'Conakry'}</td>
                          <td className='px-4 py-3.5'>
                            <span className='font-semibold text-[11px] rounded-full px-2.5 py-1' style={{ background: status.bg, color: status.color }}>
                              {status.label}
                            </span>
                          </td>
                          <td className='px-4 py-3.5 text-[12.5px] font-semibold' style={{ color: C.inkMuted }}>{t.completed}</td>
                          <td className='px-4 py-3.5'>
                            <Stars value={t.avg_rating} />
                            <p className='text-[10px]' style={{ color: C.inkMuted }}>{t.review_count} avis</p>
                          </td>
                          <td className='px-4 py-3.5 text-[12.5px]' style={{ color: C.inkMuted }}>{formatDate(t.created_at)}</td>
                          <td className='px-4 py-3.5'>
                            <button className='p-1 rounded hover:bg-gray-100'><MoreHorizontal size={16} color={C.inkMuted} /></button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className='rounded-2xl p-5 flex flex-col gap-4' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
              {selected && (
                <>
                  <div className='flex items-start justify-between'>
                    <div className='flex items-center gap-3'>
                      <Avatar name={selected.full_name} size={64} src={selected.photo_url} />
                      <div>
                        <h3 className='font-bold text-[16px]'>{selected.full_name}</h3>
                        <p className='text-[12.5px]' style={{ color: C.inkMuted }}>{selected.profession ? selected.profession.charAt(0).toUpperCase() + selected.profession.slice(1) : '—'}</p>
                      </div>
                    </div>
                    {getStatus(selected).label === 'Actif' ? (
                      <span className='font-semibold text-[10px] rounded-full px-2 py-0.5' style={{ background: C.greenBg, color: C.greenText }}>Actif</span>
                    ) : (
                      <span className='font-semibold text-[10px] rounded-full px-2 py-0.5' style={{ background: getStatus(selected).bg, color: getStatus(selected).color }}>{getStatus(selected).label}</span>
                    )}
                  </div>

                  <div className='flex gap-1' style={{ borderBottom: `1px solid ${C.border}` }}>
                    {DETAIL_TABS.map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setDetailTab(tab)}
                        className='text-[11.5px] font-semibold px-3 py-2'
                        style={{
                          color: detailTab === tab ? C.brand : C.inkMuted,
                          borderBottom: `2px solid ${detailTab === tab ? C.brand : 'transparent'}`,
                        }}
                      >
                        {tab}
                      </button>
                    ))}
                  </div>

                  {detailTab === 'Informations' && (
                    <div className='flex flex-col gap-3 text-[13px]' style={{ color: C.inkMuted }}>
                      <div className='flex items-center gap-2'><Phone size={15} /> {selected.phone}</div>
                      <div className='flex items-center gap-2'><Mail size={15} /> {selected.email || '—'}</div>
                      <div className='flex items-center gap-2'><MapPin size={15} /> {selected.address || 'Conakry'}</div>
                      <div className='flex items-center gap-2'>
                        <div className='flex-1'>
                          <span className='font-semibold' style={{ color: C.ink }}>Zone d'intervention :</span> {selected.zone_intervention || 'Conakry'}
                        </div>
                      </div>
                      <div className='flex items-center gap-2'>
                        <div className='flex-1'>
                          <span className='font-semibold' style={{ color: C.ink }}>Disponibilite :</span> {selected.availability_status || 'Non renseignee'}
                        </div>
                      </div>
                      <div className='flex items-center gap-2'>
                        <div className='flex-1'>
                          <span className='font-semibold' style={{ color: C.ink }}>Inscrit le :</span> {formatDate(selected.created_at)}
                        </div>
                      </div>

                      <div className='grid grid-cols-2 gap-3 mt-2'>
                        <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                          <p className='text-[11px]' style={{ color: C.inkMuted }}>Note moyenne</p>
                          <div className='flex items-center gap-2 mt-1'>
                            <span className='font-bold text-[18px]'>{selected.avg_rating.toFixed(1)}</span>
                            <Stars value={selected.avg_rating} />
                          </div>
                          <p className='text-[10px]' style={{ color: C.inkMuted }}>{selected.review_count} avis</p>
                        </div>
                        <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                          <p className='text-[11px]' style={{ color: C.inkMuted }}>Missions</p>
                          <p className='font-bold text-[18px] mt-1'>{selected.completed}</p>
                          <p className='text-[10px]' style={{ color: C.inkMuted }}>en cours / terminees</p>
                        </div>
                      </div>

                      <div className='grid grid-cols-2 gap-3 mt-1'>
                        <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                          <p className='text-[11px]' style={{ color: C.inkMuted }}>Documents</p>
                          <p className='font-bold text-[18px] mt-1'>{selected.doc_count}</p>
                          <p className='text-[10px]' style={{ color: C.inkMuted }}>pieces d'identite</p>
                        </div>
                        <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                          <p className='text-[11px]' style={{ color: C.inkMuted }}>Revenus</p>
                          <p className='font-bold text-[18px] mt-1'>{selected.completed * 150000}</p>
                          <p className='text-[10px]' style={{ color: C.inkMuted }}>GNF ce mois</p>
                        </div>
                      </div>

                      <div className='flex gap-2 mt-2'>
                        <button className='flex-1 font-semibold text-[12px] rounded-lg py-2 flex items-center justify-center gap-1.5' style={{ background: C.brandLight, color: '#fff' }}>
                          <FileText size={13} /> Voir profil public
                        </button>
                        <button className='flex-1 font-semibold text-[12px] rounded-lg py-2 flex items-center justify-center gap-1.5' style={{ background: C.amberBg, color: C.amberText }}>
                          <Wrench size={13} /> Voir missions
                        </button>
                      </div>
                    </div>
                  )}

                  {detailTab !== 'Informations' && (
                    <div className='py-8 text-center text-[13px]' style={{ color: C.inkMuted }}>
                      Section {detailTab.toLowerCase()} en cours de construction.
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
