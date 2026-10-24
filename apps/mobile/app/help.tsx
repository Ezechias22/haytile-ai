import { Text } from 'react-native';
import { useApp } from '../src/client';
import { Screen, Heading, Copy, Card, s } from '../src/ui';
export default function Help() {
  const { t } = useApp();
  return (
    <Screen>
      <Heading>{t('helpTitle')}</Heading>
      {[1, 2, 3, 4, 5].map((i) => (
        <Card key={i}>
          <Text style={s.title}>{t('faq' + i)}</Text>
          <Copy>{t('answer' + i)}</Copy>
        </Card>
      ))}
    </Screen>
  );
}
