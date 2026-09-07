import { Text } from 'react-native';

import { Card } from '@/components/Card';
import { Screen } from '@/components/Screen';

export default function Photos() {
  return (
    <Screen title="Photos" subtitle="Progress over time">
      <Card title="Arrives in Phase 4">
        <Text className="text-sm text-muted">
          A month calendar of thumbnails and a two-date compare slider. Photos are private: a locked
          S3 bucket with short-lived presigned URLs in both directions.
        </Text>
      </Card>
    </Screen>
  );
}
