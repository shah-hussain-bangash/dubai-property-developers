import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Dubai Property Developers',
    template: '%s · Dubai Property Developers',
  },
  description: 'Dubai Property Developers — explore property communities, developer collaboration and your next Dubai property move.',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: '#060f1d',
  colorScheme: 'dark',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
