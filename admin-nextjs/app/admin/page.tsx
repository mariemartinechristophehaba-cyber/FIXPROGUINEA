import Header from '@/components/Header';
import KPICard from '@/components/KPICard';
import StatusBadge from '@/components/StatusBadge';

const kpis = [
  { title: 'Techniciens inscrits', value: '48', change: '+12% ce mois', positive: true },
  { title: 'Demandes du mois', value: '128', change: '+8% ce mois', positive: true },
  { title: 'Revenus GNF', value: '4 250 000', change: '-3% ce mois', positive: false },
  { title: 'Avis moyen', value: '4.6/5', change: '+0.2', positive: true },
];

const demandes = [
  { id: '#D-001', client: 'Amadou Diallo', metier: 'Plomberie', zone: 'Kaloum', statut: 'new', montant: '150 000 GNF' },
  { id: '#D-002', client: 'Fatou Camara', metier: 'Electricite', zone: 'Dixinn', statut: 'assigned', montant: '225 000 GNF' },
  { id: '#D-003', client: 'Mamadou Barry', metier: 'Froid', zone: 'Matam', statut: 'done', montant: '180 000 GNF' },
  { id: '#D-004', client: 'Aminata Sow', metier: 'Menuiserie', zone: 'Coleah', statut: 'new', montant: '320 000 GNF' },
  { id: '#D-005', client: 'Ibrahim Sylla', metier: 'Plomberie', zone: 'Lambanyi', statut: 'assigned', montant: '95 000 GNF' },
];

const barData = [12, 18, 15, 22, 28, 24, 30];
const weeks = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7'];
const metiers = [
  { label: 'Plomberie', value: 40, color: 'bg-success' },
  { label: 'Electricite', value: 30, color: 'bg-warning' },
  { label: 'Froid', value: 15, color: 'bg-blue-500' },
  { label: 'Menuiserie', value: 10, color: 'bg-purple-500' },
  { label: 'Autres', value: 5, color: 'bg-white/30' },
];

export default function DashboardPage() {
  return (
    <div>
      <Header title="Tableau de bord" />
      <div className="p-6 space-y-8">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {kpis.map((k) => (
            <KPICard key={k.title} {...k} />
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-surface border border-border rounded-xl p-6">
            <h3 className="text-sm font-medium text-muted mb-4">Demandes par semaine</h3>
            <div className="flex items-end gap-3 h-48">
              {barData.map((v, i) => (
                <div key={i} className="flex-1 flex flex-col justify-end items-center gap-2 group">
                  <div
                    className="w-full bg-white/80 rounded-t-md transition-all group-hover:bg-white"
                    style={{ height: `${(v / 35) * 100}%` }}
                  />
                  <span className="text-xs text-muted">{weeks[i]}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-surface border border-border rounded-xl p-6">
            <h3 className="text-sm font-medium text-muted mb-4">Repartition par metier</h3>
            <div className="space-y-4">
              {metiers.map((m) => (
                <div key={m.label} className="flex items-center gap-4">
                  <span className="w-24 text-sm">{m.label}</span>
                  <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
                    <div className={`h-full ${m.color} rounded-full`} style={{ width: `${m.value}%` }} />
                  </div>
                  <span className="w-10 text-right text-sm text-muted">{m.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-surface border border-border rounded-xl p-6">
          <h3 className="text-sm font-medium text-muted mb-4">5 dernieres demandes</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-muted uppercase text-xs border-b border-border">
                <tr>
                  <th className="py-3 font-medium">ID</th>
                  <th className="py-3 font-medium">Client</th>
                  <th className="py-3 font-medium">Metier</th>
                  <th className="py-3 font-medium">Localisation</th>
                  <th className="py-3 font-medium">Statut</th>
                  <th className="py-3 font-medium">Montant</th>
                  <th className="py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {demandes.map((d) => (
                  <tr key={d.id} className="hover:bg-white/[0.03] transition-colors group">
                    <td className="py-3">{d.id}</td>
                    <td className="py-3">{d.client}</td>
                    <td className="py-3">{d.metier}</td>
                    <td className="py-3">{d.zone}</td>
                    <td className="py-3">
                      {d.statut === 'new' && <StatusBadge variant="warning">Nouveau</StatusBadge>}
                      {d.statut === 'assigned' && <StatusBadge variant="info">Assigne</StatusBadge>}
                      {d.statut === 'done' && <StatusBadge variant="success">Termine</StatusBadge>}
                    </td>
                    <td className="py-3">{d.montant}</td>
                    <td className="py-3">
                      <button className="opacity-0 group-hover:opacity-100 transition-opacity text-sm text-white hover:underline">
                        Voir
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
