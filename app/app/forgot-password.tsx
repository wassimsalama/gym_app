import { Link } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { requestPasswordReset } from '@/lib/auth';

export default function ForgotPassword() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);

    const { error: failure } = await requestPasswordReset(email);
    // A failure here is a transport problem, not "no such account" — Supabase
    // deliberately does not reveal which addresses are registered.
    if (failure) setError(failure.message);
    else setSent(true);

    setBusy(false);
  }

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-ink"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ paddingTop: insets.top }}
    >
      <View className="flex-1 justify-center gap-4 px-6">
        <View className="mb-2">
          <Text className="text-3xl font-bold text-white">Reset your password</Text>
          <Text className="mt-2 text-base text-muted">
            {sent
              ? 'If that address has an account, a link is on its way.'
              : 'We will email you a link to set a new one.'}
          </Text>
        </View>

        {sent ? (
          <>
            <Text className="text-sm text-muted">
              The link is good for one use and expires after an hour. Check spam if it has not
              arrived in a few minutes.
            </Text>
            <Button title="Send it again" variant="ghost" onPress={() => setSent(false)} />
          </>
        ) : (
          <>
            <TextInput
              className="h-14 rounded-2xl border border-line bg-surface px-4 text-base text-white"
              placeholder="Email"
              placeholderTextColor="#8A97A6"
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              value={email}
              onChangeText={setEmail}
              onSubmitEditing={submit}
              autoFocus
            />

            {error ? <Text className="text-sm text-danger">{error}</Text> : null}

            <Button title="Send reset link" onPress={submit} loading={busy} disabled={!email} />
          </>
        )}

        <Link href="/(auth)/sign-in" asChild>
          <Text className="mt-2 text-center text-sm text-accent">Back to sign in</Text>
        </Link>
      </View>
    </KeyboardAvoidingView>
  );
}
