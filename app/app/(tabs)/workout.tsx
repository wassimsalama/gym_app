import { Text } from 'react-native';

import { Card } from '@/components/Card';
import { Screen } from '@/components/Screen';

export default function Workout() {
  return (
    <Screen title="Workout" subtitle="Sessions, sets and PRs">
      <Card title="Arrives in Phase 2">
        <Text className="text-sm text-muted">
          Pick a split, search the 876 seeded exercises, and get last-session sets prefilled with
          plate steppers — an unchanged session is about three taps. Saving returns any PRs by Epley
          e1RM.
        </Text>
      </Card>
    </Screen>
  );
}
