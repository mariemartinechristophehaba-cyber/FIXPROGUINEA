import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith('/admin/login')) {
    return NextResponse.next();
  }

  const token = request.cookies.get('admin-token')?.value;
  const unlocked = request.cookies.get('admin-unlocked')?.value;

  if (pathname.startsWith('/admin/unlock')) {
    if (!token) {
      return NextResponse.redirect(new URL('/admin/login', request.url));
    }
    return NextResponse.next();
  }

  if (!unlocked) {
    if (token) {
      return NextResponse.redirect(new URL('/admin/unlock', request.url));
    }
    return NextResponse.redirect(new URL('/admin/login', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/admin/:path*'],
};
