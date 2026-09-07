import { Text, View } from 'react-native';

type Suggestion = {
  id: string;
  kind: 'plateau' | 'tdee_update' | 'volume_gap' | 'goal_projection' | 'logging_nudge';
  message: string;
};

/** A short label so the user can see at a glance what kind of thing this is. */
const LABELS: Record<Suggestion['kind'], string> = {
  plateau: 'Stalled lift',
  tdee_update: 'Maintenance',
  volume_gap: 'Volume gap',
  goal_projection: 'Goal pace',
  logging_nudge: 'Thin data',
};

/**
 * The engine's output, rendered plainly (spec §7.5).
 *
 * The copy already carries its own numbers, so there is nothing to dress up
 * here — and deliberately no praise, no emoji and no exclamation marks. An app
 * that congratulates you for opening it teaches you to ignore everything it
 * says.
 */
export function SuggestionCard({ suggestions }: { suggestions: Suggestion[] }) {
  if (suggestions.length === 0) return null;

  return (
    <View className="rounded-2xl border border-line bg-surface p-4">
      <Text className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">
        What your data says
      </Text>

      {suggestions.map((suggestion, index) => (
        <View
          key={suggestion.id}
          className={index > 0 ? 'mt-4 border-t border-line pt-4' : undefined}
        >
          <Text className="mb-1 text-xs font-semibold uppercase tracking-wider text-accent">
            {LABELS[suggestion.kind]}
          </Text>
          <Text className="text-sm leading-5 text-white">{suggestion.message}</Text>
        </View>
      ))}
    </View>
  );
}
