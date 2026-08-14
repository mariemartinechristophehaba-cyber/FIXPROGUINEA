'use client';

import { useState } from 'react';
import Header from '@/components/Header';
import StatusBadge from '@/components/StatusBadge';
import { Plus, Pencil, Trash2 } from 'lucide-react';

const allRows = [
  { id: 1, nom: 'Mamadou Bah', metier: 'Plomberie', zone: 'Kaloum', note: 4.8, statut: 'verified' },
  { id: 2, nom: 'Amadou Diallo', metier: 'Electricite', zone: 'Dixinn', note: 4.2, statut: 'pending' },
  { id: 3, nom: 'Fatou Camara', metier: 'Froid', zone: 'Matam', note: 4.5, statut: 'verified' },
  { id: 4, nom: 'Ibrahim Sylla', metier: 'Menuiserie', zone: 'Coleah', note: 3.9, statut: 'rejected' },
];

export default function TechniciensPage() {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 5;

  const filtered = allRows.filter((r) =>
    [r.nom, r.metier, r.zone].some((v) => v.toLowerCase().includes(query.toLowerCase()))
  );
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const start = (page - 1) * pageSize;
  const rows = filtered.slice(start, start + pageSize);

  return (
    <div>
      <Header title="Techniciens" />
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium">Liste des techniciens</h3>
          <button className="flex items-center gap-2 px-4 py-2 bg-white text-black text-sm font-medium rounded-md hover:bg-white/90 transition-colors">
            <Plus size={16} />
            Ajouter
          </button>
        </div>

        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setPage(1); }}
          placeholder="Rechercher..."
          className="w-full max-w-sm bg-surface border border-border rounded-md px-4 py-2 text-sm focus:outline-none focus:border-white/30"
        />

        <div className="overflow-x-auto border border-border rounded-xl">
          <table className="w-full text-sm text-left">
            <thead className="bg-white/5 text-muted uppercase text-xs">
              <tr>
                <th className="px-4 py-3 font-medium">Nom</th>
                <th className="px-4 py-3 font-medium">Metier</th>
                <th className="px-4 py-3 font-medium">Zone</th>
                <th className="px-4 py-3 font-medium">Note</th>
                <th className="px-4 py-3 font-medium">Statut</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-white/[0.03] transition-colors group">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-xs font-medium">
                        {row.nom.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
                      </div>
                      <span className="font-medium">{row.nom}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">{row.metier}</td>
                  <td className="px-4 py-3">{row.zone}</td>
                  <td className="px-4 py-3">{row.note}</td>
                  <td className="px-4 py-3">
                    {row.statut === 'verified' ? <StatusBadge variant="success">Verifie</StatusBadge> :
                     row.statut === 'pending' ? <StatusBadge variant="warning">En attente</StatusBadge> :
                     <StatusBadge variant="danger">Refuse</StatusBadge>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button className="p-1.5 hover:bg-white/10 rounded"><Pencil size={16} /></button>
                      <button className="p-1.5 hover:bg-white/10 rounded text-danger"><Trash2 size={16} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted">{filtered.length} resultat(s)</span>
            <div className="flex items-center gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
                className="px-3 py-1 rounded-md border border-border disabled:opacity-40 hover:bg-white/5"
              >
                Precedent
              </button>
              <span className="text-muted">{page} / {totalPages}</span>
              <button
                disabled={page === totalPages}
                onClick={() => setPage(page + 1)}
                className="px-3 py-1 rounded-md border border-border disabled:opacity-40 hover:bg-white/5"
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
