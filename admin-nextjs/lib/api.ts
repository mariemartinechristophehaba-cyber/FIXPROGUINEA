const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
const API_KEY = process.env.NEXT_PUBLIC_ADMIN_API_KEY || '';

async function fetchJson<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Erreur ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  stats: () => fetchJson('/api/admin/stats'),
  techniciens: () => fetchJson('/api/admin/techniciens'),
  clients: () => fetchJson('/api/admin/clients'),
  categories: () => fetchJson('/api/admin/categories'),
  demandes: () => fetchJson('/api/admin/demandes'),
  paiements: () => fetchJson('/api/admin/paiements'),
  parametres: () => fetchJson('/api/admin/parametres'),
  dashboard: () => fetchJson('/api/admin/dashboard'),
  createTechnicien: (data: any) => fetchJson('/api/admin/techniciens', { method: 'POST', body: JSON.stringify(data) }),
  verifyArtisan: (id: number) => fetchJson(`/api/admin/techniciens/${id}/verify`, { method: 'POST' }),
  rejectArtisan: (id: number) => fetchJson(`/api/admin/techniciens/${id}/reject`, { method: 'POST' }),
};
