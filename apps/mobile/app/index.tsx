import { Text, View } from 'react-native';
import { router } from 'expo-router';
import { useApp } from '../src/client';
import { Screen, Heading, Copy, Card, Button, s } from '../src/ui';
export default function Home() {
  const { user, t } = useApp();
  return (
    <Screen>
      <Text style={{ color: '#b491f7', fontSize: 10, letterSpacing: 2, marginBottom: 18 }}>
        HAYTILE AI · CREATIVE WORKSPACE
      </Text>
      <Heading>{t('heroTitle') + '\n' + t('heroAccent')}</Heading>
      <Copy>{t('heroDescription')}</Copy>
      {!user && <Button title={t('signin')} onPress={() => router.push('/auth')} />}
      <View style={{ marginTop: 20 }}>
        {['image', 'music', 'video', 'minidrama', 'voice', 'text'].map((studio, i) => (
          <Card key={studio}>
            <Text style={s.title}>
              {['✦', '♫', '▶', '▤', '◉', 'Aa'][i]} {t(studio)}
            </Text>
            <Copy>{t(studio + 'Desc')}</Copy>
            <Button
              title={t('open')}
              secondary
              onPress={() => router.push({ pathname: '/studio/[studio]', params: { studio } })}
            />
          </Card>
        ))}
      </View>
      <Button title={t('library')} onPress={() => router.push('/creations')} />
      <Button title={t('pricing')} secondary onPress={() => router.push('/pricing')} />
      <Button title={t('settings')} secondary onPress={() => router.push('/settings')} />
      <Button title={t('help')} secondary onPress={() => router.push('/help')} />
    </Screen>
  );
}
