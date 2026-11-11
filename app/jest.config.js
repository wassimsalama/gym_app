/**
 * Jest for the Expo app.
 *
 * The web preset, not jest-expo's default iOS one: the app ships only as a web
 * build, so tests must resolve `*.web.ts` over `*.ts` exactly as the production
 * bundle does (lib/cache.web.ts, lib/queueStore.web.ts).
 *
 * Tests live in __tests__/ at this level. Never put one under app/ — Expo
 * Router treats every file there as a route.
 */
module.exports = {
  preset: 'jest-expo/web',

  // tsconfig's `@/*` alias. Metro reads tsconfig paths; Jest does not.
  moduleNameMapper: { '^@/(.*)$': '<rootDir>/$1' },

  // e2e/ holds Playwright specs, which Jest would otherwise pick up by name.
  testPathIgnorePatterns: ['/node_modules/', '/e2e/', '/dist-e2e/'],

  // Count every source file, including ones no test has imported yet. Without
  // this Jest reports only the files a test happened to load, and the figure
  // starts out flattering instead of honest.
  collectCoverageFrom: [
    'lib/**/*.{ts,tsx}',
    'components/**/*.{ts,tsx}',
    'app/**/*.{ts,tsx}',
    '!**/*.d.ts',
  ],
  coverageReporters: ['text', 'text-summary', 'lcov', 'json-summary'],
};
