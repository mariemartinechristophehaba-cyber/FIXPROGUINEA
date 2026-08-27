'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shield } from 'lucide-react';

export default function AdminUnlockPage() {
  const router = useRouter();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const res = await fetch('/api/admin/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error || 'Mot de passe deverrouillage incorrect.');
        return;
      }

      router.push('/admin/dashboard');
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
          <p className='text-sm text-[#6B7284] mt-2'>Deuxieme verrou du tableau de bord</p>
        </div>

        {error && (
          <div className='mb-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm'>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className='space-y-5'>
          <div>
            <label className='block text-sm font-medium text-[#6B7284] mb-1.5'>Code / mot de passe admin</label>
            <div className='relative'>
              <Shield className='absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7284]' size={18} />
              <input
                type='password'
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder='Mot de passe de deverrouillage'
                className='w-full pl-10 pr-4 py-3 rounded-lg border border-[#E1E4EC] focus:outline-none focus:border-[#1E3A8A] text-sm'
              />
            </div>
          </div>

          <button
            type='submit'
            disabled={loading}
            className='w-full py-3 bg-[#1E3A8A] text-white rounded-lg font-semibold hover:bg-[#152B69] transition-colors disabled:opacity-60'
          >
            {loading ? 'Deverrouillage...' : 'Deverrouiller'}
          </button>
        </form>

        <p className='text-xs text-center text-[#6B7284] mt-6'>
          Face ID / empreinte digitale en preparation.
        </p>
      </div>
    </div>
  );
}
