'use client';

import { usePathname } from 'next/navigation';
import Sidebar from '@/components/Sidebar';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === '/admin/dashboard' || pathname === '/admin/interventions' || pathname === '/admin/techniciens' || pathname === '/admin/clients') {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 lg:ml-[220px]">
        {children}
      </main>
    </div>
  );
}
