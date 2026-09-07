import type { ReactNode } from 'react';
import { Text, View } from 'react-native';

type Props = {
  title?: string;
  footnote?: string;
  children: ReactNode;
};

export function Card({ title, footnote, children }: Props) {
  return (
    <View className="rounded-2xl border border-line bg-surface p-4">
      {title ? (
        <Text className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
          {title}
        </Text>
      ) : null}
      {children}
      {footnote ? <Text className="mt-3 text-xs text-muted">{footnote}</Text> : null}
    </View>
  );
}
