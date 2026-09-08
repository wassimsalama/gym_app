import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { ApiError, createExercise, searchExercises, type Exercise } from '@/lib/api';
import { MUSCLE_GROUPS, type MuscleGroup } from '@/lib/muscleGroups';

type Props = {
  onPick: (exercise: Exercise) => void;
  onClose: () => void;
};

/**
 * Search over the catalogue, with a fallback to creating what is missing
 * (spec §2.3). Creating requires connectivity because the session needs the
 * generated id to hang sets from — existing exercises log fine offline.
 */
export function ExerciseSearch({ onPick, onClose }: Props) {
  const insets = useSafeAreaInsets();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Exercise[]>([]);
  const [searching, setSearching] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [creating, setCreating] = useState(false);
  const [newGroup, setNewGroup] = useState<MuscleGroup>('chest');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    // Debounced so a fast typist does not fire a request per keystroke.
    const timer = setTimeout(() => {
      searchExercises(query)
        .then((found) => {
          if (active) setResults(found);
        })
        .catch((err: unknown) => {
          if (active) {
            setError(err instanceof ApiError ? err.detail : 'Could not search exercises');
          }
        })
        .finally(() => {
          if (active) setSearching(false);
        });
    }, 200);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query]);

  async function create() {
    const name = query.trim();
    if (!name) return;

    setSaving(true);
    setError(null);
    try {
      onPick(await createExercise({ name, muscle_group: newGroup }));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 0
          ? 'Creating an exercise needs a connection. Existing ones work offline.'
          : err instanceof ApiError
            ? err.detail
            : 'Could not create the exercise',
      );
      setSaving(false);
    }
  }

  return (
    <Modal visible animationType="slide" onRequestClose={onClose}>
      <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
        <View className="flex-row items-center gap-3 px-5 pb-3 pt-2">
          <TextInput
            className="h-12 min-w-0 flex-1 rounded-xl border border-line bg-surface px-4 text-base text-white"
            placeholder="Search exercises"
            placeholderTextColor="#8A97A6"
            value={query}
            onChangeText={(text) => {
              setQuery(text);
              setSearching(true);
              setCreating(false);
            }}
            autoFocus
            autoCorrect={false}
            returnKeyType="search"
          />
          <Pressable onPress={onClose}>
            <Text className="text-sm font-semibold text-muted">Close</Text>
          </Pressable>
        </View>

        <ScrollView className="flex-1 px-5" keyboardShouldPersistTaps="handled">
          {error ? <Text className="mb-3 text-sm text-danger">{error}</Text> : null}

          {searching ? (
            <View className="py-8">
              <ActivityIndicator color="#4ADE80" />
            </View>
          ) : (
            results.map((exercise) => (
              <Pressable
                key={exercise.id}
                className="border-b border-line py-4 active:bg-surface"
                onPress={() => onPick(exercise)}
              >
                <Text className="text-base text-white">{exercise.name}</Text>
                <Text className="mt-0.5 text-xs text-muted">
                  {exercise.muscle_group}
                  {exercise.equipment ? ` · ${exercise.equipment}` : ''}
                  {exercise.source === 'custom' ? ' · yours' : ''}
                </Text>
              </Pressable>
            ))
          )}

          {!searching && results.length === 0 && query.trim() ? (
            <View className="py-6">
              <Text className="text-sm text-muted">Nothing matches “{query.trim()}”.</Text>

              {creating ? (
                <View className="mt-4">
                  <Text className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
                    Muscle group
                  </Text>
                  <View className="flex-row flex-wrap gap-2">
                    {MUSCLE_GROUPS.map((group) => (
                      <Pressable
                        key={group}
                        className={`rounded-full border px-3 py-2 ${
                          group === newGroup ? 'border-accent bg-accent' : 'border-line'
                        }`}
                        onPress={() => setNewGroup(group)}
                      >
                        <Text
                          className={`text-xs font-semibold ${
                            group === newGroup ? 'text-ink' : 'text-muted'
                          }`}
                        >
                          {group}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                  <View className="mt-4">
                    <Button title={`Create “${query.trim()}”`} onPress={create} loading={saving} />
                  </View>
                </View>
              ) : (
                <View className="mt-4">
                  <Button title="Create it" variant="ghost" onPress={() => setCreating(true)} />
                </View>
              )}
            </View>
          ) : null}
        </ScrollView>
      </View>
    </Modal>
  );
}
