/**
 * Login screen — dark, tactical aesthetic.
 * POST /auth/login → stores JWT → redirects to (tabs).
 */
import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../src/AuthContext';
import { Colors, Spacing, Radius, Fonts, Shadow } from '../src/theme';

export default function LoginScreen() {
  const { login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) {
      setError('Please enter both fields');
      return;
    }
    setError('');
    setBusy(true);
    try {
      await login(username.trim(), password);
      router.replace('/(tabs)');
    } catch (e) {
      setError(e.message || 'Login failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.inner}>
        {/* Logo / Brand */}
        <View style={styles.brand}>
          <View style={styles.iconCircle}>
            <Ionicons name="shield-checkmark" size={40} color={Colors.primary} />
          </View>
          <Text style={styles.title}>SENTINEL</Text>
          <Text style={styles.subtitle}>Enhanced Surveillance System</Text>
        </View>

        {/* Form */}
        <View style={styles.card}>
          {error ? (
            <View style={styles.errorBox}>
              <Ionicons name="alert-circle" size={16} color={Colors.danger} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Username</Text>
            <View style={styles.inputWrap}>
              <Ionicons name="person-outline" size={18} color={Colors.textSecondary} style={styles.inputIcon} />
              <TextInput
                style={styles.input}
                value={username}
                onChangeText={setUsername}
                placeholder="admin"
                placeholderTextColor={Colors.textMuted}
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Password</Text>
            <View style={styles.inputWrap}>
              <Ionicons name="lock-closed-outline" size={18} color={Colors.textSecondary} style={styles.inputIcon} />
              <TextInput
                style={styles.input}
                value={password}
                onChangeText={setPassword}
                placeholder="••••••••"
                placeholderTextColor={Colors.textMuted}
                secureTextEntry={!showPass}
              />
              <TouchableOpacity onPress={() => setShowPass(!showPass)} style={styles.eyeBtn}>
                <Ionicons
                  name={showPass ? 'eye-off-outline' : 'eye-outline'}
                  size={20}
                  color={Colors.textSecondary}
                />
              </TouchableOpacity>
            </View>
          </View>

          <TouchableOpacity
            style={[styles.loginBtn, busy && styles.loginBtnDisabled]}
            onPress={handleLogin}
            disabled={busy}
            activeOpacity={0.8}
          >
            {busy ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.loginBtnText}>Sign In</Text>
            )}
          </TouchableOpacity>
        </View>

        <Text style={styles.footer}>Powered by YOLOv8 · InsightFace · MOG2</Text>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.bg,
  },
  inner: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
  },
  brand: {
    alignItems: 'center',
    marginBottom: Spacing.xxl,
  },
  iconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: Colors.primaryGlow,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.primaryDim,
  },
  title: {
    fontSize: 28,
    letterSpacing: 6,
    color: Colors.text,
    ...Fonts.bold,
  },
  subtitle: {
    fontSize: 13,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
    letterSpacing: 1,
  },
  card: {
    backgroundColor: Colors.bgCard,
    borderRadius: Radius.lg,
    padding: Spacing.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadow.card,
  },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderRadius: Radius.sm,
    padding: Spacing.sm,
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  errorText: {
    color: Colors.danger,
    fontSize: 13,
    flex: 1,
  },
  inputGroup: {
    marginBottom: Spacing.md,
  },
  label: {
    color: Colors.textSecondary,
    fontSize: 12,
    ...Fonts.medium,
    marginBottom: Spacing.xs,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bgInput,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.sm,
  },
  inputIcon: {
    marginRight: Spacing.sm,
  },
  input: {
    flex: 1,
    height: 48,
    color: Colors.text,
    fontSize: 15,
  },
  eyeBtn: {
    padding: Spacing.sm,
  },
  loginBtn: {
    backgroundColor: Colors.primary,
    borderRadius: Radius.md,
    height: 48,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.sm,
    ...Shadow.glow,
  },
  loginBtnDisabled: {
    opacity: 0.6,
  },
  loginBtnText: {
    color: '#fff',
    fontSize: 16,
    ...Fonts.semibold,
    letterSpacing: 1,
  },
  footer: {
    textAlign: 'center',
    color: Colors.textMuted,
    fontSize: 11,
    marginTop: Spacing.xl,
    letterSpacing: 0.5,
  },
});
