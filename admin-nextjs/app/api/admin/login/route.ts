import { NextResponse, NextRequest } from 'next/server';
import {
  createSessionToken,
  timingSafeEqual,
  SESSION_COOKIE,
  sessionCookieOptions,
} from '@/lib/session';

export async function POST(request: NextRequest) {
  const expectedEmail = process.env.ADMIN_DASHBOARD_EMAIL;
  const expectedPassword = process.env.ADMIN_DASHBOARD_PASSWORD;

  if (!expectedEmail || !expectedPassword) {
    return NextResponse.json(
      { error: 'Authentification admin non configuree.' },
      { status: 500 }
    );
  }

  let body: any;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Requete invalide.' }, { status: 400 });
  }

  const email = String(body?.email || '').trim().toLowerCase();
  const password = String(body?.password || '');

  const ok =
    timingSafeEqual(email, expectedEmail.trim().toLowerCase()) &&
    timingSafeEqual(password, expectedPassword);

  if (!ok) {
    return NextResponse.json(
      { error: 'Email ou mot de passe incorrect.' },
      { status: 401 }
    );
  }

  let token: string;
  try {
    token = await createSessionToken(email, false);
  } catch {
    return NextResponse.json(
      { error: 'ADMIN_SESSION_SECRET non configure cote serveur.' },
      { status: 500 }
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, token, sessionCookieOptions());
  return response;
}
