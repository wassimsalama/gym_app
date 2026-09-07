import type { ReactNode } from 'react';
import { Platform, View } from 'react-native';

/**
 * Holds the app to a readable column on wide screens.
 *
 * Every screen here was laid out at phone width — single-column cards, full
 * width inputs, a bottom tab bar. Stretched across a desktop monitor those
 * become metre-wide text fields. Rather than redesign each screen for two
 * shapes, the whole app sits in a phone-width column, centred, which is also
 * how most fitness apps present on the web.
 *
 * A no-op on native, where the viewport is already the right width.
 */
export const MAX_APP_WIDTH = 560;

export function AppFrame({ children }: { children: ReactNode }) {
  if (Platform.OS !== 'web') return <>{children}</>;

  return (
    <View className="flex-1 items-center bg-black">
      <View className="w-full flex-1 bg-ink" style={{ maxWidth: MAX_APP_WIDTH }}>
        {children}
      </View>
    </View>
  );
}
