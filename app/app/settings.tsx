import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  Alert,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { SegmentedControl } from '@/components/SegmentedControl';
import { PasswordInput } from '@/components/PasswordInput';
import { deleteAccount } from '@/lib/api';
import { signOut, supabase, updatePassword, useAuth } from '@/lib/auth';
import { setUnit, useUnit } from '@/lib/profile';
import type { Unit } from '@/lib/units';
import { clearCache } from '@/lib/cache';
import { describeError, type DisplayError } from '@/lib/errors';
import { clearQueue } from '@/lib/sync';

const CONFIRMATION = 'DELETE';

const UNIT_OPTIONS = [
  { value: 'lb' as const, label: 'Pounds (lb)' },
  { value: 'kg' as const, label: 'Kilograms (kg)' },
];

export default function Settings() {
  const unit = useUnit();
  const [unitError, setUnitError] = useState<string | null>(null);
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { session } = useAuth();

  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);

  const [changingPassword, setChangingPassword] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [repeated, setRepeated] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);
  const [changed, setChanged] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [error, setError] = useState<DisplayError | null>(null);

  async function changePassword() {
    if (newPassword !== repeated) {
      setPasswordError('The two passwords do not match');
      return;
    }

    setSavingPassword(true);
    setPasswordError(null);

    const { error: failure } = await updatePassword(newPassword);
    if (failure) {
      setPasswordError(failure.message);
    } else {
      setChanged(true);
      setChangingPassword(false);
      setNewPassword('');
      setRepeated('');
    }
    setSavingPassword(false);
  }

  function openPrivacy() {
    // The page ships inside the web build, so on the web it is a relative path
    // and needs no host of its own. A native build has no such document, so it
    // points at the deployed site.
    const native = process.env.EXPO_PUBLIC_PRIVACY_URL;
    void Linking.openURL(Platform.OS === 'web' ? '/privacy.html' : (native ?? '/privacy.html'));
  }

  /**
   * Account deletion (spec §10, §13).
   *
   * App Store review requires this to be reachable in-app and to actually
   * delete. The order matters: server data first, then local state, then the
   * session — signing out first would throw away the token the delete needs.
   */
  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await deleteAccount();

      // Local traces of a deleted account should not survive on the device.
      await clearQueue();
      await clearCache();
      await supabase.auth.signOut();

      Alert.alert(
        'Account deleted',
        'Your data has been removed. Deleting the sign-in itself is handled by ' +
          'Supabase and may take a moment to disappear everywhere.',
      );
      router.replace('/(auth)/sign-in');
    } catch (err) {
      setError(describeError(err, 'Could not delete your account'));
      setBusy(false);
    }
  }

  return (
    <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
      <View className="flex-row items-center justify-between px-5 pb-3 pt-2">
        <Text className="text-2xl font-bold text-white">Settings</Text>
        <Pressable onPress={() => router.back()}>
          <Text className="text-sm font-semibold text-muted">Done</Text>
        </Pressable>
      </View>

      <ScrollView className="flex-1 px-5" contentContainerClassName="gap-4 pb-10">
        <Card title="Account">
          <Text className="text-base text-white">{session?.user.email ?? '—'}</Text>
          <View className="mt-4">
            <Button title="Sign out" variant="ghost" onPress={() => void signOut()} />
          </View>
        </Card>

        <Card
          title="Units"
          footnote="Only changes what you see. Everything is stored in kilograms."
        >
          <SegmentedControl<Unit>
            options={UNIT_OPTIONS}
            value={unit}
            onChange={(next) => {
              setUnitError(null);
              void setUnit(next).catch(() =>
                setUnitError('Could not save that. Check your connection and try again.'),
              );
            }}
          />
          {unitError ? <Text className="mt-3 text-sm text-danger">{unitError}</Text> : null}
        </Card>

        <Card title="Password">
          {changed ? <Text className="mb-3 text-sm text-accent">Password updated.</Text> : null}
          {passwordError ? <Text className="mb-3 text-sm text-danger">{passwordError}</Text> : null}

          {changingPassword ? (
            <>
              <View className="gap-3">
                <PasswordInput
                  placeholder="New password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChangeText={setNewPassword}
                />
                <PasswordInput
                  placeholder="Repeat it"
                  autoComplete="new-password"
                  value={repeated}
                  onChangeText={setRepeated}
                />
              </View>
              <View className="mt-4 gap-2">
                <Button
                  title="Save"
                  onPress={changePassword}
                  loading={savingPassword}
                  disabled={newPassword.length < 6 || newPassword !== repeated}
                />
                <Button
                  title="Cancel"
                  variant="ghost"
                  onPress={() => {
                    setChangingPassword(false);
                    setNewPassword('');
                    setRepeated('');
                    setPasswordError(null);
                  }}
                />
              </View>
            </>
          ) : (
            <Button
              title="Change password"
              variant="ghost"
              onPress={() => {
                setChangingPassword(true);
                setChanged(false);
              }}
            />
          )}
        </Card>

        <Card title="Privacy">
          <Text className="text-sm text-muted">
            Everything stored is something you typed in. Photos live in private storage, reachable
            only through short-lived links generated for your device. There is no advertising, no
            tracking and no analytics SDK, and nothing is shared.
          </Text>
          <View className="mt-4">
            <Button title="Read the privacy policy" variant="ghost" onPress={openPrivacy} />
          </View>
        </Card>

        <Card title="Stored on this device">
          <Text className="text-sm text-muted">
            This app sets no cookies. It keeps your sign-in session and the last screen you loaded
            in local storage, and anything you log while offline in a local database until it can be
            sent. Both are needed for the app to work, neither is used to track you, and signing out
            clears them.
          </Text>
        </Card>

        <Card title="Delete account">
          {error ? <Text className="mb-3 text-sm text-danger">{error.detail}</Text> : null}

          {confirming ? (
            <>
              <Text className="mb-3 text-sm text-muted">
                This permanently removes your weight history, workouts, nutrition logs, goals and
                photos. It cannot be undone. Type {CONFIRMATION} to confirm.
              </Text>
              <TextInput
                className="h-14 rounded-2xl border border-danger bg-ink px-4 text-lg font-bold text-white"
                placeholder={CONFIRMATION}
                placeholderTextColor="#3A4552"
                autoCapitalize="characters"
                autoCorrect={false}
                value={typed}
                onChangeText={setTyped}
              />
              <View className="mt-4 gap-2">
                <Button
                  title="Delete everything"
                  onPress={remove}
                  loading={busy}
                  disabled={typed !== CONFIRMATION}
                />
                <Button
                  title="Cancel"
                  variant="ghost"
                  onPress={() => {
                    setConfirming(false);
                    setTyped('');
                  }}
                />
              </View>
            </>
          ) : (
            <>
              <Text className="mb-4 text-sm text-muted">
                Removes everything you have logged, permanently.
              </Text>
              <Button
                title="Delete my account"
                variant="ghost"
                onPress={() => setConfirming(true)}
              />
            </>
          )}
        </Card>
      </ScrollView>
    </View>
  );
}
