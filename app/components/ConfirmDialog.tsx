import { Modal, Pressable, Text, View } from 'react-native';

import { Button } from '@/components/Button';

/**
 * A confirmation the user actually sees, on every platform.
 *
 * Replaces `Alert.alert`, which is not implemented in react-native-web — its
 * whole body is `static alert() {}`. Calling it on the web does nothing at all:
 * no dialog, no callback, no error. Deleting a photo, discarding a session and
 * confirming account deletion were all wired to it, so all three silently did
 * nothing in the browser while looking correct in the source.
 *
 * Rendered rather than imperative for that reason. An imperative helper would
 * have the same shape as the thing that failed, and the failure mode was that
 * nothing rendered.
 */
export function ConfirmDialog({
  visible,
  title,
  message,
  confirmLabel,
  cancelLabel = 'Cancel',
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  visible: boolean;
  title: string;
  message?: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      {/* Tapping the backdrop cancels, matching what a native alert does. */}
      <Pressable className="flex-1 items-center justify-center bg-black/70 px-6" onPress={onCancel}>
        {/* Swallows taps so a press inside the card does not dismiss it. */}
        <Pressable
          className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5"
          onPress={() => {}}
        >
          <Text className="text-lg font-bold text-white">{title}</Text>
          {message ? <Text className="mt-2 text-sm text-muted">{message}</Text> : null}

          <View className="mt-5 gap-3">
            <Button
              title={confirmLabel}
              onPress={onConfirm}
              loading={busy}
              variant={destructive ? 'danger' : 'primary'}
            />
            <Button title={cancelLabel} variant="ghost" onPress={onCancel} disabled={busy} />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
