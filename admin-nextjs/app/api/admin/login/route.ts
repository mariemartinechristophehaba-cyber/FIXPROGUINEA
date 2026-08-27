import { NextResponse, NextRequest } from 'next/server';

function serializeCookie(
  name: string,
  value: string,
  options: { httpOnly?: boolean; secure?: boolean; sameSite?: string; maxAge?: number; path?: string } = {}
) {
  const { httpOnly = true, secure = false, sameSite = 'Lax', maxAge = 86400, path = '/' } = options;
  let cookie = `${name}=${encodeURIComponent(value)}; Path=${path}; Max-Age=${maxAge}; SameSite=${sameSite}`;
  if (httpOnly) cookie += '; HttpOnly';
  if (secure) cookie += '; Secure';
  return cookie;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { email, password } = body || {};

    const expectedEmail = process.env.ADMIN_DASHBOARD_EMAIL || 'admin@fixpro.local';
    const expectedPassword = process.env.ADMIN_DASHBOARD_PASSWORD || 'admin';

    if (email !== expectedEmail || password !== expectedPassword) {
      return NextResponse.json({ error: 'Email ou mot de passe incorrect.' }, { status: 401 });
    }

    const response = NextResponse.json({ ok: true });
    const isProduction = process.env.NODE_ENV === 'production';
    response.headers.append(
      'Set-Cookie',
      serializeCookie('admin-token', '1', { secure: isProduction })
    );
    return response;
  } catch {
    return NextResponse.json({ error: 'Requete invalide.' }, { status: 400 });
  }
}
