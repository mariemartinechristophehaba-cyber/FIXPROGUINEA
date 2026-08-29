// @ts-nocheck
'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  LayoutDashboard, Wrench, Users, UserRound, Grid3x3, Wallet, Settings, MessageSquare,
  Bell, Search, ChevronRight, Menu, X, Send,
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
  clientBg: '#16265E',
  aiBg: '#F4F5FA',
  adminBg: '#E1F3EA',
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

function roleLabel(role) {
  if (role === 'client') return 'Client';
  if (role === 'ai') return 'Lia';
  if (role === 'admin') return 'Vous';
  if (role === 'system') return 'Systeme';
  return role;
}

function roleBubble(role) {
  if (role === 'client') return { bg: C.clientBg, color: '#fff', align: 'start' };
  if (role === 'admin') return { bg: C.adminBg, color: C.ink, align: 'end' };
  return { bg: C.aiBg, color: C.ink, align: 'start' };
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
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef(null);

  const load = () => {
    setLoading(true);
    const status = { 'Tous': 'all', 'Ouverts': 'open', 'En cours': 'handling', 'Fermes': 'closed' }[filter];
    const q = search ? `&q=${encodeURIComponent(search)}` : '';
    api.liaLogs(`status=${status}${q}`)
      .then(setLogs)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  const loadMessages = (log) => {
    if (!log) return;
    setMsgLoading(true);
    api.liaLogMessages(log.id)
      .then((res) => setMessages(res.messages || []))
      .catch(() => setMessages([]))
      .finally(() => setMsgLoading(false));
  };

  useEffect(() => {
    load();
  }, [filter, search]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  useEffect(() => {
    const id = setInterval(() => {
      const status = { 'Tous': 'all', 'Ouverts': 'open', 'En cours': 'handling', 'Fermes': 'closed' }[filter];
      const q = search ? `&q=${encodeURIComponent(search)}` : '';
      api.liaLogs(`status=${status}${q}`)
        .then(setLogs)
        .catch(console.error);
      if (selected) {
        api.liaLogMessages(selected.id)
          .then((res) => setMessages(res.messages || []))
          .catch(console.error);
      }
    }, 4000);
    return () => clearInterval(id);
  }, [filter, search, selected]);

  const counts = useMemo(() => {
    return {
      total: logs.length,
      open: logs.filter((l) => l.status === 'open').length,
      handling: logs.filter((l) => l.status === 'handling').length,
      closed: logs.filter((l) => l.status === 'closed').length,
    };
  }, [logs]);

  const thread = useMemo(() => {
    if (!selected) return [];
    return logs
      .filter((l) => l.session_id === selected.session_id)
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  }, [logs, selected]);

  const handleTake = (id, e) => {
    e.stopPropagation();
    api.takeLiaLog(id)
      .then(() => {
        load();
        const log = logs.find((l) => l.id === id);
        if (log) {
          setSelected(log);
          loadMessages(log);
        }
      })
      .catch(console.error);
  };

  const handleClose = (id, e) => {
    e.stopPropagation();
    api.closeLiaLog(id)
      .then(load)
      .catch(console.error);
  };

  const handleSelect = (log) => {
    setSelected(log);
    loadMessages(log);
  };

  const handleSend = (e) => {
    e.preventDefault();
    if (!reply.trim() || !selected) return;
    setSending(true);
    api.replyLiaLog(selected.id, reply.trim())
      .then(() => {
        setReply('');
        load();
        loadMessages(selected);
      })
      .catch(console.error)
      .finally(() => setSending(false));
  };

  const isConv = selected && (selected.session_id || '').startsWith('conv-');

  return (
    <div className='fx-body w-full min-h-[760px] flex' style={{ background: C.bg, color: C.ink }}>
      <style dangerouslySetInnerHTML={{ __html: FONT_STYLE }} />

      <aside
        className={`fixed top-0 left-0 z-20 h-screen transition-transform duration-200 ${navOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
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

      <main className='flex-1 min-w-0 flex flex-col h-screen overflow-y-auto lg:ml-[220px]'>
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

        <div className='p-5 lg:p-8 flex flex-col lg:flex-row gap-5 fx-scroll overflow-y-auto'>
          <div className='flex-1 min-w-0 flex flex-col gap-5'>
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
                      <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>Statut</th>
                      <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}>Date</th>
                      <th className='fx-body font-bold text-[10.5px] uppercase tracking-wider px-4 py-3' style={{ color: C.inkMuted }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={5} className='px-4 py-8 text-center fx-body text-[13px]' style={{ color: C.inkMuted }}>Chargement...</td>
                      </tr>
                    )}
                    {!loading && logs.map((l) => {
                      const st = statusColor(l.status);
                      const active = selected && selected.id === l.id;
                      return (
                        <tr
                          key={l.id}
                          onClick={() => handleSelect(l)}
                          className='fx-row transition-colors cursor-pointer'
                          style={{
                            borderTop: `1px solid ${C.border}`,
                            background: active ? C.blueBg : 'transparent',
                          }}
                        >
                          <td className='px-4 py-3.5 text-[13px] font-medium'>
                            <div>{l.client_name || 'Visiteur'}</div>
                            <div className='text-[10.5px] fx-mono' style={{ color: C.inkMuted }}>{l.session_id?.slice(-8) || '—'}</div>
                          </td>
                          <td className='px-4 py-3.5 fx-body text-[12.5px]' style={{ maxWidth: 260 }}>{l.message}</td>
                          <td className='px-4 py-3.5'><Badge color={st.color} bg={st.bg}>{statusLabel(l.status)}</Badge></td>
                          <td className='px-4 py-3.5 fx-mono font-medium text-[11.5px]' style={{ color: C.inkMuted }}>{formatDate(l.created_at)}</td>
                          <td className='px-4 py-3.5'>
                            <div className='flex gap-2' onClick={(e) => e.stopPropagation()}>
                              {l.status !== 'handling' && (
                                <button
                                  onClick={(e) => handleTake(l.id, e)}
                                  className='fx-body font-semibold text-[10.5px] rounded px-2 py-1'
                                  style={{ background: C.brand, color: '#fff' }}
                                >
                                  Prendre
                                </button>
                              )}
                              {l.status !== 'closed' && (
                                <button
                                  onClick={(e) => handleClose(l.id, e)}
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

          {selected && (
            <div
              className='w-full lg:w-[420px] flex flex-col rounded-2xl overflow-hidden fixed lg:static inset-0 lg:inset-auto z-30 lg:z-auto'
              style={{ background: C.surface, border: `1px solid ${C.border}`, boxShadow: SHADOW_MD }}
            >
              <div
                className='flex items-center justify-between px-4 py-3'
                style={{ borderBottom: `1px solid ${C.border}`, background: C.surfaceAlt }}
              >
                <div>
                  <p className='fx-body font-semibold text-[14px]'>{selected.client_name || 'Visiteur'}</p>
                  <p className='fx-mono text-[10.5px]' style={{ color: C.inkMuted }}>{selected.session_id}</p>
                </div>
                <button onClick={() => setSelected(null)} className='p-1 rounded hover:bg-gray-200' style={{ color: C.inkMuted }}>
                  <X size={18} />
                </button>
              </div>

              <div className='flex-1 overflow-y-auto p-4 fx-scroll' style={{ maxHeight: 'calc(100vh - 260px)' }}>
                {msgLoading && (
                  <p className='text-center text-[12px]' style={{ color: C.inkMuted }}>Chargement...</p>
                )}

                {isConv ? (
                  <>
                    {messages.map((m, idx) => {
                      const bubble = roleBubble(m.sender_role);
                      return (
                        <div key={idx} className='mb-3' style={{ display: 'flex', justifyContent: bubble.align }}>
                          <div
                            className='rounded-2xl px-3.5 py-2.5 max-w-[85%]'
                            style={{
                              background: bubble.bg,
                              color: bubble.color,
                              boxShadow: SHADOW_SM,
                              borderRadius: m.sender_role === 'client' ? '16px 16px 16px 4px' : '16px 16px 4px 16px',
                            }}
                          >
                            <p className='fx-body text-[12.5px]'>{m.content}</p>
                            <p className='text-[9px] mt-1 fx-mono' style={{ color: m.sender_role === 'client' ? 'rgba(255,255,255,0.7)' : C.inkMuted }}>
                              {formatDate(m.created_at)} · {roleLabel(m.sender_role)}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                    {messages.length === 0 && !msgLoading && (
                      <p className='text-center text-[12px] mt-8' style={{ color: C.inkMuted }}>Aucun message.</p>
                    )}
                  </>
                ) : (
                  <>
                    {thread.map((t) => (
                      <React.Fragment key={t.id}>
                        <div className='mb-3' style={{ display: 'flex', justifyContent: 'flex-start' }}>
                          <div
                            className='rounded-2xl rounded-tl-sm px-3.5 py-2.5 max-w-[85%]'
                            style={{ background: C.clientBg, color: '#fff', boxShadow: SHADOW_SM }}
                          >
                            <p className='fx-body text-[12.5px]'>{t.message}</p>
                            <p className='text-[9px] mt-1 opacity-70 fx-mono'>{formatDate(t.created_at)}</p>
                          </div>
                        </div>
                        {t.reply && (
                          <div className='mb-3' style={{ display: 'flex', justifyContent: 'flex-end' }}>
                            <div
                              className='rounded-2xl rounded-tr-sm px-3.5 py-2.5 max-w-[85%]'
                              style={{ background: C.aiBg, color: C.ink, boxShadow: SHADOW_SM }}
                            >
                              <p className='fx-body text-[12.5px]'>{t.reply}</p>
                              <p className='text-[9px] mt-1 fx-mono' style={{ color: C.inkMuted }}>{formatDate(t.created_at)} · Lia</p>
                            </div>
                          </div>
                        )}
                      </React.Fragment>
                    ))}
                    {thread.length === 0 && !msgLoading && (
                      <p className='text-center text-[12px] mt-8' style={{ color: C.inkMuted }}>Aucun message.</p>
                    )}
                  </>
                )}
                <div ref={messagesEndRef} />
              </div>

              <div className='p-3' style={{ borderTop: `1px solid ${C.border}` }}>
                {!isConv ? (
                  <p className='fx-body text-[12px] text-center py-2' style={{ color: C.inkMuted }}>
                    Cette conversation n'est pas liee a un client connecte.
                  </p>
                ) : (
                  <form onSubmit={handleSend} className='flex gap-2'>
                    <input
                      value={reply}
                      onChange={(e) => setReply(e.target.value)}
                      placeholder='Ecrire votre reponse...'
                      className='fx-body text-[13px] flex-1 px-3 py-2.5 rounded-lg outline-none'
                      style={{ background: C.surfaceAlt, border: `1px solid ${C.border}` }}
                    />
                    <button
                      type='submit'
                      disabled={sending || !reply.trim()}
                      className='flex items-center justify-center rounded-lg px-3'
                      style={{
                        background: C.brand,
                        color: '#fff',
                        opacity: sending || !reply.trim() ? 0.6 : 1,
                      }}
                    >
                      <Send size={16} />
                    </button>
                  </form>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
