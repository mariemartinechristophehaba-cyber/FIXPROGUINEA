'use client';

import { useState } from 'react';
import Header from '@/components/Header';
import { Smartphone, Globe, FileText, Server, MessageCircle, BarChart3 } from 'lucide-react';

const types = [
  { id: 'mobile', label: 'App mobile', icon: Smartphone, desc: 'Application iOS & Android' },
  { id: 'web', label: 'Web app', icon: Globe, desc: 'Application web React/Next.js' },
  { id: 'landing', label: 'Landing page', icon: FileText, desc: 'Page de presentation' },
  { id: 'api', label: 'API backend', icon: Server, desc: 'API REST securisee' },
  { id: 'chatbot', label: 'Chatbot WhatsApp', icon: MessageCircle, desc: 'Automatisation WhatsApp' },
  { id: 'analytics', label: 'Module analytics', icon: BarChart3, desc: 'Tableaux et statistiques' },
];

export default function GenerateurPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [done, setDone] = useState(false);
  const [form, setForm] = useState({
    nom: '',
    langue: 'fr',
    db: 'postgresql',
    hosting: 'vercel',
    auth: true,
    paiement: true,
    chat: false,
    notifications: false,
    gps: false,
    avis: false,
  });

  const handleGenerate = () => {
    if (!selected || !form.nom) return;
    setGenerating(true);
    setDone(false);
    setProgress(0);

    let step = 0;
    const interval = setInterval(() => {
      step += 4;
      setProgress(step);
      if (step >= 100) {
        clearInterval(interval);
        setGenerating(false);
        setDone(true);
      }
    }, 120);
  };

  return (
    <div>
      <Header title="Generateur d'applications" />
      <div className="p-6 space-y-8 max-w-5xl">
        <h3 className="text-lg font-medium">Choisissez un type d'application</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {types.map((t) => {
            const Icon = t.icon;
            const active = selected === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setSelected(t.id)}
                className={`text-left p-5 rounded-xl border transition-all ${
                  active ? 'bg-white/10 border-white/30' : 'bg-surface border-border hover:border-white/20'
                }`}
              >
                <Icon size={24} className={active ? 'text-white' : 'text-muted'} />
                <div className="mt-3 font-medium">{t.label}</div>
                <div className="text-xs text-muted mt-1">{t.desc}</div>
              </button>
            );
          })}
        </div>

        {selected && (
          <div className="bg-surface border border-border rounded-xl p-6 space-y-5">
            <h4 className="font-medium">Configuration</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-muted mb-1">Nom du projet</label>
                <input
                  type="text"
                  value={form.nom}
                  onChange={(e) => setForm({ ...form, nom: e.target.value })}
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
                  placeholder="Ex : FixPro Client"
                />
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">Langue</label>
                <select
                  value={form.langue}
                  onChange={(e) => setForm({ ...form, langue: e.target.value })}
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
                >
                  <option value="fr">Francais</option>
                  <option value="en">Anglais</option>
                  <option value="bilingual">Bilingue</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">Base de donnees</label>
                <select
                  value={form.db}
                  onChange={(e) => setForm({ ...form, db: e.target.value })}
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
                >
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mongodb">MongoDB</option>
                  <option value="firebase">Firebase</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">Hebergement</label>
                <select
                  value={form.hosting}
                  onChange={(e) => setForm({ ...form, hosting: e.target.value })}
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-white/30"
                >
                  <option value="vercel">Vercel</option>
                  <option value="aws">AWS</option>
                  <option value="firebase">Firebase</option>
                  <option value="dedicated">Dedie</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                { key: 'auth', label: 'Auth' },
                { key: 'paiement', label: 'Paiement OM' },
                { key: 'chat', label: 'Chat' },
                { key: 'notifications', label: 'Notifications push' },
                { key: 'gps', label: 'GPS' },
                { key: 'avis', label: 'Avis' },
              ].map((f) => (
                <label key={f.key} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={(form as any)[f.key]}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.checked } as any)}
                    className="rounded border-border bg-background"
                  />
                  {f.label}
                </label>
              ))}
            </div>

            {generating && (
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-muted">
                  <span>Generation en cours...</span>
                  <span>{progress}%</span>
                </div>
                <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                  <div className="h-full bg-white rounded-full transition-all duration-100" style={{ width: `${progress}%` }} />
                </div>
              </div>
            )}

            {done && (
              <div className="p-3 rounded-md bg-success/10 text-success text-sm">
                Application "{form.nom}" generee avec succes (mock V1).
              </div>
            )}

            <button
              onClick={handleGenerate}
              disabled={generating || !form.nom}
              className="px-6 py-2.5 bg-white text-black text-sm font-medium rounded-md hover:bg-white/90 disabled:opacity-50 transition-colors"
            >
              {generating ? 'Generation...' : 'Generer'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
