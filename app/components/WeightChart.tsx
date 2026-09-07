import { useMemo, useState } from 'react';
import { Text, View, type LayoutChangeEvent } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';

import type { WeightSeriesPoint } from '@/lib/api';
import { formatShort } from '@/lib/dates';
import { fromKg, type Unit } from '@/lib/units';

type Props = {
  series: WeightSeriesPoint[];
  unit: Unit;
};

const SMOOTHED = '#4ADE80';
const RAW = '#8A97A6';
const GRID = '#232C36';

/** Room for the y-axis numbers, which sit outside the plotting width. */
const Y_AXIS_WIDTH = 34;
/** Breathing room so the first and last points are not flush against the edges. */
const EDGE_SPACING = 6;
const CHART_HEIGHT = 180;

/**
 * Raw daily points sit faint beneath a bold smoothed line (spec §2.4).
 * Smoothing is mandatory: unsmoothed daily weight swings on water alone, and
 * showing that makes a working cut look like failure every other morning.
 *
 * The chart measures its own container rather than being handed a width, so it
 * cannot drift out of alignment when the padding around it changes. Date
 * labels are rendered beneath it instead of on the axis — the axis centres a
 * label under its point, which pushes the final one off the right edge.
 */
export function WeightChart({ series, unit }: Props) {
  const [containerWidth, setContainerWidth] = useState(0);

  const onLayout = (event: LayoutChangeEvent) => {
    const next = Math.round(event.nativeEvent.layout.width);
    if (next !== containerWidth) setContainerWidth(next);
  };

  const { raw, smoothed, min, max } = useMemo(() => {
    const rawValues = series.map((p) => fromKg(p.raw_kg, unit));
    const smoothValues = series.map((p) => fromKg(p.smoothed_kg, unit));
    const all = [...rawValues, ...smoothValues];

    // Pad the axis so the line never touches the frame.
    const lo = all.length ? Math.min(...all) : 0;
    const hi = all.length ? Math.max(...all) : 1;
    const pad = Math.max((hi - lo) * 0.15, 0.5);

    return {
      raw: rawValues.map((value) => ({ value })),
      smoothed: smoothValues.map((value) => ({ value })),
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
          {fromKg(series[0].raw_kg, unit).toFixed(1)} {unit}
        </Text>
        <Text className="text-sm text-muted">One more day and the trend line starts.</Text>
      </View>
    );
  }

  const plotWidth = Math.max(containerWidth - Y_AXIS_WIDTH, 0);

  return (
    <View className="w-full" onLayout={onLayout}>
      {/* Nothing may paint outside the card, whatever the chart computes. */}
      <View className="w-full overflow-hidden" style={{ height: CHART_HEIGHT + 8 }}>
        {plotWidth > 0 ? (
          <LineChart
            data={raw}
            data2={smoothed}
            width={plotWidth}
            height={CHART_HEIGHT}
            adjustToWidth
            initialSpacing={EDGE_SPACING}
            endSpacing={EDGE_SPACING}
            yAxisLabelWidth={Y_AXIS_WIDTH}
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
            yAxisOffset={min}
            maxValue={max - min}
            noOfSections={3}
            yAxisThickness={0}
            xAxisColor={GRID}
            rulesColor={GRID}
            rulesType="solid"
            yAxisTextStyle={{ color: RAW, fontSize: 10 }}
            formatYLabel={(value: string) => Number(value).toFixed(0)}
            hideRules={false}
            disableScroll
            backgroundColor="transparent"
          />
        ) : null}
      </View>

      {/* Endpoints as plain text, aligned to the card rather than to a data
          point — an axis label centred on the last point overflows the edge. */}
      <View className="mt-1 flex-row justify-between" style={{ paddingLeft: Y_AXIS_WIDTH }}>
        <Text className="text-xs text-muted">{formatShort(series[0].date)}</Text>
        <Text className="text-xs text-muted">{formatShort(series[series.length - 1].date)}</Text>
      </View>
    </View>
  );
}
