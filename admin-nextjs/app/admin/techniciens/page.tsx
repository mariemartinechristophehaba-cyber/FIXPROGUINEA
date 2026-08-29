// @ts-nocheck
'use client';

import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings, MessageSquare,
  Search, Bell, Star, Check, X, MapPin, Phone, Mail, FileText,
  ChevronRight, Menu, Filter, ChevronDown, Plus,
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

const FILTER_TABS = ['Tous', 'Verifies', 'En attente', 'Actifs', 'Inactifs'];

const MOCK = [
  { id: 1, full_name: 'Fatou Camara', profession: 'Electricien', phone: '621 11 22 33', email: 'fatou@fixpro.gn', doc_count: 3, completed: 12, avg_rating: 4.6, review_count: 8, is_verified: 1, is_active: 1, latitude: null, longitude: null, address: 'Conakry', created_at: '2026-08-20T10:00:00' },
  { id: 2, full_name: 'Ibrahim Sylla', profession: 'Menuisier', phone: '622 22 33 44', email: 'ibrahim@fixpro.gn', doc_count: 2, completed: 7, avg_rating: 4.2, review_count: 5, is_verified: 1, is_active: 1, latitude: null, longitude: null, address: 'Kaloum', created_at: '2026-08-21T10:00:00' },
  { id: 3, full_name: 'Mamadou Bah', profession: 'Plombier', phone: '623 33 44 55', email: 'mamadou@fixpro.gn', doc_count: 1, completed: 4, avg_rating: 3.8, review_count: 3, is_verified: 0, is_active: 1, latitude: null, longitude: null, address: 'Dixinn', created_at: '2026-08-22T10:00:00' },
];

function label(profession) {
  if (!profession) return 'Autre';
  return profession.charAt(0).toUpperCase() + profession.slice(1);
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleDateString('fr-FR', { month: 'short' }).replace('.', '');
  return `${d.getDate()} ${month} ${d.getFullYear()}`;
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

function Stars({ value }) {
  return (
    <div className='flex items-center gap-0.5'>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={12}
          fill={i <= Math.round(value) ? C.amber : 'transparent'}
          color={i <= Math.round(value) ? C.amber : C.borderStrong}
        />
      ))}
      <span className='fx-body font-semibold text-[11.5px] ml-1'>{value.toFixed(1)}</span>
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

