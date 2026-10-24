import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Provider } from '../src/client';
import { theme } from '../src/ui';
export default function Layout() {
  return (
    <Provider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: theme.bg },
          headerTintColor: theme.text,
          contentStyle: { backgroundColor: theme.bg },
          headerTitle: 'HAYTILE AI',
        }}
      />
    </Provider>
  );
}
