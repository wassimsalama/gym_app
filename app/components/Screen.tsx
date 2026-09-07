import type { ReactNode } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

type Props = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  scroll?: boolean;
};

export function Screen({ title, subtitle, children, scroll = true }: Props) {
  const insets = useSafeAreaInsets();
  const Body = scroll ? ScrollView : View;

  return (
    <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
      <View className="px-5 pb-3 pt-2">
        <Text className="text-2xl font-bold text-white">{title}</Text>
        {subtitle ? <Text className="mt-1 text-sm text-muted">{subtitle}</Text> : null}
      </View>
      <Body className="flex-1 px-5" contentContainerClassName={scroll ? 'gap-4 pb-10' : undefined}>
        {children}
      </Body>
    </View>
  );
}