export default function FixProTechniciensPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [filter, setFilter] = useState('Tous');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('Toutes');
  const [techniciens, setTechniciens] = useState(MOCK);
  const [selected, setSelected] = useState(MOCK[0]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    full_name: '', phone: '', email: '', profession: '', password: '',
    address: '', photo: '', identity_doc: '',
  });
  const [photoName, setPhotoName] = useState('');
  const [docName, setDocName] = useState('');
  const [formError, setFormError] = useState('');
  const [creating, setCreating] = useState(false);

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
        if (mapped.length) {
          setTechniciens(mapped);
          setSelected(mapped[0]);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const categories = ['Toutes', ...Array.from(new Set(techniciens.map((t) => label(t.profession))))];

  const filtered = techniciens.filter((t) => {
    if (search && !t.full_name.toLowerCase().includes(search.toLowerCase()) && !t.phone.includes(search)) return false;
    if (category !== 'Toutes' && label(t.profession) !== category) return false;
    if (filter === 'Verifies' && !t.is_verified) return false;
    if (filter === 'En attente' && t.is_verified) return false;
    if (filter === 'Actifs' && !t.is_active) return false;
    if (filter === 'Inactifs' && t.is_active) return false;
    return true;
  });

  const handleVerify = () => {
    api.verifyArtisan(selected.id)
      .then(() => setTechniciens(techniciens.map((t) => (t.id === selected.id ? { ...t, is_verified: 1 } : t))))
      .catch(console.error);
  };

  const handleReject = () => {
    api.rejectArtisan(selected.id)
      .then(() => setTechniciens(techniciens.map((t) => (t.id === selected.id ? { ...t, is_verified: 0 } : t))))
      .catch(console.error);
  };

  const handleFile = (field, setName) => (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      setFormData((prev) => ({ ...prev, [field]: dataUrl }));
    };
    reader.readAsDataURL(file);
    setName(file.name);
  };

  const handleCreate = (e) => {
    e.preventDefault();
    setCreating(true);
    setFormError('');
    api.createTechnicien(formData)
      .then((newUser) => {
        const mapped = {
          ...newUser,
          avg_rating: 0,
          completed: 0,
          doc_count: 0,
          review_count: 0,
        };
        setTechniciens([mapped, ...techniciens]);
        setSelected(mapped);
        setModalOpen(false);
        setFormData({ full_name: '', phone: '', email: '', profession: '', password: '' });
        setCreating(false);
      })
      .catch((err) => {
        setFormError(err.message || 'Erreur lors de la creation.');
        setCreating(false);
      });
  };

  const counts = {
    total: techniciens.length,
    verified: techniciens.filter((t) => t.is_verified).length,
    pending: techniciens.filter((t) => !t.is_verified).length,
    active: techniciens.filter((t) => t.is_active).length,
  };

  return (
    <div className='fx-body w-full min-h-[760px] flex' style={{ background: C.bg, color: C.ink }}>
      <style dangerouslySetInnerHTML={{ __html: FONT_STYLE }} />

      <aside
        className={`fixed z-20 h-screen transition-transform duration-200 ${navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
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

      <main className='flex-1 min-w-0 flex flex-col lg:ml-[220px]'>
        <div
          className='flex items-center gap-4 px-5 lg:px-8 py-4 sticky top-0 z-10'
          style={{ background: 'rgba(238,240,245,0.92)', backdropFilter: 'blur(6px)', borderBottom: `1px solid ${C.border}` }}
        >
          <button className='lg:hidden' onClick={() => setNavOpen(true)}><Menu size={20} /></button>
          <div>
            <h1 className='fx-display font-bold text-[19px]'>Techniciens</h1>
            <p className='fx-body text-[12.5px]' style={{ color: C.inkMuted }}>{counts.total} techniciens inscrits</p>
          </div>
          <div
            className='hidden md:flex items-center gap-2 ml-4 px-3 py-2 rounded-lg flex-1 max-w-xs'
            style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}
          >
            <Search size={15} color={C.inkMuted} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder='Rechercher un technicien...'
              className='fx-body text-[13px] bg-transparent outline-none w-full'
            />
          </div>
          <div className='ml-auto flex items-center gap-4'>
            <button
              onClick={() => setModalOpen(true)}
              className='fx-body font-semibold text-[12px] rounded-lg px-3 py-2 hidden md:flex items-center gap-1.5'
              style={{ background: C.brand, color: '#fff', boxShadow: SHADOW_SM }}
            >
              <Plus size={14} /> Ajouter
            </button>
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
              { label: 'Inscrits', value: counts.total },
              { label: 'Verifies', value: counts.verified, color: C.green },
              { label: 'En attente', value: counts.pending, color: C.amber },
              { label: 'Actifs', value: counts.active, color: C.brandLight },
            ].map((k) => (
              <div key={k.label} className='rounded-xl p-4' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_SM }}>
                <p className='fx-body text-[12px]' style={{ color: C.inkMuted }}>{k.label}</p>
                <p className='fx-display text-[22px] font-bold mt-0.5' style={{ color: k.color || C.ink }}>{k.value}</p>
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
                {f === 'Tous' ? `${f} · ${techniciens.length}` : f}
              </button>
            ))}
            <div className='ml-auto flex items-center gap-2'>
              <button
                className='fx-body font-medium text-[12.5px] rounded-lg px-3 py-1.5 flex items-center gap-1.5'
                style={{ background: C.surface, border: `1px solid ${C.border}`, color: C.ink, boxShadow: SHADOW_SM }}
                onClick={() => setCategory(category === 'Toutes' ? categories[1] || 'Toutes' : 'Toutes')}
              >
                <Filter size={13} /> {category} <ChevronDown size={13} />
              </button>
            </div>
          </div>

          <div className='grid grid-cols-1 xl:grid-cols-3 gap-5'>
            <div className='xl:col-span-2 rounded-2xl overflow-hidden' style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}>
              <div className='fx-scroll overflow-x-auto'>
                <table className='w-full'>
                  <thead>
                    <tr className='text-left' style={{ borderBottom: `2px solid ${C.border}` }}>
                      {['Technicien', 'Metier', 'Documents', 'Terminees', 'Note', 'Verification', ''].map((h) => (
                        <th key={h} className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={7} className='px-4 py-8 text-center fx-body text-[13px]' style={{ color: C.inkMuted }}>Chargement...</td>
                      </tr>
                    )}
                    {!loading && filtered.map((t) => (
                      <tr
                        key={t.id}
                        onClick={() => setSelected(t)}
                        className='fx-row cursor-pointer transition-colors'
                        style={{
                          borderTop: `1px solid ${C.border}`,
                          background: selected?.id === t.id ? C.surfaceAlt : 'transparent',
                        }}
                      >
                        <td className='px-4 py-3.5 text-[13px] font-medium'>
                          <div className='flex items-center gap-2'>
                            <Initials name={t.full_name} size={26} bg={t.is_verified ? C.brandLight : C.inkMuted} />
                            <div>
                              {t.full_name}
                              <div className='text-[11px] font-normal' style={{ color: C.inkMuted }}>{t.phone}</div>
                            </div>
                          </div>
                        </td>
                        <td className='px-4 py-3.5'>
                          <span className='fx-body font-semibold text-[11px] rounded-full px-2.5 py-1' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>{label(t.profession)}</span>
                        </td>
                        <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{t.doc_count}</td>
                        <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{t.completed}</td>
                        <td className='px-4 py-3.5'><Stars value={t.avg_rating} /></td>
                        <td className='px-4 py-3.5'>
                          {t.is_verified ? (
                            <Badge color={C.green} bg={C.greenBg}>Verifie</Badge>
                          ) : (
                            <Badge color={C.amber} bg={C.amberBg}>En attente</Badge>
                          )}
                        </td>
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
                      <Initials name={selected.full_name} size={48} bg={selected.is_verified ? C.brandLight : C.inkMuted} />
                      <div>
                        <h3 className='fx-display font-bold text-[16px]'>{selected.full_name}</h3>
                        <p className='fx-body text-[12px]' style={{ color: C.inkMuted }}>{label(selected.profession)}</p>
                      </div>
                    </div>
                    {selected.is_verified ? (
                      <Badge color={C.green} bg={C.greenBg}>Verifie</Badge>
                    ) : (
                      <Badge color={C.amber} bg={C.amberBg}>En attente</Badge>
                    )}
                  </div>

                  <div className='flex flex-col gap-2 text-[12.5px] font-medium' style={{ color: C.inkMuted }}>
                    <div className='flex items-center gap-2'><Phone size={13} /> {selected.phone}</div>
                    <div className='flex items-center gap-2'><Mail size={13} /> {selected.email || '—'}</div>
                    <div className='flex items-center gap-2'><MapPin size={13} /> {selected.address || '—'}</div>
                    <div className='flex items-center gap-2'><FileText size={13} /> {selected.doc_count} document{selected.doc_count > 1 ? 's' : ''}</div>
                  </div>

                  <div className='grid grid-cols-2 gap-3'>
                    <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                      <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>Interventions terminees</p>
                      <p className='fx-display text-[20px] font-bold'>{selected.completed}</p>
                    </div>
                    <div className='rounded-xl p-3' style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
                      <p className='fx-body text-[11px]' style={{ color: C.inkMuted }}>Avis</p>
                      <p className='fx-display text-[20px] font-bold'>{selected.review_count}</p>
                    </div>
                  </div>

                  <div>
                    <p className='fx-body font-semibold text-[11.5px] mb-1.5' style={{ color: C.inkMuted }}>Note moyenne</p>
                    <Stars value={selected.avg_rating} />
                  </div>

                  <div className='flex gap-2 mt-1'>
                    {!selected.is_verified && (
                      <button
                        onClick={handleVerify}
                        className='flex-1 fx-body font-semibold text-[12.5px] rounded-lg py-2.5 flex items-center justify-center gap-1.5'
                        style={{ background: C.green, color: '#fff', boxShadow: '0 2px 6px rgba(15,122,82,0.3)' }}
                      >
                        <Check size={13} /> Verifier
                      </button>
                    )}
                    {selected.is_verified && (
                      <button
                        onClick={handleReject}
                        className='flex-1 fx-body font-semibold text-[12.5px] rounded-lg py-2.5 flex items-center justify-center gap-1.5'
                        style={{ background: C.red, color: '#fff', boxShadow: '0 2px 6px rgba(179,39,29,0.3)' }}
                      >
                        <X size={13} /> Retirer
                      </button>
                    )}
                  </div>
                  <p className='fx-mono text-[10px]' style={{ color: C.inkMuted }}>Inscrit le {formatDate(selected.created_at)}</p>
                </>
              )}
            </div>
          </div>
        </div>
      </main>

      {modalOpen && (
        <div className='fixed inset-0 z-50 flex items-center justify-center p-4' style={{ background: 'rgba(10,14,31,0.5)' }} onClick={() => setModalOpen(false)}>
          <div className='rounded-2xl p-6 w-full max-w-md' style={{ background: C.surface, boxShadow: SHADOW_MD }} onClick={(e) => e.stopPropagation()}>
            <div className='flex items-center justify-between mb-4'>
              <h2 className='fx-display font-bold text-[18px]'>Ajouter un technicien</h2>
              <button onClick={() => setModalOpen(false)} className='text-gray-500'><X size={18} color={C.inkMuted} /></button>
            </div>
            {formError && (
              <div className='rounded-lg p-3 mb-4' style={{ background: C.redBg, color: C.red }}>
                <p className='fx-body text-[12px]'>{formError}</p>
              </div>
            )}
            <form onSubmit={handleCreate} className='flex flex-col gap-3'>
              <input
                required
                placeholder='Nom complet'
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className='fx-body text-[13px] rounded-lg px-3 py-2.5 w-full'
                style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
              />
              <input
                required
                placeholder='Telephone'
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                className='fx-body text-[13px] rounded-lg px-3 py-2.5 w-full'
                style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
              />
              <input
                placeholder='Email (optionnel)'
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className='fx-body text-[13px] rounded-lg px-3 py-2.5 w-full'
                style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
              />
              <input
                required
                placeholder='Metier'
                value={formData.profession}
                onChange={(e) => setFormData({ ...formData, profession: e.target.value })}
                className='fx-body text-[13px] rounded-lg px-3 py-2.5 w-full'
                style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
              />
              <input
                required
                type='password'
                placeholder='Mot de passe'
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                className='fx-body text-[13px] rounded-lg px-3 py-2.5 w-full'
                style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
              />
              <input
                placeholder='Adresse / Ville'
                value={formData.address}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                className='fx-body text-[13px] rounded-lg px-3 py-2.5 w-full'
                style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
              />
              <label className='fx-body text-[12px]' style={{ color: C.inkMuted }}>
                Photo (optionnel)
                <input
                  type='file'
                  accept='image/*'
                  onChange={handleFile('photo', setPhotoName)}
                  className='fx-body text-[13px] mt-1'
                />
                {photoName && <span className='block mt-1'>{photoName}</span>}
              </label>
              <label className='fx-body text-[12px]' style={{ color: C.inkMuted }}>
                Document d'identite (optionnel)
                <input
                  type='file'
                  accept='image/*,.pdf'
                  onChange={handleFile('identity_doc', setDocName)}
                  className='fx-body text-[13px] mt-1'
                />
                {docName && <span className='block mt-1'>{docName}</span>}
              </label>
              <button
                type='submit'
                disabled={creating}
                className='fx-body font-semibold text-[13px] rounded-lg py-2.5 mt-2'
                style={{ background: C.brand, color: '#fff', boxShadow: SHADOW_SM, opacity: creating ? 0.7 : 1 }}
              >
                {creating ? 'Creation...' : 'Creer le technicien'}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
