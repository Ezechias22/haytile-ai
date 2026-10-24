import type { ExpoConfig, ConfigContext } from 'expo/config';
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'HAYTILE AI',
  slug: 'haytile-ai',
  scheme: 'haytile',
  version: '0.1.0',
  icon: './assets/icon.png',
  orientation: 'portrait',
  userInterfaceStyle: 'dark',
  ios: {
    supportsTablet: true,
    bundleIdentifier: 'com.haytile.ai',
    infoPlist: { ITSAppUsesNonExemptEncryption: false },
  },
  android: { package: 'com.haytile.ai' },
  plugins: ['expo-router', 'expo-secure-store', 'expo-localization'],
  runtimeVersion: { policy: 'fingerprint' },
  ...(process.env.HAYTILE_EAS_PROJECT_ID
    ? {
        updates: { url: `https://u.expo.dev/${process.env.HAYTILE_EAS_PROJECT_ID}` },
        extra: { eas: { projectId: process.env.HAYTILE_EAS_PROJECT_ID } },
      }
    : {}),
});
