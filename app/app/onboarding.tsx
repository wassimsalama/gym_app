import { useRouter } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { ApiError, createGoal, putDailyLog } from '@/lib/api';
import { today } from '@/lib/dates';
import { useUnit } from '@/lib/profile';
import { parseWeightInput, type Unit } from '@/lib/units';

/**
 * First launch (spec §2.6).
 *
 * The app must not look empty on day one, so this collects the two numbers
 * everything else derives from. Order matters: the weight is written first
 * because the goal takes its starting point from the log (§2.6).
 */
export default function Onboarding() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const unit: Unit = useUnit();
  const goalInput = useRef<TextInput>(null);

  const [current, setCurrent] = useState('');
  const [goal, setGoal] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = useCallback(async () => {
    const currentKg = parseWeightInput(current, unit);
    const goalKg = parseWeightInput(goal, unit);

    if (currentKg === null) {
      setError('Enter your current weight');
      return;
    }
    if (goalKg === null) {
      setError('Enter a goal weight');
      return;
    }

    setBusy(true);
    setError(null);
    try {
      // Weight first — the goal reads its start weight back from this log.
      await putDailyLog(today(), { weight_kg: currentKg });
      await createGoal(goalKg);
      router.replace('/(tabs)');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not save. Try again.');
      setBusy(false);
    }
  }, [current, goal, unit, router]);

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-ink"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ paddingTop: insets.top }}
    >
      <ScrollView
        className="flex-1 px-6"
        contentContainerClassName="flex-1 justify-center gap-5"
        keyboardShouldPersistTaps="handled"
      >
        <View>
          <Text className="text-3xl font-bold text-white">Two numbers</Text>
          <Text className="mt-2 text-base text-muted">
            Where you are and where you&apos;re going. Everything else the app derives.
          </Text>
        </View>

        <View className="gap-2">
          <Text className="text-xs font-semibold uppercase tracking-wider text-muted">
            Current weight ({unit})
          </Text>
          <TextInput
            className="h-16 rounded-2xl border border-line bg-surface px-4 text-3xl font-bold text-white"
            placeholder="—"
            placeholderTextColor="#3A4552"
            keyboardType="decimal-pad"
            returnKeyType="next"
            value={current}
            onChangeText={setCurrent}
            onSubmitEditing={() => goalInput.current?.focus()}
            autoFocus
          />
        </View>

        <View className="gap-2">
          <Text className="text-xs font-semibold uppercase tracking-wider text-muted">
            Goal weight ({unit})
          </Text>
          <TextInput
            ref={goalInput}
            className="h-16 rounded-2xl border border-line bg-surface px-4 text-3xl font-bold text-white"
            placeholder="—"
            placeholderTextColor="#3A4552"
            keyboardType="decimal-pad"
            returnKeyType="done"
            value={goal}
            onChangeText={setGoal}
            onSubmitEditing={submit}
          />
        </View>

        {error ? <Text className="text-sm text-danger">{error}</Text> : null}

        <Button title="Start" onPress={submit} loading={busy} disabled={!current || !goal} />

        <Text className="text-center text-xs text-muted">
          A target date is optional and can be set later.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
