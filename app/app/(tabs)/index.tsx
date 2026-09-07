import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { ProgressBar } from '@/components/ProgressBar';
import { StreakBadge } from '@/components/StreakBadge';
import { SyncBadge } from '@/components/SyncBadge';
import { VolumeRings } from '@/components/VolumeRings';
import { WeightChart } from '@/components/WeightChart';
import { getDashboard, type Dashboard } from '@/lib/api';
import { describeError, type DisplayError } from '@/lib/errors';
import { signOut, useAuth } from '@/lib/auth';
import { formatLong, today } from '@/lib/dates';
import { driftFromBaselineKg } from '@/lib/goalState';
import { useUnit } from '@/lib/profile';
import { formatDelta, formatWeight } from '@/lib/units';

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const unit = useUnit();

  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<DisplayError | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await getDashboard(today()));
      setError(null);
    } catch (err) {
      setError(describeError(err, 'Could not load your dashboard'));
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    getDashboard(today())
      .then((next) => {
        if (active) setData(next);
      })
      .catch((err: unknown) => {
        if (active) setError(describeError(err, 'Could not load your dashboard'));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const weight = data?.weight;
  const goal = data?.goal ?? null;
  const baselineDrift = goal ? driftFromBaselineKg(goal, weight?.current_smoothed_kg) : null;

  return (
    <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
      <View className="px-5 pb-3 pt-2">
        <View className="flex-row items-center justify-between">
          <Text className="text-2xl font-bold text-white">Dashboard</Text>
          <SyncBadge />
        </View>
        <Text className="mt-1 text-sm text-muted">{session?.user.email ?? ''}</Text>
      </View>

      <ScrollView
        className="flex-1 px-5"
        contentContainerClassName="gap-4 pb-10"
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={load} tintColor="#8A97A6" />
        }
      >
        {loading ? (
          <View className="h-40 items-center justify-center">
            <ActivityIndicator color="#4ADE80" />
          </View>
        ) : error ? (
          <Card title={error.title}>
            <Text className="text-base text-danger">{error.detail}</Text>
            {!error.offline ? (
              <Text className="mt-2 text-xs text-muted">
                The server answered, so this is not your connection. If it persists after a reload,
                the app and the API may be out of step.
              </Text>
            ) : null}
            <View className="mt-4">
              <Button title="Retry" onPress={load} />
            </View>
          </Card>
        ) : (
          <>
            {data ? (
              <StreakBadge logged14={data.streaks.logged_14} trained14={data.streaks.trained_14} />
            ) : null}

            {data && data.prs_recent.length > 0 ? (
              <Card title="Recent personal records">
                {data.prs_recent.map((pr) => (
                  <View key={pr.exercise_id} className="mb-2">
                    <Text className="text-base font-bold text-accent">{pr.exercise_name}</Text>
                    <Text className="mt-0.5 text-sm text-muted">
                      {formatWeight(pr.e1rm, unit)} estimated 1RM, up from{' '}
                      {formatWeight(pr.previous_e1rm, unit)} · {formatLong(pr.achieved_on)}
                    </Text>
                  </View>
                ))}
              </Card>
            ) : null}

            <Card title="Weight trend">
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
              <WeightChart series={weight?.series ?? []} unit={unit} />
            </Card>

            {goal ? (
              <Card title="Goal">
                <ProgressBar pct={goal.progress_pct} label="Progress" />

                <View className="mt-4 flex-row justify-between">
                  <View>
                    <Text className="text-xs text-muted">Start</Text>
                    <Text className="mt-0.5 text-base font-semibold text-white">
                      {formatWeight(goal.start_weight_kg, unit)}
                    </Text>
                  </View>
                  <View className="items-center">
                    <Text className="text-xs text-muted">Now</Text>
                    <Text className="mt-0.5 text-base font-semibold text-white">
                      {formatWeight(weight?.current_smoothed_kg, unit)}
                    </Text>
                  </View>
                  <View className="items-end">
                    <Text className="text-xs text-muted">Goal</Text>
                    <Text className="mt-0.5 text-base font-semibold text-accent">
                      {formatWeight(goal.goal_weight_kg, unit)}
                    </Text>
                  </View>
                </View>

                {baselineDrift !== null ? (
                  <Text className="mt-4 text-xs text-muted">
                    You&apos;re {formatWeight(baselineDrift, unit)} above where this goal started,
                    so it reads 0%. Restart it from the Weight tab to measure from today.
                  </Text>
                ) : (
                  <>
                    <Text className="mt-4 text-xs text-muted">
                      {goal.projected_date
                        ? `On this trend you reach it around ${formatLong(goal.projected_date)}.`
                        : 'Not enough of a trend yet to project a date.'}
                    </Text>
                    {goal.on_track !== null ? (
                      <Text
                        className={`mt-2 text-sm font-semibold ${
                          goal.on_track ? 'text-accent' : 'text-danger'
                        }`}
                      >
                        {goal.on_track
                          ? 'Ahead of your target date.'
                          : 'Behind your target date at this rate.'}
                      </Text>
                    ) : null}
                  </>
                )}
              </Card>
            ) : null}

            <Card
              title="Maintenance"
              footnote="Measured from your own weight trend and intake, not a formula."
            >
              {data?.tdee.reliable && data.tdee.estimate_kcal ? (
                <>
                  <Text className="text-3xl font-bold text-white">
                    {data.tdee.estimate_kcal}
                    <Text className="text-base font-normal text-muted"> kcal/day</Text>
                  </Text>
                  <Text className="mt-1 text-sm text-muted">
                    Based on {data.tdee.days_of_data} days of paired weight and calories.
                  </Text>
                </>
              ) : (
                <Text className="text-sm text-muted">
                  Collecting data — {Math.max(0, 14 - (data?.tdee.days_of_data ?? 0))} more days
                  with both a weight and calories logged.
                </Text>
              )}
            </Card>

            <Card title="This week's volume" footnote="Sets per muscle group since Monday.">
              <VolumeRings rings={data?.volume ?? []} />
            </Card>

            <Card title="What lands next" footnote="Roadmap §12.">
              <Text className="text-sm text-muted">
                Phase 4 — photos, the suggestions engine, weekly recap, TestFlight.
              </Text>
            </Card>
          </>
        )}

        <Button title="Sign out" variant="ghost" onPress={() => void signOut()} />
      </ScrollView>
    </View>
  );
}
