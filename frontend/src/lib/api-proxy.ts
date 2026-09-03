type ProxyOptions = {
  apiOrigin: string;
  frontendOrigin?: string;
  bffSecret?: string;
  developmentIdentity?: boolean;
  upstreamFetch?: typeof fetch;
};

function failure(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message } }, { status });
}

export async function proxyApiRequest(
  request: Request,
  options: ProxyOptions,
): Promise<Response> {
  const source = new URL(request.url);
  let publicOrigin: URL;
  try {
    publicOrigin = new URL(options.frontendOrigin || source.origin);
    if (
      !['http:', 'https:'].includes(publicOrigin.protocol) ||
      publicOrigin.username ||
      publicOrigin.password ||
      publicOrigin.pathname !== '/' ||
      publicOrigin.search ||
      publicOrigin.hash
    )
      throw new Error('Invalid FRONTEND_ORIGIN');
  } catch {
    return failure(
      503,
      'frontend_not_configured',
      'Địa chỉ frontend chưa được cấu hình hợp lệ.',
    );
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
    const origin = request.headers.get('origin');
    const fetchSite = request.headers.get('sec-fetch-site');
    if (
      (origin && origin !== publicOrigin.origin) ||
      (fetchSite && !['same-origin', 'none'].includes(fetchSite))
    ) {
      return failure(403, 'origin_rejected', 'Nguồn gửi yêu cầu không hợp lệ.');
    }
  }
  let target: URL;
  try {
    const base = new URL(options.apiOrigin);
    if (
      !['http:', 'https:'].includes(base.protocol) ||
      base.username ||
      base.password ||
      base.pathname !== '/' ||
      base.search ||
      base.hash
    )
      throw new Error('Invalid API_ORIGIN');
    target = new URL(source.pathname + source.search, base);
  } catch {
    return failure(
      503,
      'backend_not_configured',
      'Máy chủ API chưa được cấu hình hợp lệ.',
    );
  }
  const headers = new Headers(request.headers);
  for (const name of [
    'host',
    'connection',
    'content-length',
    'transfer-encoding',
    'accept-encoding',
    'cookie',
    'x-luatrag-bff-secret',
    'x-forwarded-host',
    'x-forwarded-proto',
  ])
    headers.delete(name);
  if (options.bffSecret) headers.set('x-luatrag-bff-secret', options.bffSecret);
  if (
    options.developmentIdentity &&
    ['localhost', '127.0.0.1', '[::1]'].includes(publicOrigin.hostname) &&
    (request.headers.get('host') || source.host) === publicOrigin.host &&
    !headers.has('oai-authenticated-user-id')
  ) {
    headers.set('oai-authenticated-user-id', 'local-development-user');
    headers.set('oai-authenticated-user-email', 'local@luatrag.test');
  }
  const init: RequestInit & { duplex?: 'half' } = {
    method: request.method,
    headers,
    redirect: 'manual',
    cache: 'no-store',
    signal: request.signal,
  };
  if (!['GET', 'HEAD'].includes(request.method) && request.body) {
    init.body = request.body;
    init.duplex = 'half';
  }
  try {
    const upstream = await (options.upstreamFetch || fetch)(target, init);
    const output = new Headers();
    for (const name of [
      'content-type',
      'content-disposition',
      'cache-control',
      'x-content-type-options',
      'allow',
      'retry-after',
    ]) {
      const value = upstream.headers.get(name);
      if (value) output.set(name, value);
    }
    output.set('cache-control', 'no-store');
    return new Response(request.method === 'HEAD' ? null : upstream.body, {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return failure(
      502,
      'backend_unavailable',
      'Không thể kết nối máy chủ API.',
    );
  }
}
