/**
 * Session admin signee (HMAC-SHA256).
 *
 * Remplace les anciens cookies non signes `admin-token=1` / `admin-unlocked=1`,
 * qui pouvaient etre forges par n'importe quel visiteur. Le jeton contient
 * l'identite, l'etat de deverrouillage et une expiration, le tout scelle par
 * un secret serveur (ADMIN_SESSION_SECRET).
 *
 * Utilise l'API Web Crypto : fonctionne aussi bien dans le middleware (Edge)
 * que dans les Route Handlers (Node).
 */

const COOKIE_NAME = 'admin_session';
const MAX_AGE = 60 * 60 * 8; // 8 heures

function getSecret(): string {
  const secret = process.env.ADMIN_SESSION_SECRET;
  if (!secret || secret.length < 16) {
    throw new Error(
      'ADMIN_SESSION_SECRET manquant ou trop court (>= 16 caracteres requis).'
    );
  }
  return secret;
}

function b64urlEncode(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let bin = '';
  for (let i = 0; i < arr.length; i++) bin += String.fromCharCode(arr[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64urlDecode(str: string): Uint8Array {
  const pad = str.length % 4 ? 4 - (str.length % 4) : 0;
  const b64 = str.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat(pad);
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function hmac(data: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(getSecret()),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
  return b64urlEncode(sig);
}

/** Comparaison a temps constant (evite les attaques temporelles). */
export function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export interface AdminSession {
  sub: string;
  unlocked: boolean;
  iat: number;
  exp: number;
}

export async function createSessionToken(
  sub: string,
  unlocked: boolean
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const payload: AdminSession = { sub, unlocked, iat: now, exp: now + MAX_AGE };
  const body = b64urlEncode(new TextEncoder().encode(JSON.stringify(payload)));
  const sig = await hmac(body);
  return `${body}.${sig}`;
}

export async function verifySessionToken(
  token: string | undefined | null
): Promise<AdminSession | null> {
  if (!token || !token.includes('.')) return null;
  const [body, sig] = token.split('.', 2);

  let expected: string;
  try {
    expected = await hmac(body);
  } catch {
    return null; // secret non configure
  }
  if (!timingSafeEqual(sig, expected)) return null;

  let payload: AdminSession;
  try {
    payload = JSON.parse(new TextDecoder().decode(b64urlDecode(body)));
  } catch {
    return null;
  }
  if (!payload || typeof payload.exp !== 'number') return null;
  if (payload.exp < Math.floor(Date.now() / 1000)) return null;

  return payload;
}

export const SESSION_COOKIE = COOKIE_NAME;
export const SESSION_MAX_AGE = MAX_AGE;

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: MAX_AGE,
  };
}
