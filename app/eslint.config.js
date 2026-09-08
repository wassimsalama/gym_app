const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');
const prettier = require('eslint-config-prettier/flat');

module.exports = defineConfig([
  expoConfig,
  prettier,
  { ignores: ['dist/*', '.expo/*', 'node_modules/*'] },
  {
    rules: {
      // react-native-web's Alert is `static alert() {}` — an empty function.
      // Calling it in a browser does nothing: no dialog, no callback, no error.
      // Deleting a photo, discarding a session and confirming account deletion
      // were all wired to it and all silently did nothing on the web while
      // looking correct in the source. Use components/ConfirmDialog instead,
      // which renders and therefore fails visibly if it is ever broken.
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'react-native',
              importNames: ['Alert'],
              message: 'Alert does nothing on web (react-native-web stubs it). Use ConfirmDialog.',
            },
          ],
        },
      ],
    },
  },
]);
