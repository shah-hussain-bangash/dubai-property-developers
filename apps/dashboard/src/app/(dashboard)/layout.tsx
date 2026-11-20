import type { ReactNode } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { ownerSession, SESSION_COOKIE } from '@/lib/portalAuth';
export const dynamic = 'force-dynamic';

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  if (!await ownerSession((await cookies()).get(SESSION_COOKIE)?.value).catch(()=>null)) redirect('/admin/login');
  return <AppShell>{children}</AppShell>;
}
