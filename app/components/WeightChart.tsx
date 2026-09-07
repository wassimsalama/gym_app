import { useMemo } from 'react';
import { Text, View } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';

import type { WeightSeriesPoint } from '@/lib/api';
import { formatShort } from '@/lib/dates';
import { fromKg, type Unit } from '@/lib/units';

type Props = {
  series: WeightSeriesPoint[];
  unit: Unit;
  width: number;
};

const SMOOTHED = '#4ADE80';
const RAW = '#8A97A6';

/**
 * Raw daily points sit faint beneath a bold smoothed line (spec §2.4).
 * Smoothing is mandatory: unsmoothed daily weight swings on water alone, and
 * showing that makes a working cut look like failure every other morning.
 */
export function WeightChart({ series, unit, width }: Props) {
  const { raw, smoothed, min, max } = useMemo(() => {
    const rawValues = series.map((p) => fromKg(p.raw_kg, unit));
    const smoothValues = series.map((p) => fromKg(p.smoothed_kg, unit));
    const all = [...rawValues, ...smoothValues];

    // Pad the axis so the line never touches the frame.
    const lo = all.length ? Math.min(...all) : 0;
    const hi = all.length ? Math.max(...all) : 1;
    const pad = Math.max((hi - lo) * 0.15, 0.5);

    // Label only the ends; anything denser is unreadable at phone width.
    const label = (index: number) =>
      index === 0 || index === series.length - 1 ? formatShort(series[index].date) : undefined;

    return {
      raw: series.map((p, i) => ({ value: rawValues[i], label: label(i) })),
      smoothed: series.map((p, i) => ({ value: smoothValues[i] })),
      min: lo - pad,
      max: hi + pad,
    };
  }, [series, unit]);

  if (series.length === 0) {
    return (
      <View className="h-48 items-center justify-center">
        <Text className="text-sm text-muted">Log a weight to start the trend.</Text>
      </View>
    );
  }

  // A single point has no line to draw; state the number instead of a dot.
  if (series.length === 1) {
    return (
      <View className="h-48 items-center justify-center gap-1">
        <Text className="text-3xl font-bold text-white">
          {raw[0].value.toFixed(1)} {unit}
        </Text>
        <Text className="text-sm text-muted">One more day and the trend line starts.</Text>
      </View>
    );
  }

  return (
    <LineChart
      data={raw}
      data2={smoothed}
      width={width}
      height={180}
      initialSpacing={8}
      endSpacing={8}
      spacing={Math.max(width / Math.max(series.length - 1, 1) - 1, 4)}
      adjustToWidth
      yAxisOffset={min}
      maxValue={max - min}
      // Raw: thin, faint, unobtrusive.
      color={RAW}
      thickness={1}
      dataPointsColor={RAW}
      dataPointsRadius={2}
      // Smoothed: the line the user is meant to read.
      color2={SMOOTHED}
      thickness2={3}
      hideDataPoints2
      curved
      yAxisThickness={0}
      xAxisColor="#232C36"
      rulesColor="#232C36"
      rulesType="solid"
      noOfSections={3}
      yAxisTextStyle={{ color: RAW, fontSize: 10 }}
      xAxisLabelTextStyle={{ color: RAW, fontSize: 10 }}
      yAxisLabelSuffix={` ${unit}`}
      formatYLabel={(value: string) => Number(value).toFixed(0)}
      backgroundColor="transparent"
    />
  );
}
