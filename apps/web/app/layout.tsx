import type { Metadata, Viewport } from 'next';
import './globals.css';
// Fetch the current app shell after deployments; hashed assets can still be cached.
export const dynamic = 'force-dynamic';
export const metadata: Metadata = {
  metadataBase: new URL(process.env.HAYTILE_PUBLIC_ORIGIN || 'https://ai.haytiles.com'),
  alternates: { canonical: '/' },
  applicationName: 'HAYTILE AI',
  appleWebApp: { capable: true, title: 'HAYTILE AI', statusBarStyle: 'black-translucent' },
  icons: {
    icon: [{ url: '/icons/haytile-32-v1.png', sizes: '32x32', type: 'image/png' }],
    apple: [{ url: '/icons/apple-touch-icon-v1.png', sizes: '180x180', type: 'image/png' }],
  },
  title: 'HAYTILE AI — Create beyond imagination',
  description: 'Your creative workspace. Images, music, video, voice and stories, together.',
};
export const viewport: Viewport = { themeColor: '#101019' };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ht">
      <body>{children}</body>
    </html>
  );
}
