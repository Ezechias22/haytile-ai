import { useState, useEffect } from 'react';
import { Text, Alert } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { api, useApp, languages, type Model } from '../../src/client';
import { Screen, Heading, Copy, Card, Input, Button, Chips, s } from '../../src/ui';
export default function Studio() {
  const params = useLocalSearchParams<{ studio: string; prompt?: string; title?: string }>();
  const studio = params.studio;
  const { t, user, locale } = useApp();
  const [title, setTitle] = useState(params.title || ''),
    [prompt, setPrompt] = useState(params.prompt || ''),
    [aspect, setAspect] = useState('16:9'),
    [language, setLanguage] = useState(locale),
    [duration, setDuration] = useState('8'),
    [models, setModels] = useState<Model[]>([]),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState('');
  useEffect(() => {
    api<Model[]>('/models')
      .then(setModels)
      .catch(() => {});
  }, []);
  const model = models.find((m) => m.studio === studio);
  const credits =
    (model?.credits || 0) * (studio === 'video' ? Math.ceil(Number(duration) / 10) : 1);
  async function save() {
    if (!user) {
      router.push('/auth');
      return;
    }
    setBusy(true);
    try {
      await api('/assets/text', {
        method: 'POST',
        body: JSON.stringify({ title: title || t(studio), text: prompt }),
      });
      setMessage(t('saved'));
    } catch (e) {
      setMessage(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    setBusy(true);
    try {
      await api('/jobs', {
        method: 'POST',
        body: JSON.stringify({
          studio,
          title: title || t(studio),
          prompt,
          idempotency_key: Math.random().toString(36).slice(2) + Date.now(),
          confirmed_credits: credits,
          params: {
            aspect,
            language,
            ...(studio === 'video' ? { duration: Number(duration) } : {}),
          },
        }),
      });
      setMessage(t('queued'));
    } catch (e) {
      setMessage(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  }
  function generate() {
    if (!user) {
      router.push('/auth');
      return;
    }
    Alert.alert(t('confirmCost'), credits + ' ' + t('credits'), [
      { text: t('cancel'), style: 'cancel' },
      { text: t('confirm'), onPress: submit },
    ]);
  }
  return (
    <Screen>
      <Heading>{t(studio)}</Heading>
      <Copy>{t(studio + 'Desc')}</Copy>
      <Card>
        <Input label={t('title')} value={title} onChangeText={setTitle} maxLength={120} />
        <Input
          label={t('prompt')}
          value={prompt}
          onChangeText={setPrompt}
          multiline
          maxLength={12000}
          placeholder={t('promptHint')}
        />
        <Copy>{t('language')}</Copy>
        <Chips items={languages} value={language} onChange={setLanguage} />
        {['image', 'video'].includes(studio) && (
          <Chips
            items={
              studio === 'video'
                ? { '16:9': '16:9', '9:16': '9:16' }
                : { '1:1': '1:1', '16:9': '16:9', '9:16': '9:16' }
            }
            value={aspect}
            onChange={setAspect}
          />
        )}
        {studio === 'video' && (
          <Input
            label={t('duration')}
            value={duration}
            onChangeText={setDuration}
            keyboardType="number-pad"
          />
        )}
        {!model?.available && <Copy>{t('unavailable')}</Copy>}
        {studio === 'minidrama' && <Copy>{t('scriptOnly')}</Copy>}
        {studio === 'music' && <Copy>{t('musicNote')}</Copy>}
        {message && <Text style={s.copy}>{message}</Text>}
        <Button title={t('saveDraft')} onPress={save} disabled={busy || !prompt.trim()} />
        <Button
          title={t('generate') + ' · ' + credits + ' ' + t('credits')}
          onPress={generate}
          disabled={
            busy ||
            !prompt.trim() ||
            !model?.available ||
            (studio === 'video' &&
              (!Number.isInteger(Number(duration)) ||
                Number(duration) < 8 ||
                Number(duration) > 180))
          }
        />
      </Card>
      {studio === 'minidrama' && (
        <Button title={t('storyboard')} secondary onPress={() => router.push('/projects')} />
      )}
      <Button title={t('library')} secondary onPress={() => router.push('/creations')} />
    </Screen>
  );
}
