import { Text } from 'react-native';

import { Card } from '@/components/Card';
import { Screen } from '@/components/Screen';

export default function Weight() {
  return (
    <Screen title="Weight" subtitle="Daily entry and trend">
      <Card title="Arrives in Phase 1">
        <Text className="text-sm text-muted">
          One pre-focused number field, a chart with faint raw points under a bold 7-day smoothed
          line, and a projected goal date from the current trend.
        </Text>
      </Card>
    </Screen>
  );
}
