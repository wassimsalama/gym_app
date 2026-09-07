import { ActivityIndicator, Pressable, Text, type PressableProps } from 'react-native';

type Props = PressableProps & {
  title: string;
  variant?: 'primary' | 'ghost';
  loading?: boolean;
};

export function Button({ title, variant = 'primary', loading = false, disabled, ...rest }: Props) {
  const isDisabled = disabled || loading;
  const base = 'h-14 items-center justify-center rounded-2xl px-5';
  const look =
    variant === 'primary'
      ? isDisabled
        ? 'bg-accent/40'
        : 'bg-accent active:bg-accent/80'
      : 'border border-line active:bg-surface';

  return (
    <Pressable className={`${base} ${look}`} disabled={isDisabled} {...rest}>
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? '#0B0F14' : '#8A97A6'} />
      ) : (
        <Text
          className={`text-base font-semibold ${variant === 'primary' ? 'text-ink' : 'text-muted'}`}
        >
          {title}
        </Text>
      )}
    </Pressable>
  );
}
