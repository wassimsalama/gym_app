import { Pressable, Text, View } from 'react-native';

type Props<T extends string> = {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  /** Values with no data behind them are shown but not selectable. */
  disabledValues?: readonly T[];
};

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  disabledValues = [],
}: Props<T>) {
  return (
    <View className="flex-row rounded-xl border border-line bg-ink p-1">
      {options.map((option) => {
        const selected = option.value === value;
        const disabled = disabledValues.includes(option.value);

        return (
          <Pressable
            key={option.value}
            className={`flex-1 items-center justify-center rounded-lg py-2 ${
              selected ? 'bg-line' : ''
            } ${disabled ? 'opacity-30' : ''}`}
            disabled={disabled}
            onPress={() => onChange(option.value)}
            accessibilityRole="button"
            accessibilityState={{ selected, disabled }}
          >
            <Text
              className={`text-sm ${selected ? 'font-bold text-white' : 'font-medium text-muted'}`}
            >
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}
