import { useMemo } from 'react';
import { Pressable, Text, View } from 'react-native';

import {
  addDays,
  addMonths,
  daysInMonth,
  firstWeekdayOfMonth,
  formatMonth,
  isFuture,
  startOfMonth,
  today,
  type IsoDate,
} from '@/lib/dates';

type Props = {
  /** Any date inside the month being shown. */
  month: IsoDate;
  selected: IsoDate;
  /** Days that already hold data — rendered with a marker. */
  marked?: Set<IsoDate>;
  onSelect: (date: IsoDate) => void;
  onMonthChange: (month: IsoDate) => void;
  /** Nothing later than this is selectable. Defaults to today. */
  maxDate?: IsoDate;
};

// Monday-first, matching the Monday-anchored week the volume rings use (§7.6).
const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

/**
 * Month grid for picking a date to log against.
 *
 * Hand-rolled rather than pulling in a picker dependency: the Photos tab needs
 * the same month view (§2.5), and a native picker cannot show which days
 * already have data — which is the thing that makes backfilling quick.
 */
export function MonthCalendar({
  month,
  selected,
  marked,
  onSelect,
  onMonthChange,
  maxDate = today(),
}: Props) {
  const { cells, canGoNext } = useMemo(() => {
    const first = startOfMonth(month);
    const lead = firstWeekdayOfMonth(first);
    const total = daysInMonth(first);

    const days: (IsoDate | null)[] = Array.from({ length: lead }, () => null);
    for (let i = 0; i < total; i += 1) days.push(addDays(first, i));

    return {
      cells: days,
      // Never page into a month that is entirely in the future.
      canGoNext: !isFuture(startOfMonth(addMonths(first, 1)), maxDate),
    };
  }, [month, maxDate]);

  return (
    <View className="gap-3">
      <View className="flex-row items-center justify-between">
        <Pressable
          className="h-10 w-10 items-center justify-center rounded-full active:bg-line"
          onPress={() => onMonthChange(addMonths(month, -1))}
          accessibilityLabel="Previous month"
        >
          <Text className="text-xl text-muted">‹</Text>
        </Pressable>

        <Text className="text-base font-semibold text-white">{formatMonth(month)}</Text>

        <Pressable
          className={`h-10 w-10 items-center justify-center rounded-full ${
            canGoNext ? 'active:bg-line' : 'opacity-25'
          }`}
          disabled={!canGoNext}
          onPress={() => onMonthChange(addMonths(month, 1))}
          accessibilityLabel="Next month"
        >
          <Text className="text-xl text-muted">›</Text>
        </Pressable>
      </View>

      <View className="flex-row">
        {WEEKDAYS.map((day, i) => (
          <View key={`${day}-${i}`} className="flex-1 items-center">
            <Text className="text-xs font-semibold text-muted">{day}</Text>
          </View>
        ))}
      </View>

      <View className="flex-row flex-wrap">
        {cells.map((date, index) => {
          if (date === null) {
            return <View key={`pad-${index}`} className="h-11 w-[14.28%]" />;
          }

          const disabled = isFuture(date, maxDate);
          const isSelected = date === selected;
          const hasData = marked?.has(date) ?? false;
          const dayNumber = Number(date.slice(-2));

          return (
            <Pressable
              key={date}
              className="h-11 w-[14.28%] items-center justify-center"
              disabled={disabled}
              onPress={() => onSelect(date)}
              accessibilityLabel={date}
              accessibilityState={{ selected: isSelected, disabled }}
            >
              <View
                className={`h-9 w-9 items-center justify-center rounded-full ${
                  isSelected ? 'bg-accent' : ''
                }`}
              >
                <Text
                  className={
                    disabled
                      ? 'text-base text-line'
                      : isSelected
                        ? 'text-base font-bold text-ink'
                        : 'text-base text-white'
                  }
                >
                  {dayNumber}
                </Text>
              </View>
              {/* A filled dot means that day already has a weight. */}
              <View
                className={`mt-0.5 h-1 w-1 rounded-full ${
                  hasData && !isSelected ? 'bg-accent' : 'bg-transparent'
                }`}
              />
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
