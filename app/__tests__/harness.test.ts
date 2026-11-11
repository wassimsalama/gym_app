/**
 * Harness check, not a test of app behaviour. It proves the pieces every real
 * test depends on: TypeScript compiles, the `@/` alias resolves, and modules
 * load as they do in the web bundle. Real tests are designed from the coverage
 * criteria and go alongside this file.
 */
import { Platform } from 'react-native';

import * as units from '@/lib/units';

test('runs on the web platform, like the production bundle', () => {
  expect(Platform.OS).toBe('web');
});

test('resolves the @/ alias and compiles TypeScript', () => {
  expect(typeof units.kgToLb).toBe('function');
});
