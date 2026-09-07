import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { deletePhoto, getPhotos, type Photo } from '@/lib/api';
import {
  addMonths,
  daysInMonth,
  firstWeekdayOfMonth,
  formatLong,
  formatMonth,
  isFuture,
  startOfMonth,
  today,
  type IsoDate,
} from '@/lib/dates';
import { describeError, type DisplayError } from '@/lib/errors';
import { uploadPhoto } from '@/lib/photos';

const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

export default function Photos() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();

  const [month, setMonth] = useState<IsoDate>(startOfMonth());
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<DisplayError | null>(null);

  const [viewing, setViewing] = useState<Photo | null>(null);
  const [comparing, setComparing] = useState(false);
  const [comparison, setComparison] = useState<[Photo | null, Photo | null]>([null, null]);

  const load = useCallback(async (target: IsoDate) => {
    const [year, monthNumber] = target.split('-').map(Number);
    try {
      setPhotos(await getPhotos(year, monthNumber));
      setError(null);
    } catch (err) {
      setError(describeError(err, 'Could not load your photos'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const [year, monthNumber] = month.split('-').map(Number);
    getPhotos(year, monthNumber)
      .then((found) => {
        if (active) setPhotos(found);
      })
      .catch((err: unknown) => {
        if (active) setError(describeError(err, 'Could not load your photos'));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [month]);

  /** One photo per day, keyed by date, for the calendar grid. */
  const byDate = useMemo(() => {
    const map = new Map<IsoDate, Photo>();
    photos.forEach((photo) => {
      if (!map.has(photo.taken_on)) map.set(photo.taken_on, photo);
    });
    return map;
  }, [photos]);

  const cells = useMemo(() => {
    const lead = firstWeekdayOfMonth(month);
    const total = daysInMonth(month);
    const days: (IsoDate | null)[] = Array.from({ length: lead }, () => null);
    for (let i = 0; i < total; i += 1) {
      days.push(`${month.slice(0, 8)}${String(i + 1).padStart(2, '0')}`);
    }
    return days;
  }, [month]);

  const add = useCallback(
    async (from: 'camera' | 'library') => {
      const permission =
        from === 'camera'
          ? await ImagePicker.requestCameraPermissionsAsync()
          : await ImagePicker.requestMediaLibraryPermissionsAsync();

      if (!permission.granted) {
        setError({
          title: 'Permission needed',
          detail:
            from === 'camera'
              ? 'Allow camera access in Settings to take a progress photo.'
              : 'Allow photo access in Settings to pick a progress photo.',
          offline: false,
        });
        return;
      }

      const result =
        from === 'camera'
          ? await ImagePicker.launchCameraAsync({ quality: 1 })
          : await ImagePicker.launchImageLibraryAsync({
              mediaTypes: ['images'],
              quality: 1,
            });

      if (result.canceled) return;

      setBusy(true);
      setError(null);
      try {
        await uploadPhoto(result.assets[0].uri, today());
        await load(month);
      } catch (err) {
        setError(describeError(err, 'Could not upload that photo'));
      } finally {
        setBusy(false);
      }
    },
    [month, load],
  );

  const confirmDelete = useCallback(
    (photo: Photo) => {
      Alert.alert('Delete this photo?', 'It is removed from your account permanently.', [
        { text: 'Keep', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            setViewing(null);
            try {
              await deletePhoto(photo.id);
              await load(month);
            } catch (err) {
              setError(describeError(err, 'Could not delete that photo'));
            }
          },
        },
      ]);
    },
    [month, load],
  );

  function pickForComparison(photo: Photo) {
    setComparison(([first]) => (first === null ? [photo, null] : [first, photo]));
  }

  const cellSize = Math.floor((width - 40 - 6 * 4) / 7);
  const [left, right] = comparison;

  return (
    <View className="flex-1 bg-ink" style={{ paddingTop: insets.top }}>
      <View className="px-5 pb-3 pt-2">
        <Text className="text-2xl font-bold text-white">Photos</Text>
        <Text className="mt-1 text-sm text-muted">
          {comparing ? 'Pick two days to compare' : 'Private to you'}
        </Text>
      </View>

      <ScrollView className="flex-1 px-5" contentContainerClassName="gap-4 pb-10">
        {error ? (
          <Card title={error.title}>
            <Text className="text-sm text-danger">{error.detail}</Text>
          </Card>
        ) : null}

        <Card title={formatMonth(month)}>
          <View className="mb-3 flex-row items-center justify-between">
            <Pressable
              className="h-10 w-10 items-center justify-center rounded-full active:bg-line"
              onPress={() => setMonth(addMonths(month, -1))}
              accessibilityLabel="Previous month"
            >
              <Text className="text-xl text-muted">‹</Text>
            </Pressable>
            <Text className="text-sm text-muted">
              {photos.length} {photos.length === 1 ? 'photo' : 'photos'}
            </Text>
            <Pressable
              className={`h-10 w-10 items-center justify-center rounded-full ${
                isFuture(startOfMonth(addMonths(month, 1))) ? 'opacity-25' : 'active:bg-line'
              }`}
              disabled={isFuture(startOfMonth(addMonths(month, 1)))}
              onPress={() => setMonth(addMonths(month, 1))}
              accessibilityLabel="Next month"
            >
              <Text className="text-xl text-muted">›</Text>
            </Pressable>
          </View>

          <View className="mb-1 flex-row">
            {WEEKDAYS.map((day, i) => (
              <View key={`${day}-${i}`} className="flex-1 items-center">
                <Text className="text-xs font-semibold text-muted">{day}</Text>
              </View>
            ))}
          </View>

          {loading ? (
            <View className="h-40 items-center justify-center">
              <ActivityIndicator color="#4ADE80" />
            </View>
          ) : (
            <View className="flex-row flex-wrap">
              {cells.map((date, index) => {
                if (date === null) {
                  return (
                    <View
                      key={`pad-${index}`}
                      style={{ width: cellSize, height: cellSize }}
                      className="m-0.5"
                    />
                  );
                }
                const photo = byDate.get(date);
                const selected = comparing && (left?.id === photo?.id || right?.id === photo?.id);

                return (
                  <Pressable
                    key={date}
                    className={`m-0.5 items-center justify-center overflow-hidden rounded-lg border ${
                      selected ? 'border-accent' : 'border-line'
                    } ${photo ? '' : 'bg-surface'}`}
                    style={{ width: cellSize, height: cellSize }}
                    disabled={!photo}
                    onPress={() => {
                      if (!photo) return;
                      if (comparing) pickForComparison(photo);
                      else setViewing(photo);
                    }}
                  >
                    {photo ? (
                      <Image
                        source={{ uri: photo.thumb_url ?? photo.view_url }}
                        style={{ width: '100%', height: '100%' }}
                        contentFit="cover"
                        transition={120}
                      />
                    ) : (
                      <Text className="text-xs text-line">{Number(date.slice(-2))}</Text>
                    )}
                  </Pressable>
                );
              })}
            </View>
          )}
        </Card>

        {comparing ? (
          <Card
            title="Compare"
            footnote="Tap two days above. Same pose, same light, same time of day makes the difference readable."
          >
            <View className="flex-row gap-2">
              {[left, right].map((photo, side) => (
                <View key={side} className="flex-1">
                  <View className="aspect-[3/4] overflow-hidden rounded-xl border border-line bg-surface">
                    {photo ? (
                      <Image
                        source={{ uri: photo.view_url }}
                        style={{ width: '100%', height: '100%' }}
                        contentFit="cover"
                      />
                    ) : (
                      <View className="flex-1 items-center justify-center">
                        <Text className="text-xs text-muted">
                          {side === 0 ? 'First' : 'Second'}
                        </Text>
                      </View>
                    )}
                  </View>
                  <Text className="mt-1 text-center text-xs text-muted">
                    {photo ? formatLong(photo.taken_on) : '—'}
                  </Text>
                </View>
              ))}
            </View>

            <View className="mt-4 gap-2">
              <Button
                title="Clear selection"
                variant="ghost"
                onPress={() => setComparison([null, null])}
              />
              <Button
                title="Done comparing"
                variant="ghost"
                onPress={() => {
                  setComparing(false);
                  setComparison([null, null]);
                }}
              />
            </View>
          </Card>
        ) : (
          <View className="gap-2">
            <Button title="Take a photo" onPress={() => add('camera')} loading={busy} />
            <Button title="Choose from library" variant="ghost" onPress={() => add('library')} />
            {photos.length >= 2 ? (
              <Button title="Compare two days" variant="ghost" onPress={() => setComparing(true)} />
            ) : null}
          </View>
        )}
      </ScrollView>

      <Modal
        visible={viewing !== null}
        animationType="fade"
        onRequestClose={() => setViewing(null)}
      >
        <View className="flex-1 bg-black" style={{ paddingTop: insets.top }}>
          <View className="flex-row items-center justify-between px-5 py-3">
            <Pressable onPress={() => setViewing(null)}>
              <Text className="text-base font-semibold text-white">Close</Text>
            </Pressable>
            <Text className="text-sm text-muted">
              {viewing ? formatLong(viewing.taken_on) : ''}
            </Text>
            <Pressable onPress={() => viewing && confirmDelete(viewing)}>
              <Text className="text-base font-semibold text-danger">Delete</Text>
            </Pressable>
          </View>
          {viewing ? (
            <Image
              source={{ uri: viewing.view_url }}
              style={{ flex: 1 }}
              contentFit="contain"
              transition={150}
            />
          ) : null}
        </View>
      </Modal>
    </View>
  );
}
