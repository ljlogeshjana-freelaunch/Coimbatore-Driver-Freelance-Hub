import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
export const supabase = url && key && !url.includes('your-project')
  ? createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })
  : null;
export const apiBase = (import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '')).replace(/\/$/, '');

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!apiBase) throw new Error('Backend API is not configured. Set VITE_API_URL and rebuild the frontend.');
  const { data } = supabase ? await supabase.auth.getSession() : { data: { session: null } };
  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');
  if (data.session?.access_token) headers.set('Authorization', `Bearer ${data.session.access_token}`);
  const response = await fetch(`${apiBase}${path}`, { ...init, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || `Request failed (${response.status})`);
  return body as T;
}

export function whatsappHref(phone: string, text: string) {
  return `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
}
