'use client';

import { useEffect } from 'react';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageHeader } from '@/components/ui/PageHeader';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the error in the browser console for debugging; no remote logging yet.
    console.error(error);
  }, [error]);

  return (
    <>
      <PageHeader title="Something went wrong" description="This section failed to render." />
      <ErrorState
        title="Unexpected error"
        message={error.digest ? `Error reference: ${error.digest}` : 'An unexpected error occurred while rendering this page.'}
        onRetry={reset}
        retryLabel="Try again"
      />
    </>
  );
}
