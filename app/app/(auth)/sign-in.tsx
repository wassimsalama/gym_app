import { Link } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { signIn } from '@/lib/auth';

export default function SignIn() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit() {
    setBusy(true);
    setError(null);
    const { error: authError } = await signIn(email, password);
    if (authError) setError(authError.message);
    setBusy(false);
    // On success the auth listener in useAuth swaps the navigator; no push needed.
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
        <TextInput
          className="h-14 rounded-2xl border border-line bg-surface px-4 text-base text-white"
          placeholder="Password"
          placeholderTextColor="#8A97A6"
          autoCapitalize="none"
          autoComplete="current-password"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={onSubmit}
        />

        {error ? <Text className="text-sm text-danger">{error}</Text> : null}

        <Button title="Sign in" onPress={onSubmit} loading={busy} disabled={!email || !password} />

        <Link href="/(auth)/sign-up" asChild>
          <Text className="mt-2 text-center text-sm text-muted">
            No account yet? <Text className="text-accent">Create one</Text>
          </Text>
        </Link>
      </View>
    </KeyboardAvoidingView>
  );
}
