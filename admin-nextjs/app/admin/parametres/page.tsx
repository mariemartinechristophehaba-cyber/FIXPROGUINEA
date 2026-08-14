'use client';

import { useState } from 'react';
import Header from '@/components/Header';
import StatusBadge from '@/components/StatusBadge';

export default function ParametresPage() {
  const [tab, setTab] = useState<'infos' | 'paiement'>('infos');
  const [toast, setToast] = useState('');

  const [infos, setInfos] = useState({
    nom: 'FixPro Guinee',
    email: 'contact@fixproguinee.com',
    telephone: '+224 627 31 60 69',
    ville: 'Conakry',
    description: 'Plateforme de mise en relation entre clients et techniciens du batiment.',
  });

  const [paiement, setPaiement] = useState({
    apiKey: '••••••••••••••••',
    merchantId: 'OM-TEST-123456',
    commission: '10',
    devise: 'GNF',
  });

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  };

  return (
    <div>
      <Header title="Parametres" />
      <div className="p-6 max-w-3xl">
        <div className="flex items-center gap-4 border-b border-border mb-6">
          <button
            onClick={() => setTab('infos')}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              tab === 'infos' ? 'border-white text-white' : 'border-transparent text-muted hover:text-white'
            }`}
          >
            Informations
          </button>
          <button
            onClick={() => setTab('paiement')}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              tab === 'paiement' ? 'border-white text-white' : 'border-transparent text-muted hover:text-white'
            }`}
          >
            Paiement
          </button>
        </div>

        {toast && (
          <div className="mb-4 p-3 rounded-md bg-success/10 text-success text-sm">
            {toast}
          </div>
        )}

        {tab === 'infos' ? (
          <div className="bg-surface border border-border rounded-xl p-6 space-y-4">
            {[
              { label: 'Nom de la plateforme', key: 'nom' },
              { label: 'Email', key: 'email' },
              { label: 'Telephone', key: 'telephone' },
              { label: 'Ville', key: 'ville' },
            ].map((f) => (
              <div key={f.key}>
                <label className="block text-sm text-muted mb-1">{f.label}</label>
                <input
                  type="text"
                  value={(infos as any)[f.key]}
                  onChange={(e) => setInfos({ ...infos, [f.key]: e.target.value })}
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
                />
              </div>
            ))}
            <div>
              <label className="block text-sm text-muted mb-1">Description</label>
              <textarea
                value={infos.description}
                onChange={(e) => setInfos({ ...infos, description: e.target.value })}
                rows={4}
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
              />
            </div>
            <button
              onClick={() => showToast('Informations enregistrees (mock V1).')}
              className="px-6 py-2.5 bg-white text-black text-sm font-medium rounded-md hover:bg-white/90 transition-colors"
            >
              Enregistrer
            </button>
          </div>
        ) : (
          <div className="bg-surface border border-border rounded-xl p-6 space-y-4">
            <div>
              <label className="block text-sm text-muted mb-1">API Key Orange Money</label>
              <input
                type="password"
                value={paiement.apiKey}
                onChange={(e) => setPaiement({ ...paiement, apiKey: e.target.value })}
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
              />
            </div>
            <div>
              <label className="block text-sm text-muted mb-1">Merchant ID</label>
              <input
                type="text"
                value={paiement.merchantId}
                onChange={(e) => setPaiement({ ...paiement, merchantId: e.target.value })}
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-muted mb-1">Commission (%)</label>
                <input
                  type="number"
                  value={paiement.commission}
                  onChange={(e) => setPaiement({ ...paiement, commission: e.target.value })}
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
                />
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">Devise</label>
                <input
                  type="text"
                  value={paiement.devise}
                  readOnly
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm text-muted"
                />
              </div>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => showToast('Connexion simulee — API Orange Money non configuree.')}
                className="px-4 py-2 border border-border rounded-md text-sm hover:bg-white/5 transition-colors"
              >
                Tester la connexion
              </button>
              <StatusBadge variant="warning">Mock V1</StatusBadge>
            </div>
            <button
              onClick={() => showToast('Parametres de paiement enregistres (mock V1).')}
              className="px-6 py-2.5 bg-white text-black text-sm font-medium rounded-md hover:bg-white/90 transition-colors"
            >
              Enregistrer
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
