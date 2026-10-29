import React, { createContext, useContext, useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { getLocales } from 'expo-localization';
import en from '../../../packages/i18n/en.json';
import ht from '../../../packages/i18n/ht.json';
import fr from '../../../packages/i18n/fr.json';
import pt from '../../../packages/i18n/pt-BR.json';
import es from '../../../packages/i18n/es.json';
import ar from '../../../packages/i18n/ar.json';
import zh from '../../../packages/i18n/zh-Hans.json';
import id from '../../../packages/i18n/id.json';
import sw from '../../../packages/i18n/sw.json';
export const languages: Record<string, string> = {
  ht: 'Kreyòl ayisyen',
  en: 'English',
  fr: 'Français',
  'pt-BR': 'Português (Brasil)',
  es: 'Español',
  ar: 'العربية',
  'zh-Hans': '简体中文',
  id: 'Bahasa Indonesia',
  sw: 'Kiswahili',
};
const dictionaries: Record<string, Record<string, string>> = {
  en,
  ht,
  fr,
  'pt-BR': pt,
  es,
  ar,
  'zh-Hans': zh,
  id,
  sw,
};
export type User = {
  id: string;
  name: string;
  email: string;
  locale: string;
  balance: number;
  reserved: number;
  role: string;
};
export type Asset = {
  id: string;
  title: string;
  mime: string;
  text: string | null;
  created_at: string;
};
export type Job = {
  id: string;
  title: string;
  status: string;
  progress: number;
  error: string | null;
};
export type Model = {
  studio: string;
  available: boolean;
  credits: number;
  model_id: string | null;
  options?: { model_id: string; label: string; credits: number; available: boolean; pricing_url: string }[];
};
// Only the public backend address belongs in EXPO_PUBLIC; never put API keys here.
export const base = (process.env.EXPO_PUBLIC_API_URL || '').replace(/\/$/, '');
let token = '';
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (!base) throw new Error('BACKEND_URL_REQUIRED');
  const r = await fetch(base + '/v1' + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...options.headers,
    },
  });
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'REQUEST_FAILED');
  return data;
}
export function authHeader(): Record<string, string> {
  return token ? { Authorization: 'Bearer ' + token } : {};
}
const Context = createContext<{
  user: User | null;
  locale: string;
  t: (key: string) => string;
  login: (token: string, user: User) => Promise<void>;
  logout: () => Promise<void>;
  setLocale: (l: string) => Promise<void>;
  refresh: () => Promise<void>;
}>({} as never);
export const useApp = () => useContext(Context);
export function Provider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null),
    [locale, changeLocale] = useState('ht');
  useEffect(() => {
    (async () => {
      const l = await SecureStore.getItemAsync('locale');
      const device = getLocales()[0]?.languageTag || 'ht';
      changeLocale(
        l ||
          (languages[device]
            ? device
            : languages[device.split('-')[0]]
              ? device.split('-')[0]
              : 'ht'),
      );
      token = (await SecureStore.getItemAsync('session')) || '';
      if (token)
        try {
          setUser(await api<User>('/me'));
        } catch {
          token = '';
          await SecureStore.deleteItemAsync('session');
        }
    })();
  }, []);
  const login = async (raw: string, u: User) => {
    token = raw;
    await SecureStore.setItemAsync('session', raw);
    setUser(u);
    changeLocale(u.locale);
  };
  const logout = async () => {
    try {
      await api('/auth/logout', { method: 'POST' });
    } finally {
      token = '';
      await SecureStore.deleteItemAsync('session');
      setUser(null);
    }
  };
  const setLocale = async (l: string) => {
    changeLocale(l);
    await SecureStore.setItemAsync('locale', l);
    if (user)
      setUser(
        await api<User>('/me', {
          method: 'PATCH',
          body: JSON.stringify({ name: user.name, locale: l }),
        }),
      );
  };
  const refresh = async () => setUser(await api<User>('/me'));
  return (
    <Context.Provider
      value={{
        user,
        locale,
        t: (k) => dictionaries[locale]?.[k] || en[k as keyof typeof en] || k,
        login,
        logout,
        setLocale,
        refresh,
      }}
    >
      {children}
    </Context.Provider>
  );
}
