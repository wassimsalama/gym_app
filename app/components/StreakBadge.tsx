import { Text, View } from 'react-native';

type Props = {
  logged14: number;
  trained14: number;
  windowDays?: number;
};

/**
 * Rolling counts, never a consecutive-day streak (spec §2.1).
 *
 * "0 day streak" turns one missed Tuesday into a reason to stop entirely.
 * "4 of the last 14" survives a bad week, which is the point.
 */
export function StreakBadge({ logged14, trained14, windowDays = 14 }: Props) {
  return (
    <View className="flex-row gap-3">
      <View className="flex-1 rounded-2xl border border-line bg-surface p-4">
        <Text className="text-2xl font-bold text-white">
          {trained14}
          <Text className="text-base font-normal text-muted">/{windowDays}</Text>
        </Text>
        <Text className="mt-1 text-xs text-muted">days trained</Text>
      </View>
      <View className="flex-1 rounded-2xl border border-line bg-surface p-4">
        <Text className="text-2xl font-bold text-white">
          {logged14}
          <Text className="text-base font-normal text-muted">/{windowDays}</Text>
        </Text>
        <Text className="mt-1 text-xs text-muted">days logged</Text>
      </View>
    </View>
  );
}
