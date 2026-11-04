import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: 'HAYTILE AI',
    short_name: 'HAYTILE AI',
    description: 'Images, music, video, voice and conversations with HAYTILE AI.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: '#101019',
    theme_color: '#101019',
    icons: [
      { src: '/icons/haytile-192-v1.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/haytile-512-v1.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icons/haytile-maskable-512-v1.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  };
}
