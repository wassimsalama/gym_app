import { useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { PasswordInput } from '@/components/PasswordInput';
import { updatePassword, useAuth } from '@/lib/auth';

const MIN_LENGTH = 6;

/**
 * Where the emailed reset link lands.
 *
 * Supabase exchanges the link's token for a real session before this renders,
 * so setting the password is an ordinary authenticated update. If there is no
 * session, the link was already used or has expired — say so rather than
 * showing a form that cannot work.
 */
export default function ResetPassword() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { session, loading } = useAuth();

  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirmation.length > 0 && password !== confirmation;

  async function submit() {
    if (password !== confirmation) {
      setError('The two passwords do not match');
      return;
    }

    setBusy(true);
    setError(null);

    const { error: failure } = await updatePassword(password);
    if (failure) {
      setError(failure.message);
      setBusy(false);
      return;
    }

    router.replace('/(tabs)');
  }

  if (loading) return null;

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-ink"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ paddingTop: insets.top }}
    >
      <View className="flex-1 justify-center gap-4 px-6">
        <View className="mb-2">
          <Text className="text-3xl font-bold text-white">Choose a new password</Text>
          <Text className="mt-2 text-base text-muted">
            {session
              ? `At least ${MIN_LENGTH} characters.`
              : 'This link has expired or has already been used.'}
          </Text>
        </View>

        {session ? (
          <>
            <PasswordInput
              placeholder="New password"
              autoComplete="new-password"
              value={password}
              onChangeText={setPassword}
              autoFocus
            />
            <PasswordInput
              placeholder="Repeat it"
              autoComplete="new-password"
              value={confirmation}
              onChangeText={setConfirmation}
              onSubmitEditing={submit}
            />

            {mismatch ? <Text className="text-sm text-muted">Those do not match yet.</Text> : null}
            {error ? <Text className="text-sm text-danger">{error}</Text> : null}

            <Button
              title="Save new password"
              onPress={submit}
              loading={busy}
              disabled={password.length < MIN_LENGTH || mismatch}
            />
          </>
        ) : (
          <Button title="Request a new link" onPress={() => router.replace('/forgot-password')} />
        )}
      </View>
    </KeyboardAvoidingView>
  );
}
