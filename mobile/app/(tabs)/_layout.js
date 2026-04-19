/**
 * Tab navigator layout — bottom tabs with tactical dark theme.
 * 6 tabs: Dashboard, Stream, ROI, Faces, Alerts, Settings
 */
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Fonts } from '../../src/theme';

const TAB_ICON = {
  index: { focused: 'grid', unfocused: 'grid-outline' },
  stream: { focused: 'videocam', unfocused: 'videocam-outline' },
  roi: { focused: 'scan', unfocused: 'scan-outline' },
  faces: { focused: 'people', unfocused: 'people-outline' },
  alerts: { focused: 'notifications', unfocused: 'notifications-outline' },
  settings: { focused: 'settings', unfocused: 'settings-outline' },
};

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerStyle: {
          backgroundColor: Colors.bgCard,
          borderBottomWidth: 1,
          borderBottomColor: Colors.border,
          shadowOpacity: 0,
          elevation: 0,
        },
        headerTintColor: Colors.text,
        headerTitleStyle: {
          ...Fonts.semibold,
          fontSize: 17,
          letterSpacing: 0.5,
        },
        tabBarStyle: {
          backgroundColor: Colors.bgCard,
          borderTopWidth: 1,
          borderTopColor: Colors.border,
          height: 60,
          paddingBottom: 6,
          paddingTop: 4,
        },
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.textMuted,
        tabBarLabelStyle: {
          fontSize: 10,
          ...Fonts.medium,
          letterSpacing: 0.3,
        },
        tabBarIcon: ({ focused, color, size }) => {
          const icons = TAB_ICON[route.name] || TAB_ICON.index;
          return (
            <Ionicons
              name={focused ? icons.focused : icons.unfocused}
              size={22}
              color={color}
            />
          );
        },
      })}
    >
      <Tabs.Screen name="index" options={{ title: 'Dashboard' }} />
      <Tabs.Screen name="stream" options={{ title: 'Stream' }} />
      <Tabs.Screen name="roi" options={{ title: 'ROI' }} />
      <Tabs.Screen name="faces" options={{ title: 'Faces' }} />
      <Tabs.Screen name="alerts" options={{ title: 'Alerts' }} />
      <Tabs.Screen name="settings" options={{ title: 'Settings' }} />
    </Tabs>
  );
}
