import { useState, useEffect } from 'react';
import { Text, Alert, Linking } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { router, useLocalSearchParams } from 'expo-router';
import { api, useApp, languages, type Model } from '../../src/client';
import { suggestTitle } from '../../../../packages/creation-titles';
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
  const [voice, setVoice] = useState('Kore'), [voices, setVoices] = useState<string[]>([]), [voiceDetails, setVoiceDetails] = useState<{ name: string; gender: string }[]>([]), [voiceGender, setVoiceGender] = useState('all'), [vocal, setVocal] = useState('auto');
  const suggested = suggestTitle(prompt, t(studio));
  useEffect(() => {
    SecureStore.getItemAsync('haytile-model-' + studio).then(value => setSelectedModel(value || '')).catch(() => {});
  }, [studio]);
  useEffect(() => {
    api<{ voices: string[]; voice_options?: { name: string; gender: string }[] }>('/voices').then(data => { setVoices(data.voices); setVoiceDetails(data.voice_options || []); }).catch(() => {});
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
        body: JSON.stringify({ title: title.trim() || suggested, text: prompt }),
      });
      setMessage(t('saved'));
    } catch (e) {
      setMessage(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  }
  async function submit(approvedCredits: number) {
    setBusy(true);
    try {
      await api('/jobs', {
        method: 'POST',
        body: JSON.stringify({
          studio,
          model_id: choice?.model_id,
          title: title.trim() || suggested,
          prompt,
          idempotency_key: Math.random().toString(36).slice(2) + Date.now(),
          confirmed_credits: approvedCredits,
          params: {
            aspect,
            language,
            ...(studio === 'voice' ? { voice_name: voice } : {}),
            ...(studio === 'music' ? { vocal_style: vocal } : {}),
            ...(studio === 'video' ? { duration: Number(duration) } : {}),
          },
        }),
      });
      router.replace('/creations');
    } catch (e) {
      setMessage(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    if (!user) { router.push('/auth'); return; }
    setBusy(true);
    try {
      const result = await api<{ credits: number }>('/quotes', { method: 'POST', body: JSON.stringify({ studio, model_id: choice?.model_id, prompt, params: { language, aspect, ...(studio === 'voice' ? { voice_name: voice } : {}), ...(studio === 'music' ? { vocal_style: vocal } : {}), ...(studio === 'video' ? { duration: Number(duration) } : {}) } }) });
      Alert.alert(t('confirmCost'), (choice?.label || '') + '\n' + (result.credits ? result.credits + ' ' + t('credits') : t('freeGeneration')) + '\n' + t('reservationNotice'), [{ text: t('cancel'), style: 'cancel' }, { text: t('confirm'), onPress: () => submit(result.credits) }]);
    } catch (error) { setMessage(t('quoteUnavailable')); }
    finally { setBusy(false); }
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
        <Input label={t('title')} value={title || suggested} onChangeText={setTitle} maxLength={120} />
        <Input
          label={t('prompt')}
          value={prompt}
          onChangeText={setPrompt}
          multiline
          maxLength={12000}
          placeholder={t('promptHint')}
        />
        {studio === 'voice' && <><Copy>{t('voiceType')}</Copy><Chips items={{all:t('allVoices'),male:t('maleVoices'),female:t('femaleVoices')}} value={voiceGender} onChange={gender => { setVoiceGender(gender); const first = voiceDetails.find(v => gender === 'all' || v.gender === gender); if (first) setVoice(first.name); }}/><Copy>{t('chooseVoice')}</Copy><Chips items={Object.fromEntries((voices.length ? voices : ['Kore']).filter(name => voiceGender === 'all' || voiceDetails.some(v => v.name === name && v.gender === voiceGender)).map(name => { const gender = voiceDetails.find(v => v.name === name)?.gender; return [name, name + (gender ? ' · ' + t(gender === 'male' ? 'maleVoiceLabel' : gender === 'female' ? 'femaleVoiceLabel' : 'otherVoices') : '')]; }))} value={voice} onChange={setVoice}/></>}
        {studio === 'music' && <><Copy>{t('vocalStyle')}</Copy><Chips items={{auto:t('autoVocal'),male:t('maleVocal'),female:t('femaleVocal'),duet:t('duetVocal'),instrumental:t('instrumentalVocal')}} value={vocal} onChange={setVocal}/></>}
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
          title={t('generate') + ' · ' + (['image','text'].includes(studio) ? t('freeGeneration') : t('quoteRequired'))}
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
