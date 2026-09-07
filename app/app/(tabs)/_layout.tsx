import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

const TABS: { name: string; title: string; icon: IconName }[] = [
  { name: 'index', title: 'Home', icon: 'sparkles-outline' },
  { name: 'nutrition', title: 'Nutrition', icon: 'restaurant-outline' },
  { name: 'workout', title: 'Workout', icon: 'barbell-outline' },
  { name: 'weight', title: 'Weight', icon: 'trending-down-outline' },
  { name: 'photos', title: 'Photos', icon: 'camera-outline' },
];

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#4ADE80',
        tabBarInactiveTintColor: '#8A97A6',
        tabBarStyle: { backgroundColor: '#141A21', borderTopColor: '#232C36' },
      }}
    >
      {TABS.map(({ name, title, icon }) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{
            title,
            tabBarIcon: ({ color, size }) => <Ionicons name={icon} size={size} color={color} />,
          }}
        />
      ))}
    </Tabs>
  );
}
