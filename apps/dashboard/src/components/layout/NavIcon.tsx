import type { NavIconName } from '@/lib/navigation';

/** Minimal stroked icon set for navigation (24x24 grid). */
function IconPaths({ name }: { name: NavIconName }) {
  switch (name) {
    case 'overview':
      return (
        <>
          <rect x="3" y="3" width="7" height="9" rx="1.5" />
          <rect x="14" y="3" width="7" height="5" rx="1.5" />
          <rect x="14" y="12" width="7" height="9" rx="1.5" />
          <rect x="3" y="16" width="7" height="5" rx="1.5" />
        </>
      );
    case 'leads':
      return (
        <>
          <circle cx="9" cy="8" r="3.5" />
          <path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" />
          <path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.8.7 3 2.4 3.5 5.2" />
        </>
      );
    case 'agents':
      return (
        <>
          <rect x="4" y="7" width="16" height="12" rx="3" />
          <path d="M12 3v4M9 12h.01M15 12h.01M9 16h6" />
        </>
      );
    case 'conversations':
      return (
        <>
          <path d="M4 5h16v10H9l-5 4z" />
          <path d="M8 9h8M8 12h5" />
        </>
      );
    case 'properties':
      return (
        <>
          <path d="M3 21h18M5 21V8l7-5 7 5v13" />
          <path d="M9 21v-6h6v6M9 10h.01M15 10h.01" />
        </>
      );
    case 'workflows':
      return (
        <>
          <circle cx="5" cy="6" r="2.5" />
          <circle cx="19" cy="6" r="2.5" />
          <circle cx="12" cy="18" r="2.5" />
          <path d="M7.5 6h9M6.5 8.2l4.2 7.6M17.5 8.2l-4.2 7.6" />
        </>
      );
    case 'knowledge':
      return (
        <>
          <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z" />
          <path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5M8 7h8M8 11h6" />
        </>
      );
    case 'integrations':
      return (
        <>
          <path d="M9 3v4M15 3v4M7 7h10v4a5 5 0 0 1-10 0z" />
          <path d="M12 16v5" />
        </>
      );
    case 'analytics':
      return (
        <>
          <path d="M3 21h18" />
          <rect x="5" y="11" width="3" height="7" rx="1" />
          <rect x="10.5" y="6" width="3" height="12" rx="1" />
          <rect x="16" y="13" width="3" height="5" rx="1" />
        </>
      );
    case 'settings':
      return (
        <>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" />
        </>
      );
    default:
      return null;
  }
}

export function NavIcon({ name }: { name: NavIconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <IconPaths name={name} />
    </svg>
  );
}
