import { NextRequest } from 'next/server';
export const dynamic = 'force-dynamic';
async function forward(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (path[0] !== 'v1' || path.some((p) => p === '..' || p.includes('/')))
    return Response.json({ detail: 'NOT_FOUND' }, { status: 404 });
  const base = process.env.HAYTILE_API_URL || 'http://127.0.0.1:8000';
  const target = new URL(
    '/' + path.map(encodeURIComponent).join('/') + request.nextUrl.search,
    base,
  );
  const headers = new Headers();
  for (const name of ['content-type', 'cookie', 'origin', 'authorization']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const body = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer();
    if (body && body.byteLength > 31 * 1024 * 1024)
      return Response.json({ detail: 'FILE_SIZE' }, { status: 413 });
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(60000),
      redirect: 'manual',
    });
    const resultHeaders = new Headers();
    for (const name of [
      'content-type',
      'content-disposition',
      'cache-control',
      'x-content-type-options',
      'content-security-policy',
    ]) {
      const value = upstream.headers.get(name);
      if (value) resultHeaders.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      resultHeaders.append('set-cookie', cookie);
    return new Response(upstream.body, { status: upstream.status, headers: resultHeaders });
  } catch {
    return Response.json({ detail: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }
}
export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
