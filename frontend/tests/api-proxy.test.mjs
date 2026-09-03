import assert from 'node:assert/strict';
import test from 'node:test';
import { proxyApiRequest } from '../src/lib/api-proxy.ts';

test('Docker development identity is explicit, loopback-only and never replaces an identity', async () => {
  for (const [url, enabled, identity, expected] of [
    ['http://localhost:3018/api/health', true, null, 'local-development-user'],
    ['https://luatrag.example/api/health', true, null, null],
    ['http://localhost:3018/api/health', false, null, null],
    ['http://localhost:3018/api/health', true, 'user-1', 'user-1'],
  ]) {
    const headers = identity ? { 'oai-authenticated-user-id': identity } : {};
    const response = await proxyApiRequest(new Request(url, { headers }), {
      apiOrigin: 'http://backend:8000',
      developmentIdentity: enabled,
      upstreamFetch: async (_url, init) => {
        assert.equal(init.headers.get('oai-authenticated-user-id'), expected);
        return Response.json({ status: 'ok' });
      },
    });
    assert.equal(response.status, 200);
  }
});

test('BFF rejects cross-origin mutations before contacting the backend', async () => {
  const response = await proxyApiRequest(
    new Request('https://luatrag.example/api/ask', {
      method: 'POST',
      headers: { origin: 'https://attacker.example' },
    }),
    {
      apiOrigin: 'http://127.0.0.1:8000',
      upstreamFetch: () => {
        throw new Error('Should not fetch');
      },
    },
  );
  assert.equal(response.status, 403);
});

test('Docker proxy checks the configured public origin, not the internal container URL', async () => {
  const response = await proxyApiRequest(
    new Request('http://0.0.0.0:3000/api/ask', {
      method: 'POST',
      headers: {
        host: 'localhost:3018',
        origin: 'http://localhost:3018',
        'sec-fetch-site': 'same-origin',
      },
      body: '{}',
    }),
    {
      apiOrigin: 'http://backend:8000',
      frontendOrigin: 'http://localhost:3018',
      developmentIdentity: true,
      upstreamFetch: async (_url, init) => {
        assert.equal(
          init.headers.get('oai-authenticated-user-id'),
          'local-development-user',
        );
        return Response.json({ status: 'ok' });
      },
    },
  );
  assert.equal(response.status, 200);
});

test('BFF rejects invalid public origin configuration', async () => {
  const response = await proxyApiRequest(
    new Request('http://localhost:3018/api/health'),
    {
      apiOrigin: 'http://backend:8000',
      frontendOrigin: 'http://localhost:3018/unexpected-path',
      upstreamFetch: () => {
        throw new Error('Should not fetch');
      },
    },
  );
  assert.equal(response.status, 503);
});

test('BFF preserves body, identity, status and query; replaces client secret', async () => {
  let called = false;
  const response = await proxyApiRequest(
    new Request('http://localhost:3000/api/ask?mode=deep', {
      method: 'POST',
      headers: {
        origin: 'http://localhost:3000',
        'content-type': 'application/json',
        'oai-authenticated-user-id': 'user-1',
        'x-luatrag-bff-secret': 'forged-secret',
      },
      body: '{"question":"test"}',
    }),
    {
      apiOrigin: 'http://127.0.0.1:8000',
      bffSecret: 'server-secret',
      upstreamFetch: async (url, init) => {
        called = true;
        assert.equal(String(url), 'http://127.0.0.1:8000/api/ask?mode=deep');
        assert.equal(init.headers.get('x-luatrag-bff-secret'), 'server-secret');
        assert.equal(init.headers.get('oai-authenticated-user-id'), 'user-1');
        assert.equal(
          await new Response(init.body).text(),
          '{"question":"test"}',
        );
        return Response.json({ answer: 'ok' }, { status: 201 });
      },
    },
  );
  assert.ok(called);
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), { answer: 'ok' });
});

test('BFF returns a useful API error if backend is unavailable', async () => {
  const response = await proxyApiRequest(
    new Request('http://localhost:3000/api/health'),
    {
      apiOrigin: 'http://127.0.0.1:8000',
      upstreamFetch: async () => {
        throw new Error('ECONNREFUSED');
      },
    },
  );
  assert.equal(response.status, 502);
  assert.equal((await response.json()).error.code, 'backend_unavailable');
});
