'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Bell } from 'lucide-react';

export default function Notifications() {
  const [pending, setPending] = useState(0);

  const check = async () => {
    try {
      const stats = await api.stats();
      setPending(stats.pending_artisans || 0);
    } catch {
      // Silencieux si l'API n'est pas joignable
    }
  };

  useEffect(() => {
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Link href="/admin/techniciens/" className="relative p-2 hover:bg-white/5 rounded-md transition-colors">
      <Bell size={20} />
      {pending > 0 && (
        <>
          <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-orange-500 rounded-full animate-ping" />
          <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-orange-500 rounded-full" />
        </>
      )}
    </Link>
  );
}
