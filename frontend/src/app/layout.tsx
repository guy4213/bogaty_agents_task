import type { Metadata } from 'next';
import './globals.css';
import { QueryProvider } from '@/providers/QueryProvider';
import { Header } from '@/components/Header';

export const metadata: Metadata = {
  title: 'Content Engine',
  description: 'Autonomous multi-modal content generation for social platforms',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-zinc-50 text-zinc-900 min-h-screen">
        <QueryProvider>
          <Header />
          <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">{children}</main>
        </QueryProvider>
      </body>
    </html>
  );
}
