import { NextResponse, NextRequest } from 'next/server';
import {
  verifySessionToken,
  createSessionToken,
  timingSafeEqual,
  SESSION_COOKIE,
  sessionCookieOptions,
} from '@/lib/session';

export async function POST(request: NextRequest) {
  const session = await verifySessionToken(
    request.cookies.get(SESSION_COOKIE)?.value
  );
  if (!session) {
    return NextResponse.json({ error: 'Session non initialisee.' }, { status: 401 });
  }

  const expected = process.env.ADMIN_DASHBOARD_UNLOCK;
  if (!expected) {
    return NextResponse.json(
      { error: 'Deverrouillage admin non configure.' },
      { status: 500 }
    );
  }

  let body: any;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Requete invalide.' }, { status: 400 });
  }

  const password = String(body?.password || '');

  if (!timingSafeEqual(password, expected)) {
    return NextResponse.json(
      { error: 'Mot de passe deverrouillage incorrect.' },
      { status: 401 }
    );
  }

  const token = await createSessionToken(session.sub, true);
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, token, sessionCookieOptions());
  return response;
}
