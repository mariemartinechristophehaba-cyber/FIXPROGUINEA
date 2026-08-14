'use client';

import { useEffect, useState } from 'react';
import Header from '@/components/Header';
import StatusBadge from '@/components/StatusBadge';
import { api } from '@/lib/api';
import { Eye } from 'lucide-react';

const statusLabel: Record<string, string> = { new: 'Nouveau', assigned: 'Assigne', done: 'Termine', completed: 'Termine', cancelled: 'Annule' };

function statusBadge(statut: string) {
  const s = statut || 'new';
  if (s === 'new') return <StatusBadge variant="warning">{statusLabel[s]}</StatusBadge>;
  if (s === 'assigned') return <StatusBadge variant="info">{statusLabel[s]}</StatusBadge>;
  if (s === 'done' || s === 'completed') return <StatusBadge variant="success">{statusLabel[s]}</StatusBadge>;
  return <StatusBadge variant="danger">{statusLabel[s]}</StatusBadge>;
}

export default function DemandesPage() {
  const [demandes, setDemandes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.demandes()
      .then((d) => { setDemandes(d); setLoading(false); })
      .catch((e: any) => { setError(e.message || 'Impossible de charger les demandes.'); setLoading(false); });
  }, []);

  return (
    <div>
      <Header title="Demandes" />
      <div className="p-6 space-y-6">
        <h3 className="text-lg font-medium">Demandes d'intervention</h3>

        {error && (
          <div className="p-3 rounded-md bg-red-500/10 text-red-400 text-sm border border-red-500/20">
            {error}
          </div>
        )}

        <div className="overflow-x-auto border border-zinc-800 rounded-xl">
          <table className="w-full text-sm text-left">
            <thead className="bg-white/5 text-zinc-400 uppercase text-xs">
              <tr>
                <th className="px-4 py-3 font-medium">ID demande</th>
                <th className="px-4 py-3 font-medium">Client</th>
                <th className="px-4 py-3 font-medium">Telephone</th>
                <th className="px-4 py-3 font-medium">Metier</th>
                <th className="px-4 py-3 font-medium">Zone</th>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Statut</th>
                <th className="px-4 py-3 font-medium">Montant</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {loading ? (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-zinc-500">Chargement...</td></tr>
              ) : demandes.map((d: any) => (
                <tr key={d.id} className="hover:bg-white/[0.03] transition-colors group">
                  <td className="px-4 py-3">#{d.id}</td>
                  <td className="px-4 py-3">{d.client_name || d.client_nom}</td>
                  <td className="px-4 py-3">{d.client_phone || d.client_tel || '—'}</td>
                  <td className="px-4 py-3">{d.metier}</td>
                  <td className="px-4 py-3">{d.zone}</td>
                  <td className="px-4 py-3">{d.created_at ? d.created_at.slice(0, 10) : '—'}</td>
                  <td className="px-4 py-3">{statusBadge(d.statut)}</td>
                  <td className="px-4 py-3">{d.montant ? `${Number(d.montant).toLocaleString('fr-FR')} GNF` : '—'}</td>
                  <td className="px-4 py-3">
                    <button className="p-1.5 hover:bg-white/10 rounded opacity-0 group-hover:opacity-100 transition-opacity">
                      <Eye size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && demandes.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-zinc-500">Aucune demande</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
