import axios from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      const refresh = localStorage.getItem('refresh_token');
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/auth/refresh`, null, {
            headers: { Authorization: `Bearer ${refresh}` },
          });
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);
          err.config.headers.Authorization = `Bearer ${data.access_token}`;
          return api(err.config);
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      } else {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  register: (data: { email: string; password: string; full_name: string }) =>
    api.post('/auth/register', data),
  login: (data: { email: string; password: string }) =>
    api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
  addKey: (data: { api_key: string; api_secret: string; is_testnet: boolean; label?: string }) =>
    api.post('/auth/keys', data),
  listKeys: () => api.get('/auth/keys'),
  deleteKey: (id: string) => api.delete(`/auth/keys/${id}`),
  updateSettings: (data: object) => api.put('/auth/settings', data),
};

// ── Trading ───────────────────────────────────────────────────────────────────
export const tradingApi = {
  trades:      (params?: object) => api.get('/trading/trades', { params }),
  openTrades:  () => api.get('/trading/positions'),
  closeTrade:  (id: string) => api.post(`/trading/trades/${id}/close`),
  performance: () => api.get('/performance/summary'),
};

// ── Health ────────────────────────────────────────────────────────────────────
export const healthApi = {
  check: () => api.get('/health', { baseURL: 'http://localhost:8000' }),
};
