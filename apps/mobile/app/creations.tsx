import { useState, useEffect, useCallback } from 'react';
import { Text, Image, Modal, View, Alert, ActivityIndicator } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { fetch as expoFetch } from 'expo/fetch';
import { useAudioPlayer } from 'expo-audio';
import { useVideoPlayer, VideoView } from 'expo-video';
import { api, base, authHeader, useApp, type Asset, type Job } from '../src/client';
import { Screen, Heading, Copy, Card, Button, Input, s, theme } from '../src/ui';
function AudioPreview({ url }: { url: string }) {
  const player = useAudioPlayer(url);
  const { t } = useApp();
  return (
    <Button
      title={t('preview') + ' / ⏸'}
      onPress={() => (player.playing ? player.pause() : player.play())}
    />
  );
}
function VideoPreview({ url }: { url: string }) {
  const player = useVideoPlayer(url);
  return <VideoView player={player} style={{ width: '100%', height: 250 }} nativeControls />;
}
export default function Creations() {
  const { user, t } = useApp();
  const [assets, setAssets] = useState<Asset[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [preview, setPreview] = useState<Asset | null>(null),
    [url, setUrl] = useState(''),
    [rename, setRename] = useState<Asset | null>(null),
    [newTitle, setNewTitle] = useState('');
  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      setAssets(await api('/assets'));
      setJobs(await api('/jobs'));
    } catch (e) {
      setError(t('error') + ' (' + (e as Error).message + ')');
    }
  }, [user, t]);
  useFocusEffect(
    useCallback(() => {
      refresh();
      const id = setInterval(refresh, 5000);
      return () => clearInterval(id);
    }, [refresh]),
  );
  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  }
  async function link(a: Asset) {
    const result = await api<{ path: string }>('/assets/' + a.id + '/link');
    return base + result.path;
  }
  async function open(a: Asset) {
    setPreview(a);
    setUrl('');
    await act(async () => setUrl(await link(a)));
  }
  async function upload() {
    if (!user) {
      router.push('/auth');
      return;
    }
    const result = await DocumentPicker.getDocumentAsync({
      type: [
        'image/png',
        'image/jpeg',
        'image/webp',
        'audio/mpeg',
        'audio/wav',
        'audio/ogg',
        'video/mp4',
        'text/plain',
      ],
      copyToCacheDirectory: true,
    });
    if (result.canceled) return;
    await act(async () => {
      const data = new FormData();
      data.append('file', new File(result.assets[0].uri));
      const r = await expoFetch(base + '/v1/assets/upload', {
        method: 'POST',
        headers: authHeader(),
        body: data,
      });
      if (!r.ok) throw new Error('UPLOAD_FAILED');
      await refresh();
    });
  }
  async function share(a: Asset) {
    await act(async () => {
      const signed = await link(a),
        file = await File.downloadFileAsync(
          signed,
          new File(
            Paths.cache,
            'haytile-' +
              a.id +
              '.' +
              (a.mime === 'text/plain'
                ? 'txt'
                : a.mime === 'audio/mpeg'
                  ? 'mp3'
                  : a.mime.split('/')[1]),
          ),
          { idempotent: true },
        );
      if (await Sharing.isAvailableAsync())
        await Sharing.shareAsync(file.uri, { mimeType: a.mime });
      else throw new Error('SHARING_UNAVAILABLE');
    });
  }
  function remove(a: Asset) {
    Alert.alert(t('delete'), t('deleteConfirm'), [
      { text: t('cancel'), style: 'cancel' },
      {
        text: t('delete'),
        style: 'destructive',
        onPress: () =>
          act(async () => {
            await api('/assets/' + a.id, { method: 'DELETE' });
            await refresh();
          }),
      },
    ]);
  }
  return (
    <Screen>
      <Heading>{t('library')}</Heading>
      <Copy>{t('privacy')}</Copy>
      {!user ? (
        <Button title={t('signin')} onPress={() => router.push('/auth')} />
      ) : (
        <>
          <Button title={t('upload')} onPress={upload} disabled={busy} />
          <Copy>{t('uploadHint')}</Copy>
          {error && <Text style={s.error}>{error}</Text>}
          {!assets.length && (
            <Card>
              <Copy>{t('emptyDescription')}</Copy>
            </Card>
          )}
          {assets.map((a) => (
            <Card key={a.id}>
              <Text style={s.title}>{a.title}</Text>
              <Copy>{a.mime + ' · ' + new Date(a.created_at).toLocaleDateString()}</Copy>
              {a.text && (
                <Text numberOfLines={3} style={s.copy}>
                  {a.text}
                </Text>
              )}
              <Button title={t('preview')} secondary onPress={() => open(a)} />
              <Button title={t('download')} secondary onPress={() => share(a)} />
              <View style={{ flexDirection: 'row', gap: 12 }}>
                <Button
                  title={t('rename')}
                  secondary
                  onPress={() => {
                    setRename(a);
                    setNewTitle(a.title);
                  }}
                />
                <Button title={t('delete')} secondary onPress={() => remove(a)} />
              </View>
            </Card>
          ))}
          <Heading>{t('jobs')}</Heading>
          {jobs.map((j) => (
            <Card key={j.id}>
              <Text style={s.title}>{j.title}</Text>
              <Copy>{t(j.status) + ' · ' + j.progress + '%'}</Copy>
              {j.error && <Text style={s.error}>{j.error}</Text>}
              {j.status === 'failed' && (
                <Button
                  title={t('retry')}
                  disabled={busy}
                  secondary
                  onPress={() =>
                    act(async () => {
                      await api('/jobs/' + j.id + '/retry', { method: 'POST' });
                      await refresh();
                    })
                  }
                />
              )}
            </Card>
          ))}
        </>
      )}
      <Modal visible={!!preview} animationType="slide" onRequestClose={() => setPreview(null)}>
        <Screen>
          <Heading>{preview?.title}</Heading>
          {preview?.text ? (
            <Text selectable style={s.copy}>
              {preview.text}
            </Text>
          ) : !url ? (
            <ActivityIndicator color={theme.accent} />
          ) : preview?.mime.startsWith('image/') ? (
            <Image
              source={{ uri: url }}
              resizeMode="contain"
              style={{ width: '100%', height: 350 }}
            />
          ) : preview?.mime.startsWith('audio/') ? (
            <AudioPreview url={url} />
          ) : (
            <VideoPreview url={url} />
          )}{' '}
          {preview?.text &&
            ['image', 'music', 'video', 'minidrama', 'voice', 'text'].map((studio) => (
              <Button
                key={studio}
                title={t('sendTo') + ' ' + t(studio)}
                secondary
                onPress={() => {
                  setPreview(null);
                  router.push({
                    pathname: '/studio/[studio]',
                    params: { studio, prompt: preview.text!, title: preview.title },
                  });
                }}
              />
            ))}
          <Button title={t('close')} onPress={() => setPreview(null)} />
        </Screen>
      </Modal>
      <Modal visible={!!rename} animationType="slide" onRequestClose={() => setRename(null)}>
        <Screen>
          <Heading>{t('rename')}</Heading>
          <Input label={t('title')} value={newTitle} onChangeText={setNewTitle} />
          <Button
            title={t('save')}
            disabled={busy || !newTitle.trim()}
            onPress={() =>
              act(async () => {
                await api('/assets/' + rename!.id, {
                  method: 'PATCH',
                  body: JSON.stringify({ title: newTitle }),
                });
                setRename(null);
                await refresh();
              })
            }
          />
          <Button title={t('cancel')} secondary onPress={() => setRename(null)} />
        </Screen>
      </Modal>
    </Screen>
  );
}
