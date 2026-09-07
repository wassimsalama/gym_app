import { Link } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { signUp } from '@/lib/auth';

export default function SignUp() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit() {
    setBusy(true);
    setError(null);
    setNotice(null);

    const { data, error: authError } = await signUp(email, password);
    if (authError) {
      setError(authError.message);
    } else if (!data.session) {
      // Supabase is configured to require email confirmation.
      setNotice('Check your email to confirm the address, then sign in.');
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
          <Text className="text-3xl font-bold text-white">Create account</Text>
          <Text className="mt-2 text-base text-muted">Six characters minimum.</Text>
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
        <TextInput
          className="h-14 rounded-2xl border border-line bg-surface px-4 text-base text-white"
          placeholder="Password"
          placeholderTextColor="#8A97A6"
          autoCapitalize="none"
          autoComplete="new-password"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={onSubmit}
        />

        {error ? <Text className="text-sm text-danger">{error}</Text> : null}
        {notice ? <Text className="text-sm text-accent">{notice}</Text> : null}

        <Button
          title="Create account"
          onPress={onSubmit}
          loading={busy}
          disabled={!email || password.length < 6}
        />

        <Link href="/(auth)/sign-in" asChild>
          <Text className="mt-2 text-center text-sm text-muted">
            Already have one? <Text className="text-accent">Sign in</Text>
          </Text>
        </Link>
      </View>
    </KeyboardAvoidingView>
  );
}
