// Local demo is the default. Set VITE_AUTH_MODE=supabase to restore real Auth.
export const isLocalAuth = (import.meta.env.VITE_AUTH_MODE || 'local') === 'local'
