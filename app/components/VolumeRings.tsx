import { Text, View } from 'react-native';

type Ring = {
  muscle_group: string;
  sets_this_week: number;
  weekly_target: number;
};

/**
 * Sets per muscle group against target, for the Monday-anchored week (§7.6).
 *
 * Groups at zero are shown deliberately: a leg day that never happened is the
 * most useful thing on the card, and hiding empty rows would bury it.
 */
export function VolumeRings({ rings }: { rings: Ring[] }) {
  const targeted = rings.filter((r) => r.weekly_target > 0);
  const extra = rings.filter((r) => r.weekly_target === 0 && r.sets_this_week > 0);

  if (targeted.length === 0) return null;

  return (
    <View className="gap-3">
      {[...targeted, ...extra].map((ring) => {
        const pct =
          ring.weekly_target > 0
            ? Math.min(100, (ring.sets_this_week / ring.weekly_target) * 100)
            : 100;
        const met = ring.weekly_target > 0 && ring.sets_this_week >= ring.weekly_target;

        return (
          <View key={ring.muscle_group}>
            <View className="mb-1 flex-row items-baseline justify-between">
              <Text className="text-sm capitalize text-white">{ring.muscle_group}</Text>
              <Text className={`text-xs ${met ? 'text-accent' : 'text-muted'}`}>
                {ring.sets_this_week}
                {ring.weekly_target > 0 ? ` / ${ring.weekly_target} sets` : ' sets'}
              </Text>
            </View>
            <View className="h-2 overflow-hidden rounded-full bg-line">
              <View
                className={`h-full rounded-full ${met ? 'bg-accent' : 'bg-muted'}`}
                style={{ width: `${pct}%` }}
              />
            </View>
          </View>
        );
      })}
    </View>
  );
}
