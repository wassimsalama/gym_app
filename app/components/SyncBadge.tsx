import { Text, View } from 'react-native';

import { useSyncState } from '@/lib/useSync';

/**
 * Shown only once writes have actually struggled (spec §8.2 — after more than
 * three attempts). A badge that appears on every save would train the user to
 * ignore it, and the ordinary case is that a write lands immediately.
 */
export function SyncBadge() {
  const { struggling } = useSyncState();

  if (struggling === 0) return null;

  return (
    <View className="self-start rounded-full border border-line bg-surface px-3 py-1">
      <Text className="text-xs font-semibold text-muted">{struggling} unsynced · will retry</Text>
    </View>
  );
}
