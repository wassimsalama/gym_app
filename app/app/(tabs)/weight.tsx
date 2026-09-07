import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { MonthCalendar } from '@/components/MonthCalendar';
import { ProgressBar } from '@/components/ProgressBar';
import { SegmentedControl } from '@/components/SegmentedControl';
import { WeightChart } from '@/components/WeightChart';
import { ApiError, getDashboard, putDailyLog, type Dashboard } from '@/lib/api';
import {
  formatLong,
  formatRelativeDay,
  isSameMonth,
  startOfMonth,
  today,
  type IsoDate,
} from '@/lib/dates';
import { useUnit } from '@/lib/profile';
import {
  deltaOver,
  RANGE_OPTIONS,
  rangeLabel,
  sliceSeries,
  unavailableRanges,
  type RangeKey,
} from '@/lib/ranges';
import { formatDelta, formatWeight, fromKg, parseWeightInput } from '@/lib/units';

export default function Weight() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const unit = useUnit();
  const input = useRef<TextInput>(null);

  const [range, setRange] = useState<RangeKey>('1M');
  const [logDate, setLogDate] = useState<IsoDate>(today());
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState<IsoDate>(startOfMonth());

  const [entry, setEntry] = useState('');
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<IsoDate | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await getDashboard());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not load your trend');
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // State is set from promise callbacks, never synchronously in the effect
    // body — that would cascade renders on every mount.
    let active = true;

    getDashboard()
      .then((next) => {
        if (active) setData(next);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof ApiError ? err.detail : 'Could not load your trend');
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    // Spec §2.4: the field is pre-focused, so logging today is one tap after
    // typing. Picking another date is opt-in and never gets in the way.
    const timer = setTimeout(() => input.current?.focus(), 350);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  /** Days already holding a weight — dotted in the calendar so gaps are obvious. */
  const loggedDates = useMemo(
    () => new Set((data?.weight.series ?? []).map((p) => p.date)),
    [data],
  );

  const existingForDate = useMemo(
    () => data?.weight.series.find((p) => p.date === logDate)?.raw_kg ?? null,
    [data, logDate],
  );

  const pickDate = useCallback(
    (date: IsoDate) => {
      setLogDate(date);
      setCalendarOpen(false);
      setError(null);
      setSaved(null);
      // Prefill with whatever is already recorded, so backfilling a day that
      // exists is a correction rather than a blind overwrite.
      const existing = data?.weight.series.find((p) => p.date === date)?.raw_kg ?? null;
      setEntry(existing === null ? '' : fromKg(existing, unit).toFixed(1));
      setTimeout(() => input.current?.focus(), 250);
    },
    [data, unit],
  );

  const save = useCallback(async () => {
    const kg = parseWeightInput(entry, unit);
    if (kg === null) {
      setError('Enter a weight first');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await putDailyLog(logDate, { weight_kg: kg });
      setSaved(logDate);
      setEntry('');
      // Backfilling should land you back on today, ready for tomorrow.
      setLogDate(today());
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not save');
    } finally {
      setSaving(false);
    }
  }, [entry, unit, logDate, load]);

  const weight = data?.weight;
  const goal = data?.goal ?? null;
  const isToday = logDate === today();

  // Memoised so the fallback does not mint a fresh array on every render and
  // invalidate everything downstream of it.
  const series = useMemo(() => weight?.series ?? [], [weight]);
  const visible = useMemo(() => sliceSeries(series, range), [series, range]);
  const rangeDelta = useMemo(() => deltaOver(visible), [visible]);
  const unavailable = useMemo(() => unavailableRanges(series), [series]);

  return (
    <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
      <View className="px-5 pb-3 pt-2">
        <Text className="text-2xl font-bold text-white">Weight</Text>
        <Text className="mt-1 text-sm text-muted">{formatLong(today())}</Text>
      </View>

      <ScrollView
        className="flex-1 px-5"
        contentContainerClassName="gap-4 pb-10"
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={load} tintColor="#8A97A6" />
        }
      >
        <Card title={`Log a weight (${unit})`}>
          <View className="flex-row gap-3">
            <TextInput
              ref={input}
              className="h-16 flex-1 rounded-2xl border border-line bg-ink px-4 text-3xl font-bold text-white"
              placeholder="—"
              placeholderTextColor="#3A4552"
              keyboardType="decimal-pad"
              returnKeyType="done"
              value={entry}
              onChangeText={setEntry}
              onSubmitEditing={save}
              selectTextOnFocus
            />
            <View className="w-28 justify-center">
              <Button title="Save" onPress={save} loading={saving} disabled={!entry} />
            </View>
          </View>

          <Pressable
            className="mt-3 flex-row items-center justify-between rounded-xl border border-line px-4 py-3 active:bg-line"
            onPress={() => {
              setVisibleMonth(startOfMonth(logDate));
              setCalendarOpen(true);
            }}
          >
            <Text className="text-sm text-muted">Date</Text>
            <Text className="text-sm font-semibold text-white">
              {formatRelativeDay(logDate)}
              {!isToday && existingForDate !== null ? '  ·  editing' : ''}
              {'   ▾'}
            </Text>
          </Pressable>

          {!isToday ? (
            <Text className="mt-2 text-xs text-muted">
              Backfilling {formatLong(logDate)}. The trend recalculates once it saves.
            </Text>
          ) : null}

          {error ? <Text className="mt-3 text-sm text-danger">{error}</Text> : null}
          {saved && !error ? (
            <Text className="mt-3 text-sm text-accent">Saved {formatRelativeDay(saved)}.</Text>
          ) : null}
        </Card>

        <Card
          title="History"
          footnote="Faint dots are daily readings; the bold line is the 7-day average. Judge progress by the line."
        >
          {loading ? (
            <View className="h-48 items-center justify-center">
              <ActivityIndicator color="#4ADE80" />
            </View>
          ) : (
            <>
              <View className="mb-3">
                <SegmentedControl
                  options={RANGE_OPTIONS}
                  value={range}
                  onChange={setRange}
                  disabledValues={unavailable}
                />
              </View>

              <View className="mb-3">
                <Text className="text-3xl font-bold text-white">
                  {formatWeight(weight?.current_smoothed_kg, unit)}
                </Text>
                <Text className="mt-1 text-sm text-muted">
                  {rangeDelta === null ? (
                    'Not enough logged in this span to show a change yet.'
                  ) : (
                    <>
                      <Text
                        className={`font-semibold ${
                          rangeDelta <= 0 ? 'text-accent' : 'text-white'
                        }`}
                      >
                        {formatDelta(rangeDelta, unit)}
                      </Text>
                      {` over ${rangeLabel(range).toLowerCase()} · ${visible.length} ${
                        visible.length === 1 ? 'entry' : 'entries'
                      }`}
                    </>
                  )}
                </Text>
              </View>

              <WeightChart series={visible} unit={unit} width={width - 72} />
            </>
          )}
        </Card>

        {goal ? (
          <Card title="Goal">
            <ProgressBar
              pct={goal.progress_pct}
              label="Progress"
              caption={
                goal.projected_date
                  ? `On this trend you reach it around ${formatLong(goal.projected_date)}.`
                  : 'Not enough of a trend yet to project a date.'
              }
            />
          </Card>
        ) : null}
      </ScrollView>

      <Modal
        visible={calendarOpen}
        animationType="slide"
        transparent
        onRequestClose={() => setCalendarOpen(false)}
      >
        <Pressable
          className="flex-1 justify-end bg-black/60"
          onPress={() => setCalendarOpen(false)}
        >
          <Pressable
            className="rounded-t-3xl border-t border-line bg-surface px-5 pt-5"
            style={{ paddingBottom: insets.bottom + 20 }}
            onPress={(event) => event.stopPropagation()}
          >
            <View className="mb-4 flex-row items-center justify-between">
              <Text className="text-lg font-bold text-white">Pick a day</Text>
              <Pressable onPress={() => pickDate(today())}>
                <Text className="text-sm font-semibold text-accent">Today</Text>
              </Pressable>
            </View>

            <MonthCalendar
              month={visibleMonth}
              selected={logDate}
              marked={loggedDates}
              onSelect={pickDate}
              onMonthChange={setVisibleMonth}
            />

            <Text className="mt-4 text-xs text-muted">
              A dot marks a day you have already logged.
              {isSameMonth(visibleMonth, today()) ? ' Future days are not selectable.' : ''}
            </Text>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}
