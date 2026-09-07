import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
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
import { ProgressBar } from '@/components/ProgressBar';
import { WeightChart } from '@/components/WeightChart';
import { ApiError, getDashboard, putDailyLog, type Dashboard } from '@/lib/api';
import { formatLong, today } from '@/lib/dates';
import { useUnit } from '@/lib/profile';
import { formatDelta, formatWeight, parseWeightInput } from '@/lib/units';

export default function Weight() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const unit = useUnit();
  const input = useRef<TextInput>(null);

  const [entry, setEntry] = useState('');
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    // State is set from the promise callbacks, never synchronously in the
    // effect body — that would cascade renders on every mount.
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

    // Spec §2.4: one number field, pre-focused — save is one tap after typing.
    const timer = setTimeout(() => input.current?.focus(), 350);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  const save = useCallback(async () => {
    const kg = parseWeightInput(entry, unit);
    if (kg === null) {
      setError('Enter a weight first');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await putDailyLog(today(), { weight_kg: kg });
      setEntry('');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not save');
    } finally {
      setSaving(false);
    }
  }, [entry, unit, load]);

  const goal = data?.goal ?? null;
  const weight = data?.weight;

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
        <Card title={`Today's weight (${unit})`}>
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
          {error ? <Text className="mt-3 text-sm text-danger">{error}</Text> : null}
        </Card>

        <Card
          title="Trend"
          footnote="Faint dots are daily readings; the bold line is the 7-day average. Judge progress by the line."
        >
          {loading ? (
            <View className="h-48 items-center justify-center">
              <ActivityIndicator color="#4ADE80" />
            </View>
          ) : (
            <>
              <View className="mb-3 flex-row items-baseline gap-3">
                <Text className="text-3xl font-bold text-white">
                  {formatWeight(weight?.current_smoothed_kg, unit)}
                </Text>
                {weight?.delta_since_start_kg != null ? (
                  <Text
                    className={`text-base font-semibold ${
                      weight.delta_since_start_kg <= 0 ? 'text-accent' : 'text-muted'
                    }`}
                  >
                    {formatDelta(weight.delta_since_start_kg, unit)} since start
                  </Text>
                ) : null}
              </View>
              <WeightChart series={weight?.series ?? []} unit={unit} width={width - 72} />
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
    </View>
  );
}
