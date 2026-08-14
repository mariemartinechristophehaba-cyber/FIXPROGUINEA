'use client';

import { useEffect, useState } from 'react';
import Header from '@/components/Header';
import StatusBadge from '@/components/StatusBadge';
import { api } from '@/lib/api';
import { Plus, Pencil, Trash2 } from 'lucide-react';

function statusBadge(statut: string) {
  if (statut === 'verified' || statut === '1') return <StatusBadge variant="success">Verifie</StatusBadge>;
  if (statut === 'pending' || statut === '0') return <StatusBadge variant="warning">En attente</StatusBadge>;
  return <StatusBadge variant="danger">Refuse</StatusBadge>;
}

export default function TechniciensPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 5;

  const load = async () => {
    setError('');
    setLoading(true);
    try {
      const data = await api.techniciens();
      setRows(data);
    } catch (e: any) {
      setError(e.message || 'Impossible de charger les techniciens.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const filtered = rows.filter((r) =>
    [r.full_name, r.profession, r.city, r.zone, r.quartier].some((v) =>
      String(v || '').toLowerCase().includes(query.toLowerCase())
    )
  );
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const start = (page - 1) * pageSize;
  const visible = filtered.slice(start, start + pageSize);

  const verify = async (id: number) => {
    try {
      await api.verifyArtisan(id);
      load();
    } catch (e: any) {
      setError(e.message || 'Erreur lors de la validation.');
    }
  };

  const reject = async (id: number) => {
    if (!confirm('Refuser ce technicien ?')) return;
    try {
      await api.rejectArtisan(id);
      load();
    } catch (e: any) {
      setError(e.message || 'Erreur lors du refus.');
    }
  };

  return (
    <div>
      <Header title="Techniciens" />
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium">Liste des techniciens</h3>
          <button className="flex items-center gap-2 px-4 py-2 bg-white text-black text-sm font-medium rounded-md hover:bg-zinc-200 transition-colors">
            <Plus size={16} />
            Ajouter
          </button>
        </div>

        {error && (
          <div className="p-3 rounded-md bg-red-500/10 text-red-400 text-sm border border-red-500/20">
            {error}
          </div>
        )}

        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setPage(1); }}
          placeholder="Rechercher..."
          className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-md px-4 py-2 text-sm focus:outline-none focus:border-white/30"
        />

        <div className="overflow-x-auto border border-zinc-800 rounded-xl">
          <table className="w-full text-sm text-left">
            <thead className="bg-white/5 text-zinc-400 uppercase text-xs">
              <tr>
                <th className="px-4 py-3 font-medium">Nom</th>
                <th className="px-4 py-3 font-medium">Metier</th>
                <th className="px-4 py-3 font-medium">Zone</th>
                <th className="px-4 py-3 font-medium">Note</th>
                <th className="px-4 py-3 font-medium">Statut</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-500">Chargement...</td></tr>
              ) : visible.map((row: any) => (
                <tr key={row.id} className="hover:bg-white/[0.03] transition-colors group">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-xs font-medium">
                        {String(row.full_name || '').split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()}
                      </div>
                      <span className="font-medium">{row.full_name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">{row.profession || '—'}</td>
                  <td className="px-4 py-3">{row.city || row.zone || '—'}</td>
                  <td className="px-4 py-3">{row.avg_rating ? Number(row.avg_rating).toFixed(1) : '—'}</td>
                  <td className="px-4 py-3">{statusBadge(String(row.is_verified))}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {row.is_verified === 0 && (
                        <button onClick={() => verify(row.id)} className="px-2 py-1 text-xs bg-emerald-500/10 text-emerald-400 rounded hover:bg-emerald-500/20">Accepter</button>
                      )}
                      {row.is_verified === 0 && (
                        <button onClick={() => reject(row.id)} className="px-2 py-1 text-xs bg-red-500/10 text-red-400 rounded hover:bg-red-500/20">Refuser</button>
                      )}
                      <button className="p-1.5 hover:bg-white/10 rounded opacity-0 group-hover:opacity-100 transition-opacity"><Pencil size={16} /></button>
                      <button className="p-1.5 hover:bg-white/10 rounded text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 size={16} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && visible.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-500">Aucun technicien</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-zinc-500">{filtered.length} resultat(s)</span>
            <div className="flex items-center gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
                className="px-3 py-1 rounded-md border border-zinc-800 disabled:opacity-40 hover:bg-white/5"
              >
                Precedent
              </button>
              <span className="text-zinc-500">{page} / {totalPages}</span>
              <button
                disabled={page === totalPages}
                onClick={() => setPage(page + 1)}
                className="px-3 py-1 rounded-md border border-zinc-800 disabled:opacity-40 hover:bg-white/5"
              >
                Suivant
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
