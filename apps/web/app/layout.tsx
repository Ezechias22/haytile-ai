import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
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
