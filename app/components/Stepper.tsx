import { Pressable, Text, TextInput, View } from 'react-native';

type Props = {
  label: string;
  /** Displayed value, already in the user's unit. */
  value: string;
  onChange: (next: string) => void;
  onStep: (direction: 1 | -1) => void;
  keyboardType?: 'decimal-pad' | 'number-pad';
  width?: number;
};

/**
 * Number field with +/- either side.
 *
 * The steppers carry the interaction budget: §2.3 wants an unchanged session
 * logged in about three taps, and nudging a lift by one plate should never
 * mean opening a keyboard. The field stays editable for the times it does.
 */
export function Stepper({
  label,
  value,
  onChange,
  onStep,
  keyboardType = 'decimal-pad',
  width = 96,
}: Props) {
  return (
    <View className="items-center gap-1">
      <Text className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</Text>
      <View className="flex-row items-center">
        <Pressable
          className="h-11 w-9 items-center justify-center rounded-l-xl border border-line bg-surface active:bg-line"
          onPress={() => onStep(-1)}
          accessibilityLabel={`Decrease ${label}`}
        >
          <Text className="text-lg font-bold text-muted">−</Text>
        </Pressable>

        <TextInput
          className="h-11 border-y border-line bg-ink text-center text-base font-bold text-white"
          style={{ width }}
          value={value}
          onChangeText={onChange}
          keyboardType={keyboardType}
          returnKeyType="done"
          selectTextOnFocus
          accessibilityLabel={label}
        />

        <Pressable
          className="h-11 w-9 items-center justify-center rounded-r-xl border border-line bg-surface active:bg-line"
          onPress={() => onStep(1)}
          accessibilityLabel={`Increase ${label}`}
        >
          <Text className="text-lg font-bold text-muted">+</Text>
        </Pressable>
      </View>
    </View>
  );
}
