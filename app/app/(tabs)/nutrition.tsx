import { Text } from 'react-native';

import { Card } from '@/components/Card';
import { Screen } from '@/components/Screen';

export default function Nutrition() {
  return (
    <Screen title="Nutrition" subtitle="Calories and macros">
      <Card title="Arrives in Phase 3">
        <Text className="text-sm text-muted">
          Four numeric fields prefilled from yesterday, a \Same
        </Text>
      </Card>
    </Screen>
  );
}
