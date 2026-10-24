import { useState } from 'react';
import { Text } from 'react-native';
import { router } from 'expo-router';
import { api, useApp, type User } from '../src/client';
import { Screen, Heading, Copy, Input, Button, s } from '../src/ui';
export default function Auth() {
  const { t, login, locale } = useApp();
  const [mode, setMode] = useState('login'),
    [name, setName] = useState(''),
    [email, setEmail] = useState(''),
    [password, setPassword] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    setError('');
    try {
      const result = await api<{ user: User; token: string }>('/auth/' + mode, {
        method: 'POST',
        body: JSON.stringify({ name, email, password, locale }),
      });
      await login(result.token, result.user);
      router.back();
    } catch (e) {
      setError(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  }
  return (
    <Screen>
      <Heading>{t(mode === 'login' ? 'signin' : 'signup')}</Heading>
      <Copy>{t('loginDescription')}</Copy>
      {mode === 'register' && (
        <Input label={t('name')} value={name} onChangeText={setName} autoComplete="name" />
      )}
      <Input
        label={t('email')}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        keyboardType="email-address"
        autoComplete="email"
      />
      <Input
        label={t('password')}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
        placeholder={t('passwordHint')}
      />
      {error && <Text style={s.error}>{error}</Text>}
      <Button
        title={t(mode === 'login' ? 'signin' : 'signup')}
        onPress={submit}
        disabled={
          busy || !email || !password || (mode === 'register' && (!name || password.length < 12))
        }
      />
      <Button
        title={t(mode === 'login' ? 'signup' : 'signin')}
        secondary
        onPress={() => setMode(mode === 'login' ? 'register' : 'login')}
      />
    </Screen>
  );
}
