import { proxyApiRequest } from '@/lib/api-proxy';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function forward(request: Request) {
  return proxyApiRequest(request, {
    apiOrigin: process.env.API_ORIGIN || 'http://127.0.0.1:8000',
    frontendOrigin: process.env.FRONTEND_ORIGIN,
    bffSecret: process.env.LUATRAG_BFF_SECRET,
    developmentIdentity: process.env.APP_ENV === 'development',
  });
}

export {
  forward as GET,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
  forward as HEAD,
  forward as OPTIONS,
};
