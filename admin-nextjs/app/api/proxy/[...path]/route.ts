/**
 * Proxy serveur vers l'API admin Flask.
 *
 * Toutes les requetes du dashboard passent par ici. La cle ADMIN_API_KEY
 * reste cote serveur (jamais exposee au navigateur) et chaque appel exige
 * une session admin signee et deverrouillee.
 */

import { NextRequest, NextResponse } from 'next/server';
import { verifySessionToken, SESSION_COOKIE } from '@/lib/session';

const FLASK_URL = (
  process.env.FLASK_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://127.0.0.1:5000'
).replace(/\/$/, '');

async function guard(req: NextRequest): Promise<NextResponse | null> {
  const session = await verifySessionToken(req.cookies.get(SESSION_COOKIE)?.value);
  if (!session) {
    return NextResponse.json({ error: 'Non authentifie.' }, { status: 401 });
  }
  if (!session.unlocked) {
    return NextResponse.json({ error: 'Session non deverrouillee.' }, { status: 403 });
  }
  return null;
}

async function forward(
  req: NextRequest,
  segments: string[],
  method: 'GET' | 'POST'
): Promise<NextResponse> {
  const denied = await guard(req);
  if (denied) return denied;

  const key = process.env.ADMIN_API_KEY;
  if (!key) {
    return NextResponse.json(
      { error: 'ADMIN_API_KEY non configuree cote serveur.' },
      { status: 500 }
    );
  }

  const safePath = segments.map(encodeURIComponent).join('/');
  const search = req.nextUrl.search || '';
  const target = `${FLASK_URL}/api/admin/${safePath}${search}`;

  const init: RequestInit = {
    method,
    headers: { 'X-API-Key': key, 'Content-Type': 'application/json' },
    cache: 'no-store',
  };
  if (method === 'POST') {
    init.body = await req.text();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return NextResponse.json(
      { error: 'Backend injoignable.' },
      { status: 502 }
    );
  }

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') || 'application/json',
    },
  });
}

export async function GET(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return forward(req, params.path, 'GET');
}

export async function POST(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return forward(req, params.path, 'POST');
}
