import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { ProgressBar } from '@/components/ProgressBar';
import { SyncBadge } from '@/components/SyncBadge';
import { ApiError, getDailyLogs, getDashboard, putDailyLog, type DailyLog } from '@/lib/api';
import { addDays, formatLong, today, yesterday } from '@/lib/dates';
import { checkMacros, meanOf, parseWholeNumber } from '@/lib/macros';

type Field = 'calories' | 'protein_g' | 'carbs_g' | 'fat_g';

const FIELDS: { key: Field; label: string; max: number }[] = [
  { key: 'calories', label: 'Calories', max: 20_000 },
  { key: 'protein_g', label: 'Protein (g)', max: 10_000 },
  { key: 'carbs_g', label: 'Carbs (g)', max: 10_000 },
  { key: 'fat_g', label: 'Fat (g)', max: 10_000 },
];

type Draft = Record<Field, string>;

const EMPTY: Draft = { calories: '', protein_g: '', carbs_g: '', fat_g: '' };

export default function Nutrition() {
  const insets = useSafeAreaInsets();
  const first = useRef<TextInput>(null);

  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [logs, setLogs] = useState<DailyLog[]>([]);
  const [tdee, setTdee] = useState<{ estimate_kcal: number | null; reliable: boolean } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [rows, dashboard] = await Promise.all([
        getDailyLogs(addDays(today(), -13), today()),
        getDashboard(today()),
      ]);
      setLogs(rows);
      setTdee(dashboard.tdee);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not load your nutrition');
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([getDailyLogs(addDays(today(), -13), today()), getDashboard(today())])
      .then(([rows, dashboard]) => {
        if (!active) return;
        setLogs(rows);
        setTdee(dashboard.tdee);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof ApiError ? err.detail : 'Could not load your nutrition');
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const todaysLog = useMemo(() => logs.find((l) => l.log_date === today()) ?? null, [logs]);
  const yesterdaysLog = useMemo(() => logs.find((l) => l.log_date === yesterday()) ?? null, [logs]);

  /** Yesterday's numbers, shown as placeholders until something is typed (§2.2). */
  const placeholders = useMemo(
    () => ({
      calories: yesterdaysLog?.calories?.toString() ?? '—',
      protein_g: yesterdaysLog?.protein_g?.toString() ?? '—',
      carbs_g: yesterdaysLog?.carbs_g?.toString() ?? '—',
      fat_g: yesterdaysLog?.fat_g?.toString() ?? '—',
    }),
    [yesterdaysLog],
  );

  const parsed = useMemo(
    () => ({
      calories: parseWholeNumber(draft.calories, 20_000),
      protein_g: parseWholeNumber(draft.protein_g, 10_000),
      carbs_g: parseWholeNumber(draft.carbs_g, 10_000),
      fat_g: parseWholeNumber(draft.fat_g, 10_000),
    }),
    [draft],
  );

  const check = useMemo(
    () => checkMacros(parsed.calories, parsed.protein_g, parsed.carbs_g, parsed.fat_g),
    [parsed],
  );

  const weekAverage = useMemo(() => {
    const recent = logs.filter((l) => l.log_date > addDays(today(), -8));
    return {
      calories: meanOf(recent.map((l) => l.calories)),
      protein: meanOf(recent.map((l) => l.protein_g)),
      days: recent.filter((l) => l.calories !== null).length,
    };
  }, [logs]);

  const copyYesterday = useCallback(() => {
    if (!yesterdaysLog) return;
    setDraft({
      calories: yesterdaysLog.calories?.toString() ?? '',
      protein_g: yesterdaysLog.protein_g?.toString() ?? '',
      carbs_g: yesterdaysLog.carbs_g?.toString() ?? '',
      fat_g: yesterdaysLog.fat_g?.toString() ?? '',
    });
    setSaved(false);
  }, [yesterdaysLog]);

  const save = useCallback(async () => {
    const patch: Partial<Record<Field, number>> = {};
    (Object.keys(parsed) as Field[]).forEach((key) => {
      const value = parsed[key];
      if (value !== null) patch[key] = value;
    });

    if (Object.keys(patch).length === 0) {
      setError('Enter at least one number');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      // The mismatch note never blocks this — §2.2 is explicit.
      await putDailyLog(today(), patch);
      setSaved(true);
      setDraft(EMPTY);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not save');
    } finally {
      setSaving(false);
    }
  }, [parsed, load]);

  const anythingTyped = Object.values(draft).some((v) => v.trim() !== '');

  return (
    <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
      <View className="px-5 pb-3 pt-2">
        <View className="flex-row items-center justify-between">
          <Text className="text-2xl font-bold text-white">Nutrition</Text>
          <SyncBadge />
        </View>
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
        <Card
          title="Today"
          footnote={
            todaysLog?.calories != null
              ? `Already logged ${todaysLog.calories} kcal today. Saving again replaces it.`
              : 'Placeholders show yesterday, so an unchanged day is one tap.'
          }
        >
          {FIELDS.map((field, index) => (
            <View key={field.key} className="mb-3">
              <Text className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
                {field.label}
              </Text>
              <TextInput
                ref={index === 0 ? first : undefined}
                className="h-14 rounded-2xl border border-line bg-ink px-4 text-2xl font-bold text-white"
                placeholder={placeholders[field.key]}
                placeholderTextColor="#3A4552"
                keyboardType="number-pad"
                returnKeyType="done"
                value={draft[field.key]}
                onChangeText={(text) => {
                  setDraft((current) => ({ ...current, [field.key]: text }));
                  setSaved(false);
                }}
                selectTextOnFocus
              />
            </View>
          ))}

          {check?.mismatched ? (
            <Text className="mb-3 text-xs text-muted">
              Your macros work out to {Math.round(check.computed)} kcal, but you entered{' '}
              {check.entered}. Worth a second look — saving anyway is fine.
            </Text>
          ) : null}

          {error ? <Text className="mb-3 text-sm text-danger">{error}</Text> : null}
          {saved && !error ? (
            <Text className="mb-3 text-sm text-accent">Saved for today.</Text>
          ) : null}

          <View className="gap-2">
            <Button title="Save" onPress={save} loading={saving} disabled={!anythingTyped} />
            {yesterdaysLog?.calories != null ? (
              <Button title="Same as yesterday" variant="ghost" onPress={copyYesterday} />
            ) : null}
          </View>
        </Card>

        <Card
          title="Last 7 days"
          footnote={
            tdee?.reliable && tdee.estimate_kcal
              ? `Maintenance is around ${tdee.estimate_kcal} kcal, measured from your own weight trend.`
              : 'Maintenance needs 14 days with both weight and calories before it means anything.'
          }
        >
          {loading ? (
            <View className="h-20 items-center justify-center">
              <ActivityIndicator color="#4ADE80" />
            </View>
          ) : weekAverage.calories === null ? (
            <Text className="text-sm text-muted">Nothing logged in the last week yet.</Text>
          ) : (
            <>
              <View className="flex-row items-baseline gap-3">
                <Text className="text-3xl font-bold text-white">
                  {Math.round(weekAverage.calories)}
                </Text>
                <Text className="text-sm text-muted">
                  kcal average over {weekAverage.days} {weekAverage.days === 1 ? 'day' : 'days'}
                </Text>
              </View>

              {weekAverage.protein !== null ? (
                <Text className="mt-1 text-sm text-muted">
                  {Math.round(weekAverage.protein)} g protein average
                </Text>
              ) : null}

              {tdee?.reliable && tdee.estimate_kcal ? (
                <View className="mt-4">
                  <ProgressBar
                    pct={(weekAverage.calories / tdee.estimate_kcal) * 100}
                    label="Against maintenance"
                  />
                  <Text className="mt-2 text-xs text-muted">
                    {weekAverage.calories < tdee.estimate_kcal
                      ? `About ${Math.round(tdee.estimate_kcal - weekAverage.calories)} kcal under maintenance a day.`
                      : `About ${Math.round(weekAverage.calories - tdee.estimate_kcal)} kcal over maintenance a day.`}
                  </Text>
                </View>
              ) : null}
            </>
          )}
        </Card>
      </ScrollView>
    </View>
  );
}
