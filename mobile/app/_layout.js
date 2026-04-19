/**
 * Root layout — wraps the entire app in AuthProvider.
 * If not authenticated → show Login screen.
 * If authenticated → show (tabs) layout.
 */
import { Slot, useRouter, useSegments } from 'expo-router';
import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { AuthProvider, useAuth } from '../src/AuthContext';
import { Colors } from '../src/theme';

function AuthGate() {
  const { token, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;

    const inAuthGroup = segments[0] === '(tabs)';

    if (!token && inAuthGroup) {
      router.replace('/login');
    } else if (token && !inAuthGroup) {
      router.replace('/(tabs)');
    }
  }, [token, loading, segments]);

  if (loading) {
    return (
      <View style={styles.loader}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  return <Slot />;
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="light" backgroundColor={Colors.bg} />
      <AuthGate />
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  loader: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.bg,
  },
});
