import { useState, useEffect } from 'react';
import { Text, Alert, Linking } from 'react-native';
import * as SecureStore from 'expo-secure-store';
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
  const [selectedModel, setSelectedModel] = useState('');
  useEffect(() => {
    SecureStore.getItemAsync('haytile-model-' + studio).then(value => setSelectedModel(value || '')).catch(() => {});
  }, [studio]);
  useEffect(() => {
    api<Model[]>('/models')
      .then(setModels)
      .catch(() => {});
  }, []);
  const studioModel = models.find((m) => m.studio === studio);
  const options = studioModel?.options || (studioModel?.model_id ? [{ ...studioModel, model_id: studioModel.model_id, label: studioModel.model_id, pricing_url: 'https://ai.google.dev/gemini-api/docs/pricing' }] : []);
  const choice = options.find(option => option.model_id === selectedModel) || options.find(option => option.model_id === studioModel?.model_id) || options[0];
  const model = studioModel ? { ...studioModel, ...choice } : undefined;
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
          model_id: choice?.model_id,
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
    Alert.alert(t('confirmCost'), (choice?.label || '') + '\n' + credits + ' ' + t('credits') + '\n' + t('modelPricingNotice'), [
      { text: t('cancel'), style: 'cancel' },
      { text: t('confirm'), onPress: submit },
    ]);
  }
  return (
    <Screen>
      <Heading>{t(studio)}</Heading>
      <Copy>{t(studio + 'Desc')}</Copy>
      <Card>
        <Copy>{t('aiModel')}</Copy>
        {options.length ? <Chips items={Object.fromEntries(options.map(option => [option.model_id, option.label]))} value={choice?.model_id || ''} onChange={value => {
          setSelectedModel(value);
          SecureStore.setItemAsync('haytile-model-' + studio, value).catch(() => {});
        }} /> : <Copy>{t('notConfigured')}</Copy>}
        <Copy>{t('modelPricingNotice')}</Copy>
        <Button title={t('providerPricing')} onPress={() => Linking.openURL(choice?.pricing_url || 'https://ai.google.dev/gemini-api/docs/pricing')} />
        {studio === 'minidrama' && <Copy>{t('miniModelChoiceNote')}</Copy>}
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
