import { useState, useEffect } from 'react';
import { Text, Alert, View } from 'react-native';
import { router } from 'expo-router';
import { api, useApp, type Asset, type Model } from '../src/client';
import { Screen, Heading, Copy, Card, Button, Input, Chips, s } from '../src/ui';
type Character = {
  id: string;
  name: string;
  appearance: string;
  wardrobe: string;
  voice: string;
  language: string;
  reference_asset_id: string | null;
};
type Scene = {
  id: string;
  title: string;
  description: string;
  dialogue: string;
  duration: number;
  character_ids: string[];
  asset_id: string | null;
};
type Project = {
  id: string;
  title: string;
  version: number;
  document: {
    premise: string;
    continuity: string;
    aspect: '16:9' | '9:16';
    characters: Character[];
    scenes: Scene[];
  };
};
const uid = () => Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
export default function Projects() {
  const { user, t } = useApp();
  const [projects, setProjects] = useState<Project[]>([]),
    [current, setCurrent] = useState<Project | null>(null),
    [assets, setAssets] = useState<Asset[]>([]),
    [model, setModel] = useState<Model | null>(null),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState('');
  async function refresh() {
    setProjects(await api<Project[]>('/projects'));
    setAssets(await api<Asset[]>('/assets'));
    setModel((await api<Model[]>('/models')).find((m) => m.studio === 'video') || null);
  }
  useEffect(() => {
    if (user) refresh().catch(() => {});
  }, [user]);
  async function act(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setMessage(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  }
  function doc(patch: Partial<Project['document']>) {
    if (!current) return;
    setCurrent({ ...current, document: { ...current.document, ...patch } });
    setDirty(true);
  }
  function scene(id: string, patch: Partial<Scene>) {
    if (current)
      doc({ scenes: current.document.scenes.map((s) => (s.id === id ? { ...s, ...patch } : s)) });
  }
  function char(id: string, patch: Partial<Character>) {
    if (current)
      doc({
        characters: current.document.characters.map((c) => (c.id === id ? { ...c, ...patch } : c)),
      });
  }
  async function reload() {
    const all = await api<Project[]>('/projects');
    setProjects(all);
    if (current) setCurrent(all.find((p) => p.id === current.id) || null);
    setDirty(false);
  }
  return (
    <Screen>
      <Heading>{t('storyboard')}</Heading>
      <Copy>{t('storyboardNote')}</Copy>
      {!user ? (
        <Button title={t('signin')} onPress={() => router.push('/auth')} />
      ) : (
        <>
          <Button
            title={t('newProject')}
            disabled={busy || dirty}
            onPress={() =>
              act(async () => {
                const p = await api<Project>('/projects', {
                  method: 'POST',
                  body: JSON.stringify({
                    title: t('newProject'),
                    document: {
                      premise: '',
                      continuity: '',
                      aspect: '16:9',
                      characters: [],
                      scenes: [],
                    },
                  }),
                });
                setCurrent(p);
                await refresh();
              })
            }
          />
          <Chips
            items={Object.fromEntries(projects.map((p) => [p.id, p.title]))}
            value={current?.id || ''}
            onChange={(id) => {
              if (dirty) {
                setMessage(t('saveBeforeRender'));
                return;
              }
              setCurrent(projects.find((p) => p.id === id) || null);
            }}
          />
          {message && <Text style={s.copy}>{message}</Text>}
          {current && (
            <>
              <Card>
                <Input
                  label={t('title')}
                  value={current.title}
                  onChangeText={(title) => {
                    setCurrent({ ...current, title });
                    setDirty(true);
                  }}
                />
                <Input
                  label={t('premise')}
                  value={current.document.premise}
                  onChangeText={(premise) => doc({ premise })}
                  multiline
                  maxLength={4000}
                />
                <Input
                  label={t('continuity')}
                  value={current.document.continuity}
                  onChangeText={(continuity) => doc({ continuity })}
                  multiline
                  maxLength={4000}
                />
                <Chips
                  items={{ '16:9': '16:9', '9:16': '9:16' }}
                  value={current.document.aspect}
                  onChange={(aspect) => doc({ aspect: aspect as '16:9' | '9:16' })}
                />
              </Card>
              <Heading>{t('characters')}</Heading>
              {current.document.characters.map((c) => (
                <Card key={c.id}>
                  <Input
                    label={t('name')}
                    value={c.name}
                    onChangeText={(name) => char(c.id, { name })}
                  />
                  <Input
                    label={t('appearance')}
                    value={c.appearance}
                    onChangeText={(appearance) => char(c.id, { appearance })}
                    multiline
                  />
                  <Input
                    label={t('wardrobe')}
                    value={c.wardrobe}
                    onChangeText={(wardrobe) => char(c.id, { wardrobe })}
                  />
                  <Input
                    label={t('voiceProfile')}
                    value={c.voice}
                    onChangeText={(voice) => char(c.id, { voice })}
                  />
                  <Copy>{t('reference')}</Copy>
                  <Chips
                    items={{
                      '': t('none'),
                      ...Object.fromEntries(
                        assets
                          .filter((a) => a.mime.startsWith('image/'))
                          .map((a) => [a.id, a.title]),
                      ),
                    }}
                    value={c.reference_asset_id || ''}
                    onChange={(id) => char(c.id, { reference_asset_id: id || null })}
                  />
                  <Button
                    title={t('delete')}
                    secondary
                    onPress={() =>
                      doc({
                        characters: current.document.characters.filter((x) => x.id !== c.id),
                        scenes: current.document.scenes.map((s) => ({
                          ...s,
                          character_ids: s.character_ids.filter((id) => id !== c.id),
                        })),
                      })
                    }
                  />
                </Card>
              ))}
              <Button
                title={t('addCharacter')}
                secondary
                disabled={current.document.characters.length >= 20}
                onPress={() =>
                  doc({
                    characters: [
                      ...current.document.characters,
                      {
                        id: uid(),
                        name: t('character'),
                        appearance: '',
                        wardrobe: '',
                        voice: '',
                        language: 'ht',
                        reference_asset_id: null,
                      },
                    ],
                  })
                }
              />
              <Heading>{t('scenes')}</Heading>
              {current.document.scenes.map((sc, index) => (
                <Card key={sc.id}>
                  <Text style={s.title}>
                    {index + 1}. {sc.title}
                  </Text>
                  <Input
                    label={t('title')}
                    value={sc.title}
                    onChangeText={(title) => scene(sc.id, { title })}
                  />
                  <Input
                    label={t('sceneDescription')}
                    value={sc.description}
                    onChangeText={(description) => scene(sc.id, { description })}
                    multiline
                    maxLength={2000}
                  />
                  <Input
                    label={t('dialogue')}
                    value={sc.dialogue}
                    onChangeText={(dialogue) => scene(sc.id, { dialogue })}
                    multiline
                    maxLength={4000}
                  />
                  <Input
                    label={t('duration')}
                    value={String(sc.duration)}
                    onChangeText={(duration) => scene(sc.id, { duration: Number(duration) })}
                    keyboardType="number-pad"
                  />
                  <Copy>{t('characters')}</Copy>
                  {current.document.characters.map((c) => (
                    <Button
                      key={c.id}
                      title={(sc.character_ids.includes(c.id) ? '✓ ' : '+ ') + c.name}
                      secondary
                      onPress={() =>
                        scene(sc.id, {
                          character_ids: sc.character_ids.includes(c.id)
                            ? sc.character_ids.filter((id) => id !== c.id)
                            : [...sc.character_ids, c.id],
                        })
                      }
                    />
                  ))}
                  <Copy>{t('sceneMedia')}</Copy>
                  <Chips
                    items={{
                      '': t('none'),
                      ...Object.fromEntries(
                        assets
                          .filter((a) => a.mime.startsWith('video/'))
                          .map((a) => [a.id, a.title]),
                      ),
                    }}
                    value={sc.asset_id || ''}
                    onChange={(id) => scene(sc.id, { asset_id: id || null })}
                  />
                  <Button
                    title={t('moveUp')}
                    secondary
                    disabled={index === 0}
                    onPress={() => {
                      const scenes = [...current.document.scenes];
                      [scenes[index - 1], scenes[index]] = [scenes[index], scenes[index - 1]];
                      doc({ scenes });
                    }}
                  />
                  <Button
                    title={t('delete')}
                    secondary
                    onPress={() =>
                      doc({ scenes: current.document.scenes.filter((s) => s.id !== sc.id) })
                    }
                  />
                  <Button
                    title={t('generateScene') + ' · ' + (model?.credits || 0) + ' ◈'}
                    disabled={busy || dirty || !model?.available}
                    onPress={() =>
                      Alert.alert(
                        t('confirmCost'),
                        String(model?.credits || 0) + ' ' + t('credits'),
                        [
                          { text: t('cancel'), style: 'cancel' },
                          {
                            text: t('confirm'),
                            onPress: () =>
                              act(async () => {
                                await api(
                                  '/projects/' + current.id + '/scenes/' + sc.id + '/generate',
                                  {
                                    method: 'POST',
                                    body: JSON.stringify({
                                      idempotency_key: uid(),
                                      confirmed_credits: model?.credits || 0,
                                    }),
                                  },
                                );
                                setMessage(t('queued'));
                              }),
                          },
                        ],
                      )
                    }
                  />
                </Card>
              ))}
              <Button
                title={t('addScene')}
                secondary
                disabled={current.document.scenes.length >= 22}
                onPress={() =>
                  doc({
                    scenes: [
                      ...current.document.scenes,
                      {
                        id: uid(),
                        title: t('scene') + ' ' + (current.document.scenes.length + 1),
                        description: '',
                        dialogue: '',
                        duration: 8,
                        character_ids: [],
                        asset_id: null,
                      },
                    ],
                  })
                }
              />
              <Copy>{t('saveBeforeRender')}</Copy>
              <Button
                title={t('save')}
                disabled={busy || !dirty}
                onPress={() =>
                  act(async () => {
                    const p = await api<Project>('/projects/' + current.id, {
                      method: 'PUT',
                      body: JSON.stringify(current),
                    });
                    setCurrent(p);
                    setDirty(false);
                    setMessage(t('saved'));
                    await refresh();
                  })
                }
              />
              <Button
                title={t('refresh')}
                secondary
                disabled={busy || dirty}
                onPress={() => act(reload)}
              />
              <Button
                title={t('assemble')}
                disabled={
                  busy ||
                  dirty ||
                  !current.document.scenes.length ||
                  current.document.scenes.some((s) => !s.asset_id)
                }
                onPress={() =>
                  act(async () => {
                    await api('/projects/' + current.id + '/assemble', {
                      method: 'POST',
                      body: JSON.stringify({ idempotency_key: uid() }),
                    });
                    router.push('/creations');
                  })
                }
              />
            </>
          )}
        </>
      )}
    </Screen>
  );
}
