import { useState } from 'react';
import { Pressable, Text, TextInput, View, type TextInputProps } from 'react-native';

type Props = Omit<TextInputProps, 'secureTextEntry'> & {
  placeholder?: string;
};

/**
 * A password field you can unmask.
 *
 * Typing a password blind on a phone keyboard is how people end up locked out
 * of their own account, and a reveal toggle costs nothing — the field is masked
 * by default, and showing it is the user's deliberate choice.
 */
export function PasswordInput({ placeholder = 'Password', ...rest }: Props) {
  const [visible, setVisible] = useState(false);

  return (
    <View className="relative">
      <TextInput
        className="h-14 rounded-2xl border border-line bg-surface px-4 pr-16 text-base text-white"
        placeholder={placeholder}
        placeholderTextColor="#8A97A6"
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry={!visible}
        {...rest}
      />
      <Pressable
        className="absolute right-0 top-0 h-14 justify-center px-4"
        onPress={() => setVisible((current) => !current)}
        accessibilityRole="button"
        accessibilityLabel={visible ? 'Hide password' : 'Show password'}
      >
        <Text className="text-sm font-semibold text-muted">{visible ? 'Hide' : 'Show'}</Text>
      </Pressable>
    </View>
  );
}
