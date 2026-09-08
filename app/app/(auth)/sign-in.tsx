import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { PasswordInput } from '@/components/PasswordInput';
import { resendConfirmation, signIn } from '@/lib/auth';
import { describeWait, recordFailure, recordSuccess, secondsRemaining } from '@/lib/loginThrottle';

export default function SignIn() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lockedFor, setLockedFor] = useState(0);
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [resent, setResent] = useState(false);

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
    setUnconfirmed(false);
    setResent(false);

    const { error: authError } = await signIn(email, password);

    if (authError) {
      // An unconfirmed address is not a wrong password, and must not be
      // throttled like one — the account is unreachable no matter how many
      // times it is typed correctly, so counting attempts only locks someone
      // out of the screen that offers the actual remedy.
      if (authError.code === 'email_not_confirmed') {
        setUnconfirmed(true);
      } else {
        const next = recordFailure(email);
        setLockedFor(next);
        setError(
          next > 0 ? `Too many attempts. Try again in ${describeWait(next)}.` : authError.message,
        );
      }
    } else {
      recordSuccess(email);
      // The auth listener in useAuth swaps the navigator; no push needed.
    }

    setBusy(false);
  }

  async function resend() {
    setBusy(true);
    const { error: failure } = await resendConfirmation(email);
    setBusy(false);
    if (failure) {
      setError(failure.message);
      return;
    }
    setResent(true);
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

        {unconfirmed ? (
          <View className="gap-3 rounded-2xl border border-line bg-surface p-4">
            <Text className="text-sm text-white">
              This address has not been confirmed yet. Check your inbox for the confirmation email —
              resetting your password will not fix it.
            </Text>
            {resent ? (
              <Text className="text-sm text-accent">
                Sent. If it does not arrive, check your spam folder.
              </Text>
            ) : (
              <Button title="Resend confirmation email" variant="ghost" onPress={resend} />
            )}
          </View>
        ) : null}

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
