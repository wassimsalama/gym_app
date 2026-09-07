import { Text, View } from 'react-native';

type Props = {
  /** 0–100, already clamped by the API. */
  pct: number;
  label?: string;
  caption?: string;
};

export function ProgressBar({ pct, label, caption }: Props) {
  const clamped = Math.max(0, Math.min(100, pct));

  return (
    <View className="gap-2">
      {label ? (
        <View className="flex-row items-baseline justify-between">
          <Text className="text-sm text-muted">{label}</Text>
          <Text className="text-sm font-semibold text-white">{clamped.toFixed(0)}%</Text>
        </View>
      ) : null}

      <View className="h-3 overflow-hidden rounded-full bg-line">
        <View className="h-full rounded-full bg-accent" style={{ width: `${clamped}%` }} />
      </View>

      {caption ? <Text className="text-xs text-muted">{caption}</Text> : null}
    </View>
  );
}
