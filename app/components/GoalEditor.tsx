import { useState } from 'react';
import { Modal, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { MonthCalendar } from '@/components/MonthCalendar';
import { ApiError, createGoal, updateGoal, type Goal } from '@/lib/api';
import { formatLong, startOfMonth, today, type IsoDate } from '@/lib/dates';
import { formatWeight, fromKg, parseWeightInput, type Unit } from '@/lib/units';

type Props = {
  visible: boolean;
  goal: Goal;
  unit: Unit;
  /** Most recent smoothed weight, used to describe re-baselining. */
  currentKg: number | null;
  onClose: () => void;
  onSaved: () => void;
};

/**
 * Two distinct operations, kept visually distinct because they mean different
 * things:
 *
 *   Save        — move the target. The baseline is untouched, so progress
 *                 already earned is preserved (PATCH /goals/active).
 *   Start over  — open a new goal from today's weight. Progress resets,
 *                 deliberately (POST /goals).
 *
 * Conflating them would either silently reset progress on an innocuous edit or
 * make a stale baseline impossible to fix.
 */
export function GoalEditor({ visible, goal, unit, currentKg, onClose, onSaved }: Props) {
  const insets = useSafeAreaInsets();

  // Seeded at mount rather than synced in an effect. The parent remounts this
  // via `key` each time it opens, so a cancelled edit leaves nothing behind and
  // no effect has to chase prop changes.
  const [weight, setWeight] = useState(() => fromKg(goal.goal_weight_kg, unit).toFixed(1));
  const [startWeight, setStartWeight] = useState(() =>
    fromKg(goal.start_weight_kg, unit).toFixed(1),
  );
  const [targetDate, setTargetDate] = useState<IsoDate | null>(goal.target_date);
  const [pickingDate, setPickingDate] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState<IsoDate>(
    startOfMonth(goal.target_date ?? today()),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRestart, setConfirmRestart] = useState(false);

  async function save() {
    const kg = parseWeightInput(weight, unit);
    if (kg === null) {
      setError('Enter a goal weight');
      return;
    }

    const startKg = parseWeightInput(startWeight, unit);
    if (startKg === null) {
      setError('Enter the weight you started from');
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await updateGoal({
        goal_weight_kg: kg,
        start_weight_kg: startKg,
        target_date: targetDate,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not save');
    } finally {
      setBusy(false);
    }
  }

  async function restart() {
    const kg = parseWeightInput(weight, unit);
    if (kg === null) {
      setError('Enter a goal weight');
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await createGoal(kg, targetDate);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not start a new goal');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <Pressable className="flex-1 justify-end bg-black/60" onPress={onClose}>
        <Pressable
          className="max-h-[88%] rounded-t-3xl border-t border-line bg-surface"
          onPress={(event) => event.stopPropagation()}
        >
          <ScrollView
            className="px-5 pt-5"
            contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}
            keyboardShouldPersistTaps="handled"
          >
            <View className="mb-4 flex-row items-center justify-between">
              <Text className="text-lg font-bold text-white">Your goal</Text>
              <Pressable onPress={onClose}>
                <Text className="text-sm font-semibold text-muted">Cancel</Text>
              </Pressable>
            </View>

            {pickingDate ? (
              <>
                <MonthCalendar
                  month={visibleMonth}
                  selected={targetDate ?? today()}
                  onSelect={(date) => {
                    setTargetDate(date);
                    setPickingDate(false);
                  }}
                  onMonthChange={setVisibleMonth}
                  minDate={today()}
                />
                <View className="mt-4">
                  <Button
                    title="No target date"
                    variant="ghost"
                    onPress={() => {
                      setTargetDate(null);
                      setPickingDate(false);
                    }}
                  />
                </View>
              </>
            ) : (
              <>
                <Text className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
                  Goal weight ({unit})
                </Text>
                <TextInput
                  className="h-16 rounded-2xl border border-line bg-ink px-4 text-3xl font-bold text-white"
                  placeholder="—"
                  placeholderTextColor="#3A4552"
                  keyboardType="decimal-pad"
                  returnKeyType="done"
                  value={weight}
                  onChangeText={setWeight}
                  selectTextOnFocus
                />

                <Text className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-muted">
                  Started from ({unit})
                </Text>
                <TextInput
                  className="h-16 rounded-2xl border border-line bg-ink px-4 text-3xl font-bold text-white"
                  placeholder="—"
                  placeholderTextColor="#3A4552"
                  keyboardType="decimal-pad"
                  returnKeyType="done"
                  value={startWeight}
                  onChangeText={setStartWeight}
                  selectTextOnFocus
                />
                <Text className="mt-2 text-xs text-muted">
                  Progress is measured from this. Correct it if it was wrong — that keeps the goal
                  and its history. To measure from today instead, start over below.
                </Text>

                <Pressable
                  className="mt-3 flex-row items-center justify-between rounded-xl border border-line px-4 py-3 active:bg-line"
                  onPress={() => {
                    setVisibleMonth(startOfMonth(targetDate ?? today()));
                    setPickingDate(true);
                  }}
                >
                  <Text className="text-sm text-muted">Target date</Text>
                  <Text className="text-sm font-semibold text-white">
                    {targetDate ? formatLong(targetDate) : 'None'} {'  ▾'}
                  </Text>
                </Pressable>

                <Text className="mt-3 text-xs text-muted">
                  Started at {formatWeight(goal.start_weight_kg, unit)} on{' '}
                  {formatLong(goal.start_date)}. Saving keeps that baseline, so progress already
                  earned is preserved.
                </Text>

                {error ? <Text className="mt-3 text-sm text-danger">{error}</Text> : null}

                <View className="mt-5">
                  <Button title="Save" onPress={save} loading={busy} />
                </View>

                <View className="mt-6 border-t border-line pt-5">
                  {confirmRestart ? (
                    <>
                      <Text className="mb-3 text-sm text-muted">
                        This opens a new goal measured from{' '}
                        {currentKg === null ? 'your latest weight' : formatWeight(currentKg, unit)}.
                        Progress resets to 0%.
                      </Text>
                      <View className="flex-row gap-3">
                        <View className="flex-1">
                          <Button
                            title="Cancel"
                            variant="ghost"
                            onPress={() => setConfirmRestart(false)}
                          />
                        </View>
                        <View className="flex-1">
                          <Button title="Start over" onPress={restart} loading={busy} />
                        </View>
                      </View>
                    </>
                  ) : (
                    <>
                      <Text className="mb-3 text-xs text-muted">
                        Baseline wrong? Re-anchor the goal to your latest weight.
                      </Text>
                      <Button
                        title="Start over from today"
                        variant="ghost"
                        onPress={() => setConfirmRestart(true)}
                      />
                    </>
                  )}
                </View>
              </>
            )}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
