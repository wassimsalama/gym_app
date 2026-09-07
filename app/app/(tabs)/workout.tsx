import * as Crypto from 'expo-crypto';
import { useCallback, useState } from 'react';
import { Alert, Pressable, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { ExerciseSearch } from '@/components/ExerciseSearch';
import { Stepper } from '@/components/Stepper';
import { SyncBadge } from '@/components/SyncBadge';
import {
  ApiError,
  getLastSets,
  putDailyLog,
  saveSession,
  type Exercise,
  type PersonalRecord,
  type SetInput,
  type Split,
} from '@/lib/api';
import { formatLong, today } from '@/lib/dates';
import { useUnit } from '@/lib/profile';
import {
  formatWeight,
  fromKg,
  parseReps,
  parseWeightInput,
  stepKg,
  stepReps,
  WEIGHT_STEP,
  type Unit,
} from '@/lib/units';

const SPLITS: Split[] = ['push', 'pull', 'legs', 'upper', 'lower', 'full', 'other'];

/** One set in the builder, held as display strings so typing is unimpeded. */
type DraftSet = { weight: string; reps: string };

type DraftExercise = {
  exercise: Exercise;
  sets: DraftSet[];
  /** Date the prefilled numbers came from, if any. */
  prefilledFrom: string | null;
};

function blankSet(unit: Unit): DraftSet {
  return { weight: unit === 'kg' ? '20' : '45', reps: '8' };
}

export default function Workout() {
  const insets = useSafeAreaInsets();
  const unit = useUnit();

  const [split, setSplit] = useState<Split | null>(null);
  const [exercises, setExercises] = useState<DraftExercise[]>([]);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prs, setPrs] = useState<PersonalRecord[] | null>(null);
  const [savedOffline, setSavedOffline] = useState(false);

  const started = split !== null;

  /**
   * Adding an exercise pulls last session's sets and pre-populates them — the
   * behaviour §2.3 calls the killer UX. Logging an unchanged session then costs
   * a handful of taps rather than a dozen keyboard entries.
   */
  const addExercise = useCallback(
    async (exercise: Exercise) => {
      setSearching(false);
      setError(null);

      let sets: DraftSet[] = [blankSet(unit)];
      let prefilledFrom: string | null = null;

      try {
        const last = await getLastSets(exercise.id);
        if (last.sets.length > 0) {
          sets = last.sets.map((s) => ({
            weight: fromKg(s.weight_kg, unit).toFixed(1).replace(/\.0$/, ''),
            reps: String(s.reps),
          }));
          prefilledFrom = last.session_date;
        }
      } catch {
        // Offline: a blank set is a fine starting point, and the session still
        // saves through the queue.
      }

      setExercises((current) => [...current, { exercise, sets, prefilledFrom }]);
    },
    [unit],
  );

  const mutateSet = useCallback(
    (exerciseIndex: number, setIndex: number, patch: Partial<DraftSet>) => {
      setExercises((current) =>
        current.map((entry, i) =>
          i !== exerciseIndex
            ? entry
            : {
                ...entry,
                sets: entry.sets.map((s, j) => (j === setIndex ? { ...s, ...patch } : s)),
              },
        ),
      );
    },
    [],
  );

  const addSet = useCallback(
    (exerciseIndex: number) => {
      setExercises((current) =>
        current.map((entry, i) =>
          i !== exerciseIndex
            ? entry
            : {
                ...entry,
                sets: [...entry.sets, entry.sets[entry.sets.length - 1] ?? blankSet(unit)],
              },
        ),
      );
    },
    [unit],
  );

  const removeSet = useCallback((exerciseIndex: number, setIndex: number) => {
    setExercises((current) =>
      current.map((entry, i) =>
        i !== exerciseIndex
          ? entry
          : { ...entry, sets: entry.sets.filter((_, j) => j !== setIndex) },
      ),
    );
  }, []);

  const removeExercise = useCallback((exerciseIndex: number) => {
    setExercises((current) => current.filter((_, i) => i !== exerciseIndex));
  }, []);

  function reset() {
    setSplit(null);
    setExercises([]);
    setError(null);
  }

  /** Save the detailed session. */
  const save = useCallback(async () => {
    if (!split) return;

    const sets: SetInput[] = [];
    for (const entry of exercises) {
      entry.sets.forEach((draft, index) => {
        const weight = parseWeightInput(draft.weight, unit);
        const reps = parseReps(draft.reps);
        // A blank or nonsensical row is dropped rather than blocking the save;
        // the user is standing in a gym, not filling in a form.
        if (weight === null || reps === null) return;
        sets.push({
          exercise_id: entry.exercise.id,
          set_number: index + 1,
          weight_kg: weight,
          reps,
        });
      });
    }

    setSaving(true);
    setError(null);
    setPrs(null);
    setSavedOffline(false);

    try {
      const result = await saveSession({
        // The server's dedupe key: a retried write cannot duplicate the session.
        client_uuid: Crypto.randomUUID(),
        session_date: today(),
        split,
        sets,
      });

      // Keep the streak/volume view honest even for a set-less quick log.
      await putDailyLog(today(), { trained: true, split });

      if (result === null) {
        setSavedOffline(true);
      } else {
        setPrs(result.prs);
      }
      setSplit(null);
      setExercises([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not save the session');
    } finally {
      setSaving(false);
    }
  }, [split, exercises, unit]);

  /** Mark today trained without detailing it (spec §2.3). */
  const quickLog = useCallback(async (chosen: Split) => {
    setSaving(true);
    setError(null);
    setPrs(null);
    setSavedOffline(false);
    try {
      await saveSession({
        client_uuid: Crypto.randomUUID(),
        session_date: today(),
        split: chosen,
        sets: [],
      });
      const queued = await putDailyLog(today(), { trained: true, split: chosen });
      setSavedOffline(queued === null);
      setSplit(null);
      setExercises([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not save');
    } finally {
      setSaving(false);
    }
  }, []);

  function confirmDiscard() {
    Alert.alert('Discard this session?', 'Nothing logged so far will be saved.', [
      { text: 'Keep going', style: 'cancel' },
      { text: 'Discard', style: 'destructive', onPress: reset },
    ]);
  }

  return (
    <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
      <View className="px-5 pb-3 pt-2">
        <View className="flex-row items-center justify-between">
          <Text className="text-2xl font-bold text-white">Workout</Text>
          <SyncBadge />
        </View>
        <Text className="mt-1 text-sm text-muted">{formatLong(today())}</Text>
      </View>

      <ScrollView
        className="flex-1 px-5"
        contentContainerClassName="gap-4 pb-10"
        keyboardShouldPersistTaps="handled"
      >
        {prs && prs.length > 0 ? (
          <Card title="Personal record">
            {prs.map((pr) => (
              <View key={pr.exercise_id} className="mb-2">
                <Text className="text-base font-bold text-accent">{pr.exercise_name}</Text>
                <Text className="mt-0.5 text-sm text-muted">
                  Estimated 1RM {formatWeight(pr.e1rm, unit)}, up from{' '}
                  {formatWeight(pr.previous_e1rm, unit)}.
                </Text>
              </View>
            ))}
          </Card>
        ) : null}

        {prs && prs.length === 0 ? (
          <Card title="Session saved">
            <Text className="text-sm text-muted">
              Logged for {formatLong(today())}. No PRs this time.
            </Text>
          </Card>
        ) : null}

        {savedOffline ? (
          <Card title="Saved offline">
            <Text className="text-sm text-muted">
              Stored on this device and queued. It syncs by itself when you have signal — you can
              close the app.
            </Text>
          </Card>
        ) : null}

        {error ? (
          <Card title="Problem">
            <Text className="text-sm text-danger">{error}</Text>
          </Card>
        ) : null}

        {!started ? (
          <>
            <Card title="Start a session" footnote="Pick the split you are training.">
              <View className="flex-row flex-wrap gap-2">
                {SPLITS.map((option) => (
                  <Pressable
                    key={option}
                    className="rounded-full border border-line px-4 py-3 active:bg-surface"
                    onPress={() => setSplit(option)}
                  >
                    <Text className="text-sm font-semibold capitalize text-white">{option}</Text>
                  </Pressable>
                ))}
              </View>
            </Card>

            <Card
              title="Quick log"
              footnote="For days you trained but will not detail. Feeds streaks and rest-day tracking."
            >
              <View className="flex-row flex-wrap gap-2">
                {SPLITS.map((option) => (
                  <Pressable
                    key={option}
                    className="rounded-full border border-line px-3 py-2 active:bg-surface"
                    disabled={saving}
                    onPress={() => quickLog(option)}
                  >
                    <Text className="text-xs font-semibold capitalize text-muted">{option}</Text>
                  </Pressable>
                ))}
              </View>
            </Card>
          </>
        ) : (
          <>
            <View className="flex-row items-center justify-between">
              <Text className="text-lg font-bold capitalize text-white">{split} day</Text>
              <Pressable onPress={confirmDiscard}>
                <Text className="text-sm font-semibold text-muted">Discard</Text>
              </Pressable>
            </View>

            {exercises.map((entry, exerciseIndex) => (
              <Card key={`${entry.exercise.id}-${exerciseIndex}`} title={entry.exercise.name}>
                {entry.prefilledFrom ? (
                  <Text className="mb-3 text-xs text-muted">
                    Prefilled from {formatLong(entry.prefilledFrom)}. Adjust what changed.
                  </Text>
                ) : (
                  <Text className="mb-3 text-xs text-muted">First time logging this one.</Text>
                )}

                {entry.sets.map((draft, setIndex) => (
                  <View key={setIndex} className="mb-3 flex-row items-end justify-between gap-2">
                    <Text className="mb-3 w-6 text-sm font-semibold text-muted">
                      {setIndex + 1}
                    </Text>

                    <Stepper
                      label={unit}
                      value={draft.weight}
                      keyboardType="decimal-pad"
                      onChange={(next) => mutateSet(exerciseIndex, setIndex, { weight: next })}
                      onStep={(direction) => {
                        const kg = parseWeightInput(draft.weight, unit) ?? 0;
                        const stepped = stepKg(kg, direction, unit);
                        mutateSet(exerciseIndex, setIndex, {
                          weight: fromKg(stepped, unit)
                            .toFixed(2)
                            .replace(/\.?0+$/, ''),
                        });
                      }}
                    />

                    <Stepper
                      label="reps"
                      value={draft.reps}
                      keyboardType="number-pad"
                      width={64}
                      onChange={(next) => mutateSet(exerciseIndex, setIndex, { reps: next })}
                      onStep={(direction) =>
                        mutateSet(exerciseIndex, setIndex, {
                          reps: String(stepReps(parseReps(draft.reps) ?? 8, direction)),
                        })
                      }
                    />

                    <Pressable
                      className="mb-1 h-9 w-9 items-center justify-center rounded-full active:bg-line"
                      onPress={() => removeSet(exerciseIndex, setIndex)}
                      accessibilityLabel={`Remove set ${setIndex + 1}`}
                    >
                      <Text className="text-lg text-muted">×</Text>
                    </Pressable>
                  </View>
                ))}

                <View className="mt-1 flex-row gap-3">
                  <View className="flex-1">
                    <Button title="Add set" variant="ghost" onPress={() => addSet(exerciseIndex)} />
                  </View>
                  <View className="flex-1">
                    <Button
                      title="Remove"
                      variant="ghost"
                      onPress={() => removeExercise(exerciseIndex)}
                    />
                  </View>
                </View>
              </Card>
            ))}

            <Button title="Add exercise" variant="ghost" onPress={() => setSearching(true)} />

            <Button
              title={exercises.length === 0 ? 'Save as trained' : 'Save session'}
              onPress={save}
              loading={saving}
            />

            <Text className="text-center text-xs text-muted">
              Plates step by {WEIGHT_STEP[unit]} {unit}.
            </Text>
          </>
        )}
      </ScrollView>

      {searching ? (
        <ExerciseSearch onPick={addExercise} onClose={() => setSearching(false)} />
      ) : null}
    </View>
  );
}
