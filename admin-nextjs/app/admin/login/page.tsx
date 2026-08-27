'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Mail, Lock } from 'lucide-react';

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const res = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error || 'Email ou mot de passe incorrect.');
        return;
      }

      router.push('/admin/unlock');
    } catch {
      setError('Erreur reseau. Veuillez reessayer.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className='min-h-screen flex items-center justify-center bg-[#F4F5F8] text-[#10162B] p-4'>
      <div className='w-full max-w-md bg-white rounded-2xl shadow-lg p-8'>
        <div className='text-center mb-8'>
          <h1 className='text-2xl font-bold'>FixPro <span className='text-[#1E3A8A]'>Admin</span></h1>
          <p className='text-sm text-[#6B7284] mt-2'>Connexion securisee au tableau de bord</p>
        </div>

        {error && (
          <div className='mb-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm'>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className='space-y-5'>
          <div>
            <label className='block text-sm font-medium text-[#6B7284] mb-1.5'>Adresse e-mail</label>
            <div className='relative'>
              <Mail className='absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7284]' size={18} />
              <input
                type='email'
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder='admin@fixpro.app'
                className='w-full pl-10 pr-4 py-3 rounded-lg border border-[#E1E4EC] focus:outline-none focus:border-[#1E3A8A] text-sm'
              />
            </div>
          </div>

          <div>
            <label className='block text-sm font-medium text-[#6B7284] mb-1.5'>Mot de passe</label>
            <div className='relative'>
              <Lock className='absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7284]' size={18} />
              <input
                type='password'
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder='Votre mot de passe'
                className='w-full pl-10 pr-4 py-3 rounded-lg border border-[#E1E4EC] focus:outline-none focus:border-[#1E3A8A] text-sm'
              />
            </div>
          </div>

          <button
            type='submit'
            disabled={loading}
            className='w-full py-3 bg-[#1E3A8A] text-white rounded-lg font-semibold hover:bg-[#152B69] transition-colors disabled:opacity-60'
          >
            {loading ? 'Connexion...' : 'Se connecter'}
          </button>
        </form>

        <p className='text-xs text-center text-[#6B7284] mt-6'>
          Le Face ID / empreinte arrive dans une prochaine version.
        </p>
      </div>
    </div>
  );
}
