export type NavIconName =
  | 'overview'
  | 'leads'
  | 'agents'
  | 'conversations'
  | 'properties'
  | 'workflows'
  | 'knowledge'
  | 'integrations'
  | 'analytics'
  | 'settings';

export interface NavItem {
  href: string;
  label: string;
  icon: NavIconName;
  planned?: boolean;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Operations',
    items: [
      { href: '/overview', label: 'Overview', icon: 'overview' },
      { href: '/enquiries', label: 'Leads & enquiries', icon: 'leads' },
      { href: '/agent-properties', label: 'Properties', icon: 'properties' },
      { href: '/listing-review', label: 'Website listing review', icon: 'properties' },
      { href: '/agent-management', label: 'Agent management', icon: 'properties' },
      { href: '/prospect-research', label: 'Prospect Research', icon: 'leads' },
      { href: '/prospect-research/outreach', label: 'Social outreach', icon: 'conversations' },
    ],
  },
  {
    title: 'AI tools & demos',
    items: [
      { href: '/demo-lab', label: 'Demo Lab', icon: 'overview' },
      { href: '/leads', label: 'Lead qualification demo', icon: 'leads' },
      { href: '/conversations', label: 'Reply draft demo', icon: 'conversations' },
      { href: '/properties', label: 'Property AI demo', icon: 'properties' },
      { href: '/agents', label: 'Agents', icon: 'agents' },
      { href: '/workflows', label: 'Workflows', icon: 'workflows' },
      { href: '/knowledge', label: 'Knowledge', icon: 'knowledge' },
    ],
  },
  {
    title: 'Platform',
    items: [
      { href: '/integrations', label: 'Integrations', icon: 'integrations' },
      { href: '/analytics', label: 'Analytics demo', icon: 'analytics' },
      { href: '/security', label: 'Account security', icon: 'settings' },
      { href: '/recovery', label: 'Portal recovery', icon: 'settings' },
      { href: '/settings', label: 'Settings', icon: 'settings' },
    ],
  },
];

export function isNavItemActive(href: string, pathname: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}
