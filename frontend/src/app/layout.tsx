import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { QueryProvider } from '@/providers/QueryProvider';
import { SidebarProvider } from '@/providers/SidebarContext';
import { Sidebar } from '@/components/Sidebar';

const inter = Inter({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Content Engine',
  description: 'Autonomous multi-modal content generation for social platforms',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="flex h-screen overflow-hidden">
        <QueryProvider>
          <SidebarProvider>
            <Sidebar />
            <div className="flex-1 flex flex-col overflow-hidden min-w-0">
              {children}
            </div>
          </SidebarProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
