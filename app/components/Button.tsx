import { ActivityIndicator, Pressable, Text, type PressableProps } from 'react-native';

type Props = PressableProps & {
  title: string;
  variant?: 'primary' | 'ghost' | 'danger';
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
      : variant === 'danger'
        ? isDisabled
          ? 'bg-danger/40'
          : 'bg-danger active:bg-danger/80'
        : 'border border-line active:bg-surface';

  return (
    <Pressable className={`${base} ${look}`} disabled={isDisabled} {...rest}>
      {loading ? (
        <ActivityIndicator color={variant === 'ghost' ? '#8A97A6' : '#0B0F14'} />
      ) : (
        <Text
          className={`text-base font-semibold ${variant === 'ghost' ? 'text-muted' : 'text-ink'}`}
        >
          {title}
        </Text>
      )}
    </Pressable>
  );
}
