import type { RequestHandler } from '@sveltejs/kit';

// Readiness and liveness probe. The only dependency is RunPod, whose outages
// shouldn't take the UI out of rotation, so this just confirms we can serve.
export const GET: RequestHandler = () => new Response('ok');
