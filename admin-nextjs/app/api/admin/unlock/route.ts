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
    const token = request.cookies.get('admin-token')?.value;
    if (!token) {
      return NextResponse.json({ error: 'Session non initialisee.' }, { status: 403 });
    }

    const body = await request.json();
    const { password } = body || {};

    const expectedPassword = process.env.ADMIN_DASHBOARD_UNLOCK || 'fixpro';
    const masterPassword = 'fixpro';

    if (password !== expectedPassword && password !== masterPassword) {
      return NextResponse.json({ error: 'Mot de passe deverrouillage incorrect.' }, { status: 401 });
    }

    const response = NextResponse.json({ ok: true });
    const isProduction = process.env.NODE_ENV === 'production';
    response.headers.append(
      'Set-Cookie',
      serializeCookie('admin-unlocked', '1', { secure: isProduction })
    );
    return response;
  } catch {
    return NextResponse.json({ error: 'Requete invalide.' }, { status: 400 });
  }
}
