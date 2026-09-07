import { Text, View } from 'react-native';

import { formatShort } from '@/lib/dates';
import { formatDelta, formatWeight, fromKg, type Unit } from '@/lib/units';

type Recap = {
  week_start: string;
  week_end: string;
  sessions: number;
  total_sets: number;
  total_volume_kg: number;
  weight_delta_kg: number | null;
  days_trained: number;
  days_logged: number;
  best_lift: {
    exercise_name: string;
    e1rm: number;
    was_a_record: boolean;
  } | null;
};

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View className="flex-1">
      <Text className="text-2xl font-bold text-white">{value}</Text>
      <Text className="mt-0.5 text-xs text-muted">{label}</Text>
    </View>
  );
}

/**
 * Last week, self-contained (spec §2.1, §7.7).
 *
 * Screenshot-friendly is a real requirement: this gets sent to a training
 * partner with no context, so the dates and units are on the card rather than
 * implied by the screen around it.
 */
export function RecapCard({ recap, unit }: { recap: Recap; unit: Unit }) {
  const volume = Math.round(fromKg(recap.total_volume_kg, unit));

  return (
    <View className="rounded-2xl border border-line bg-surface p-4">
      <Text className="text-xs font-semibold uppercase tracking-wider text-muted">
        Last week · {formatShort(recap.week_start)} – {formatShort(recap.week_end)}
      </Text>

      <View className="mt-4 flex-row">
        <Stat
          value={String(recap.sessions)}
          label={recap.sessions === 1 ? 'session' : 'sessions'}
        />
        <Stat value={String(recap.total_sets)} label="sets" />
        <Stat value={volume.toLocaleString()} label={`${unit} moved`} />
      </View>

      <View className="mt-4 flex-row">
        <Stat
          value={recap.weight_delta_kg === null ? '—' : formatDelta(recap.weight_delta_kg, unit)}
          label="weight"
        />
        <Stat value={`${recap.days_trained}/7`} label="days trained" />
        <Stat value={`${recap.days_logged}/7`} label="days logged" />
      </View>

      {recap.best_lift ? (
        <View className="mt-4 border-t border-line pt-4">
          <Text className="text-xs text-muted">Best lift</Text>
          <Text className="mt-1 text-base font-semibold text-white">
            {recap.best_lift.exercise_name} · {formatWeight(recap.best_lift.e1rm, unit)} est. 1RM
          </Text>
          {recap.best_lift.was_a_record ? (
            <Text className="mt-1 text-sm font-semibold text-accent">
              An all-time best for that lift.
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
