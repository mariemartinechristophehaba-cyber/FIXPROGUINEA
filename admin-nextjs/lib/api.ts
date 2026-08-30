/**
 * Client API du dashboard admin.
 *
 * Les appels ne vont PLUS directement vers Flask : ils passent par le proxy
 * same-origin `/api/proxy/*`, qui detient la cle ADMIN_API_KEY cote serveur
 * et verifie la session. Aucun secret n'est expose au navigateur.
 */

async function fetchJson<T = any>(path: string, init?: RequestInit): Promise<T> {
  const proxyPath = path.replace(/^\/api\/admin/, '/api/proxy');
  const res = await fetch(proxyPath, {
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    if ((res.status === 401 || res.status === 403) && typeof window !== 'undefined') {
      window.location.href = '/admin/login';
    }
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
  liaLogs: (params: string = '') => fetchJson(`/api/admin/lia-logs?${params}`),
  liaLogMessages: (id: number) => fetchJson(`/api/admin/lia-logs/${id}/messages`),
  takeLiaLog: (id: number) => fetchJson(`/api/admin/lia-logs/${id}/take`, { method: 'POST' }),
  closeLiaLog: (id: number) => fetchJson(`/api/admin/lia-logs/${id}/close`, { method: 'POST' }),
  replyLiaLog: (id: number, message: string) => fetchJson(`/api/admin/lia-logs/${id}/reply`, { method: 'POST', body: JSON.stringify({ message }) }),
  dashboard: () => fetchJson('/api/admin/dashboard'),
  createTechnicien: (data: any) => fetchJson('/api/admin/techniciens', { method: 'POST', body: JSON.stringify(data) }),
  verifyArtisan: (id: number) => fetchJson(`/api/admin/techniciens/${id}/verify`, { method: 'POST' }),
  rejectArtisan: (id: number) => fetchJson(`/api/admin/techniciens/${id}/reject`, { method: 'POST' }),
};
