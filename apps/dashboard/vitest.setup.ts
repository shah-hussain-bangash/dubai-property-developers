
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Clean up rendered components after each test.
afterEach(() => {
  cleanup();
});
