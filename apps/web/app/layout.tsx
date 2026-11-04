import type { Metadata } from 'next';
import './globals.css';
// Fetch the current app shell after deployments; hashed assets can still be cached.
export const dynamic = 'force-dynamic';
export const metadata: Metadata = {
  metadataBase: new URL(process.env.HAYTILE_PUBLIC_ORIGIN || 'https://ai.haytiles.com'),
  alternates: { canonical: '/' },
  icons: { icon: '/favicon.svg' },
  title: 'HAYTILE AI — Create beyond imagination',
  description: 'Your creative workspace. Images, music, video, voice and stories, together.',
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ht">
      <body>{children}</body>
    </html>
  );
}
