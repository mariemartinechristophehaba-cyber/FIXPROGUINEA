import Header from '@/components/Header';
import StatusBadge from '@/components/StatusBadge';
import { Eye } from 'lucide-react';

const demandes = [
  { id: '#D-001', client: 'Amadou Diallo', telephone: '+224 620 00 00 01', metier: 'Plomberie', zone: 'Kaloum', date: '2025-08-12', statut: 'new', montant: '150 000 GNF' },
  { id: '#D-002', client: 'Fatou Camara', telephone: '+224 620 00 00 02', metier: 'Electricite', zone: 'Dixinn', date: '2025-08-11', statut: 'assigned', montant: '225 000 GNF' },
  { id: '#D-003', client: 'Mamadou Barry', telephone: '+224 620 00 00 03', metier: 'Froid', zone: 'Matam', date: '2025-08-10', statut: 'done', montant: '180 000 GNF' },
  { id: '#D-004', client: 'Aminata Sow', telephone: '+224 620 00 00 04', metier: 'Menuiserie', zone: 'Coleah', date: '2025-08-09', statut: 'new', montant: '320 000 GNF' },
];

const statusLabel: Record<string, string> = { new: 'Nouveau', assigned: 'Assigne', done: 'Termine' };

export default function DemandesPage() {
  return (
    <div>
      <Header title="Demandes" />
      <div className="p-6 space-y-6">
        <h3 className="text-lg font-medium">Demandes d'intervention</h3>
        <div className="overflow-x-auto border border-border rounded-xl">
          <table className="w-full text-sm text-left">
            <thead className="bg-white/5 text-muted uppercase text-xs">
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
            <tbody className="divide-y divide-border">
              {demandes.map((d) => (
                <tr key={d.id} className="hover:bg-white/[0.03] transition-colors group">
                  <td className="px-4 py-3">{d.id}</td>
                  <td className="px-4 py-3">{d.client}</td>
                  <td className="px-4 py-3">{d.telephone}</td>
                  <td className="px-4 py-3">{d.metier}</td>
                  <td className="px-4 py-3">{d.zone}</td>
                  <td className="px-4 py-3">{d.date}</td>
                  <td className="px-4 py-3">
                    {d.statut === 'new' ? <StatusBadge variant="warning">{statusLabel[d.statut]}</StatusBadge> :
                     d.statut === 'assigned' ? <StatusBadge variant="info">{statusLabel[d.statut]}</StatusBadge> :
                     <StatusBadge variant="success">{statusLabel[d.statut]}</StatusBadge>}
                  </td>
                  <td className="px-4 py-3">{d.montant}</td>
                  <td className="px-4 py-3">
                    <button className="p-1.5 hover:bg-white/10 rounded opacity-0 group-hover:opacity-100 transition-opacity">
                      <Eye size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
