import { useState, useEffect } from 'react';
import { Text } from 'react-native';
import { api, useApp } from '../src/client';
import { Screen, Heading, Copy, Card, s } from '../src/ui';
export default function Pricing() {
  const { user, t } = useApp();
  const [wallet, setWallet] = useState<{
    balance: number;
    reserved: number;
    transactions: { id: string; kind: string; amount: number }[];
  } | null>(null);
  useEffect(() => {
    if (user)
      api<NonNullable<typeof wallet>>('/wallet')
        .then(setWallet)
        .catch(() => {});
  }, [user]);
  return (
    <Screen>
      <Heading>{t('pricing')}</Heading>
      <Card>
        <Copy>{t('balance')}</Copy>
        <Heading>{(wallet?.balance || 0) - (wallet?.reserved || 0)} ◈</Heading>
        <Copy>{t('reserved') + ': ' + (wallet?.reserved || 0)}</Copy>
      </Card>
      <Card>
        <Text style={s.title}>{t('freePlan')}</Text>
        <Copy>{t('freePlanDescription')}</Copy>
      </Card>
      <Copy>{t('plansNotice')}</Copy>
      <Heading>{t('transactions')}</Heading>
      {wallet?.transactions.map((x) => (
        <Card key={x.id}>
          <Copy>{x.kind + ' · ' + x.amount}</Copy>
        </Card>
      ))}
    </Screen>
  );
}
