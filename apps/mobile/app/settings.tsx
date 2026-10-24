import { useState } from 'react';
import { Text, Alert } from 'react-native';
import { router } from 'expo-router';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { api, useApp, languages } from '../src/client';
import { Screen, Heading, Copy, Card, Button, Input, Chips, s } from '../src/ui';
export default function Settings() {
  const { user, t, locale, setLocale, logout, refresh } = useApp();
  const [name, setName] = useState(user?.name || ''),
    [password, setPassword] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setMessage(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  }
  return (
    <Screen>
      <Heading>{t('settings')}</Heading>
      <Copy>{t('language')}</Copy>
      <Chips items={languages} value={locale} onChange={(l) => run(() => setLocale(l))} />
      {message && <Text style={s.copy}>{message}</Text>}
      {!user ? (
        <Button title={t('signin')} onPress={() => router.push('/auth')} />
      ) : (
        <>
          <Card>
            <Input label={t('name')} value={name} onChangeText={setName} />
            <Copy>{user.email}</Copy>
            <Button
              title={t('save')}
              disabled={busy || !name.trim()}
              onPress={() =>
                run(async () => {
                  await api('/me', { method: 'PATCH', body: JSON.stringify({ name, locale }) });
                  await refresh();
                  setMessage(t('saved'));
                })
              }
            />
            <Button
              title={t('export')}
              secondary
              disabled={busy}
              onPress={() =>
                run(async () => {
                  const data = await api('/me/export');
                  const f = new File(Paths.cache, 'haytile-data.json');
                  f.create({ overwrite: true });
                  f.write(JSON.stringify(data, null, 2));
                  await Sharing.shareAsync(f.uri, { mimeType: 'application/json' });
                })
              }
            />
            <Button
              title={t('signout')}
              secondary
              onPress={() =>
                run(async () => {
                  await logout();
                  router.replace('/');
                })
              }
            />
          </Card>
          <Card>
            <Text style={s.title}>{t('deleteAccount')}</Text>
            <Copy>{t('deleteWarning')}</Copy>
            <Input
              label={t('password')}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
            <Button
              title={t('deleteAccount')}
              disabled={busy || !password}
              secondary
              onPress={() =>
                Alert.alert(t('deleteAccount'), t('deleteWarning'), [
                  { text: t('cancel'), style: 'cancel' },
                  {
                    text: t('confirm'),
                    style: 'destructive',
                    onPress: () =>
                      run(async () => {
                        await api('/me', { method: 'DELETE', body: JSON.stringify({ password }) });
                        try {
                          await logout();
                        } catch {}
                        router.replace('/');
                      }),
                  },
                ])
              }
            />
          </Card>
        </>
      )}
    </Screen>
  );
}
