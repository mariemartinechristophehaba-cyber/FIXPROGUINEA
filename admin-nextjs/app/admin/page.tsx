import Header from '@/components/Header';
import KPICard from '@/components/KPICard';
import StatusBadge from '@/components/StatusBadge';
import { api } from '@/lib/api';

const barData = [12, 18, 15, 22, 28, 24, 30];
const weeks = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7'];
const metiers = [
  { label: 'Plomberie', value: 40, color: 'bg-emerald-500' },
  { label: 'Electricite', value: 30, color: 'bg-orange-500' },
  { label: 'Froid', value: 15, color: 'bg-blue-500' },
  { label: 'Menuiserie', value: 10, color: 'bg-purple-500' },
  { label: 'Autres', value: 5, color: 'bg-zinc-500' },
];

function statusBadge(statut: string) {
  if (statut === 'new') return <StatusBadge variant="warning">Nouveau</StatusBadge>;
  if (statut === 'assigned') return <StatusBadge variant="info">Assigne</StatusBadge>;
  if (statut === 'done' || statut === 'completed') return <StatusBadge variant="success">Termine</StatusBadge>;
  if (statut === 'cancelled') return <StatusBadge variant="danger">Annule</StatusBadge>;
  return <StatusBadge variant="neutral">{statut}</StatusBadge>;
}

export default async function DashboardPage() {
  let stats: any = {};
  let demandes: any[] = [];
  try {
    stats = await api.stats();
    demandes = await api.demandes();
  } catch (e) {
    console.error(e);
  }

  const kpis = [
    { title: 'Techniciens inscrits', value: String(stats.techniciens || 0), change: '+12% ce mois', positive: true },
    { title: 'Demandes du mois', value: String(stats.demandes_mois || 0), change: '+8% ce mois', positive: true },
    { title: 'Revenus GNF', value: `${(stats.revenus || 0).toLocaleString('fr-FR')}`, change: '-3% ce mois', positive: false },
    { title: 'Avis moyen', value: `${(stats.avis_moyen || 0).toFixed(1)}/5`, change: '+0.2', positive: true },
  ];

  const recent = demandes.slice(0, 5);

  return (
    <div>
      <Header title="Tableau de bord" />
      <div className="p-6 space-y-8">
        {(stats.pending_artisans || 0) > 0 && (
          <div className="bg-orange-500/10 border border-orange-500/20 rounded-xl p-4 flex items-center justify-between">
            <div>
              <div className="font-medium text-orange-400">
                {stats.pending_artisans} inscription(s) en attente de validation
              </div>
              <div className="text-sm text-zinc-400">
                Un nouvel artisan s'est inscrit. Veuillez verifier son dossier.
              </div>
            </div>
            <a href="/admin/techniciens/" className="px-4 py-2 bg-orange-500 text-black text-sm font-medium rounded-md hover:bg-orange-400 transition-colors">
              Voir les inscriptions
            </a>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {kpis.map((k) => (
            <KPICard key={k.title} {...k} />
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Demandes par semaine</h3>
            <div className="flex items-end gap-3 h-48">
              {barData.map((v, i) => (
                <div key={i} className="flex-1 flex flex-col justify-end items-center gap-2 group">
                  <div
                    className="w-full bg-zinc-200 rounded-t-md transition-all group-hover:bg-white"
                    style={{ height: `${(v / 35) * 100}%` }}
                  />
                  <span className="text-xs text-zinc-500">{weeks[i]}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Repartition par metier</h3>
            <div className="space-y-4">
              {metiers.map((m) => (
                <div key={m.label} className="flex items-center gap-4">
                  <span className="w-24 text-sm">{m.label}</span>
                  <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div className={`h-full ${m.color} rounded-full`} style={{ width: `${m.value}%` }} />
                  </div>
                  <span className="w-10 text-right text-sm text-zinc-500">{m.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Demandes recentes</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-zinc-400 uppercase text-xs border-b border-zinc-800">
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
              <tbody className="divide-y divide-zinc-800">
                {recent.map((d: any) => (
                  <tr key={d.id} className="hover:bg-white/[0.03] transition-colors group">
                    <td className="py-3">#{d.id}</td>
                    <td className="py-3">{d.client_name || d.client_nom}</td>
                    <td className="py-3">{d.metier}</td>
                    <td className="py-3">{d.zone}</td>
                    <td className="py-3">{statusBadge(d.statut)}</td>
                    <td className="py-3">{d.montant ? `${Number(d.montant).toLocaleString('fr-FR')} GNF` : '—'}</td>
                    <td className="py-3">
                      <button className="opacity-0 group-hover:opacity-100 transition-opacity text-sm text-white hover:underline">
                        Voir
                      </button>
                    </td>
                  </tr>
                ))}
                {recent.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-zinc-500">Aucune demande</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
