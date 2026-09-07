import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { PasswordInput } from '@/components/PasswordInput';
import { signIn } from '@/lib/auth';
import { describeWait, recordFailure, recordSuccess, secondsRemaining } from '@/lib/loginThrottle';

export default function SignIn() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lockedFor, setLockedFor] = useState(0);

  const isLocked = lockedFor > 0;

  // Count the lockout down so the button re-enables on its own, rather than
  // leaving someone staring at a dead form wondering if it is broken. The
  // effect depends only on *whether* a lockout is running, not its value, so
  // the interval is created once rather than restarted every second.
  useEffect(() => {
    if (!isLocked) return;

    const timer = setInterval(() => {
      setLockedFor((current) => {
        const next = current - 1;
        if (next <= 0) {
          setError(null);
          return 0;
        }
        return next;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isLocked]);

  async function onSubmit() {
    const wait = secondsRemaining(email);
    if (wait > 0) {
      setLockedFor(wait);
      return;
    }

    setBusy(true);
    setError(null);

    const { error: authError } = await signIn(email, password);

    if (authError) {
      const next = recordFailure(email);
      setLockedFor(next);
      setError(
        next > 0 ? `Too many attempts. Try again in ${describeWait(next)}.` : authError.message,
      );
    } else {
      recordSuccess(email);
      // The auth listener in useAuth swaps the navigator; no push needed.
    }

    setBusy(false);
  }

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-ink"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ paddingTop: insets.top }}
    >
      <View className="flex-1 justify-center gap-4 px-6">
        <View className="mb-4">
          <Text className="text-3xl font-bold text-white">Gym App</Text>
          <Text className="mt-2 text-base text-muted">Weight, macros and lifts in one place.</Text>
        </View>

        <TextInput
          className="h-14 rounded-2xl border border-line bg-surface px-4 text-base text-white"
          placeholder="Email"
          placeholderTextColor="#8A97A6"
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
        />
        <PasswordInput
          autoComplete="current-password"
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={onSubmit}
        />

        <Link href="/forgot-password" asChild>
          <Text className="-mt-1 text-right text-sm text-muted">Forgotten your password?</Text>
        </Link>

        {error ? <Text className="text-sm text-danger">{error}</Text> : null}

        <Button
          title={isLocked ? `Wait ${describeWait(lockedFor)}` : 'Sign in'}
          onPress={onSubmit}
          loading={busy}
          disabled={!email || !password || isLocked}
        />

        <Link href="/(auth)/sign-up" asChild>
          <Text className="mt-2 text-center text-sm text-muted">
            No account yet? <Text className="text-accent">Create one</Text>
          </Text>
        </Link>
      </View>
    </KeyboardAvoidingView>
  );
}
