/**
 * Settings screen — view and update system configuration.
 * Pulls from GET /settings, updates via POST /settings/update.
 */
import { useCallback, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  TextInput,
  Modal,
  RefreshControl,
  ActivityIndicator,
  Switch,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, Radius, Fonts, Shadow } from '../../src/theme';
import { getSettings, updateSetting, healthCheck } from '../../src/api';
import { useAuth } from '../../src/AuthContext';

const SETTING_META = {
  loitering_threshold: {
    label: 'Loitering Threshold',
    icon: 'timer-outline',
    desc: 'Seconds before a person is flagged as loitering',
    suffix: 's',
    type: 'number',
  },
  night_start_hour: {
    label: 'Night Start Hour',
    icon: 'moon-outline',
    desc: 'Hour when night mode scoring begins (24h)',
    suffix: ':00',
    type: 'number',
  },
  night_end_hour: {
    label: 'Night End Hour',
    icon: 'sunny-outline',
    desc: 'Hour when night mode scoring ends (24h)',
    suffix: ':00',
    type: 'number',
  },
  alert_score_app: {
    label: 'App Alert Threshold',
    icon: 'phone-portrait-outline',
    desc: 'Minimum score to trigger in-app + WS alert',
    suffix: '',
    type: 'number',
  },
  alert_score_whatsapp: {
    label: 'WhatsApp Alert Threshold',
    icon: 'chatbubble-outline',
    desc: 'Minimum score to trigger WhatsApp notification',
    suffix: '',
    type: 'number',
  },
};

export default function SettingsScreen() {
  const { logout } = useAuth();
  const [settings, setSettings] = useState([]);
  const [health, setHealth] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [editItem, setEditItem] = useState(null);

  const load = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([
        getSettings().catch(() => []),
        healthCheck().catch(() => null),
      ]);
      setSettings(s || []);
      setHealth(h);
    } catch (_) {}
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handleSave = async (key, value) => {
    try {
      await updateSetting(key, value);
      await load();
    } catch (_) {}
    setEditItem(null);
  };

  return (
    <View style={s.container}>
      <FlatList
        data={settings}
        keyExtractor={(item) => item.key}
        contentContainerStyle={s.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={Colors.primary}
          />
        }
        ListHeaderComponent={
          <>
            {/* Server Status Card */}
            <View style={s.statusCard}>
              <View style={s.statusRow}>
                <View style={s.statusLeft}>
                  <View
                    style={[
                      s.statusDot,
                      {
                        backgroundColor: health
                          ? Colors.success
                          : Colors.danger,
                      },
                    ]}
                  />
                  <Text style={s.statusLabel}>Server Status</Text>
                </View>
                <Text
                  style={[
                    s.statusValue,
                    { color: health ? Colors.success : Colors.danger },
                  ]}
                >
                  {health ? 'Online' : 'Offline'}
                </Text>
              </View>
              {health && (
                <Text style={s.statusVersion}>v{health.version || '1.0.0'}</Text>
              )}
            </View>

            <Text style={s.sectionTitle}>System Configuration</Text>
          </>
        }
        renderItem={({ item }) => {
          const meta = SETTING_META[item.key] || {
            label: item.key,
            icon: 'settings-outline',
            desc: '',
            suffix: '',
            type: 'text',
          };
          return (
            <TouchableOpacity
              style={s.card}
              activeOpacity={0.7}
              onPress={() => setEditItem(item)}
            >
              <View style={s.cardIcon}>
                <Ionicons name={meta.icon} size={20} color={Colors.primary} />
              </View>
              <View style={s.cardBody}>
                <Text style={s.cardLabel}>{meta.label}</Text>
                <Text style={s.cardDesc}>{meta.desc}</Text>
              </View>
              <View style={s.cardValue}>
                <Text style={s.valueText}>
                  {item.value}
                  {meta.suffix}
                </Text>
                <Ionicons
                  name="chevron-forward"
                  size={16}
                  color={Colors.textMuted}
                />
              </View>
            </TouchableOpacity>
          );
        }}
        ListFooterComponent={
          <View style={s.footer}>
            <View style={s.infoCard}>
              <Ionicons
                name="information-circle-outline"
                size={18}
                color={Colors.info}
              />
              <Text style={s.infoText}>
                Changes take effect immediately. Loitering threshold updates the
                in-memory tracker. Night hours affect the Three-Signal scoring
                system.
              </Text>
            </View>
            <TouchableOpacity style={s.logoutBtn} onPress={logout}>
              <Ionicons name="log-out-outline" size={18} color={Colors.danger} />
              <Text style={s.logoutText}>Sign Out</Text>
            </TouchableOpacity>
            <Text style={s.footerBrand}>
              SENTINEL v1.0.0 · YOLOv8 · InsightFace · MOG2
            </Text>
          </View>
        }
        ListEmptyComponent={
          <View style={s.empty}>
            <Ionicons
              name="settings-outline"
              size={48}
              color={Colors.textMuted}
            />
            <Text style={s.emptyT}>No settings available</Text>
          </View>
        }
      />

      {/* Edit Modal */}
      {editItem && (
        <EditModal
          item={editItem}
          meta={SETTING_META[editItem.key]}
          onClose={() => setEditItem(null)}
          onSave={handleSave}
        />
      )}
    </View>
  );
}

function EditModal({ item, meta, onClose, onSave }) {
  const [value, setValue] = useState(item.value);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    await onSave(item.key, value);
    setBusy(false);
  };

  const label = meta?.label || item.key;

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <View style={s.overlay}>
        <View style={s.modal}>
          <Text style={s.modalTitle}>Edit {label}</Text>
          {meta?.desc ? <Text style={s.modalDesc}>{meta.desc}</Text> : null}

          <Text style={s.lbl}>Value</Text>
          <TextInput
            style={s.inp}
            value={value}
            onChangeText={setValue}
            keyboardType={meta?.type === 'number' ? 'numeric' : 'default'}
            autoFocus
            selectTextOnFocus
          />

          <View style={s.acts}>
            <TouchableOpacity style={s.cancelBtn} onPress={onClose}>
              <Text style={s.cancelTxt}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={s.submitBtn}
              onPress={submit}
              disabled={busy}
            >
              {busy ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={s.submitTxt}>Save</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  list: { padding: Spacing.md, paddingBottom: 100 },

  // Status card
  statusCard: {
    backgroundColor: Colors.bgCard,
    borderRadius: Radius.md,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadow.card,
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  statusLeft: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  statusLabel: { color: Colors.text, fontSize: 15, ...Fonts.semibold },
  statusValue: { fontSize: 14, ...Fonts.bold, textTransform: 'uppercase', letterSpacing: 1 },
  statusVersion: { color: Colors.textMuted, fontSize: 11, marginTop: 4 },

  // Section
  sectionTitle: {
    color: Colors.textSecondary,
    fontSize: 12,
    ...Fonts.medium,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: Spacing.sm,
  },

  // Setting cards
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bgCard,
    padding: Spacing.md,
    borderRadius: Radius.md,
    marginBottom: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.primaryGlow,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: Spacing.sm,
  },
  cardBody: { flex: 1 },
  cardLabel: { color: Colors.text, fontSize: 14, ...Fonts.semibold },
  cardDesc: { color: Colors.textMuted, fontSize: 11, marginTop: 2 },
  cardValue: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  valueText: {
    color: Colors.primary,
    fontSize: 15,
    ...Fonts.bold,
  },

  // Footer
  footer: { marginTop: Spacing.lg },
  infoCard: {
    flexDirection: 'row',
    gap: Spacing.sm,
    backgroundColor: 'rgba(6, 182, 212, 0.08)',
    padding: Spacing.md,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: 'rgba(6, 182, 212, 0.15)',
    marginBottom: Spacing.lg,
  },
  infoText: { flex: 1, color: Colors.info, fontSize: 12, lineHeight: 18 },
  logoutBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    padding: Spacing.md,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.2)',
    marginBottom: Spacing.md,
  },
  logoutText: { color: Colors.danger, fontSize: 14, ...Fonts.medium },
  footerBrand: {
    textAlign: 'center',
    color: Colors.textMuted,
    fontSize: 11,
    letterSpacing: 0.5,
    marginBottom: Spacing.xl,
  },

  // Empty
  empty: {
    alignItems: 'center',
    paddingVertical: Spacing.xxl * 2,
    gap: Spacing.sm,
  },
  emptyT: { color: Colors.textSecondary, fontSize: 15, ...Fonts.medium },

  // Modal
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    paddingHorizontal: Spacing.lg,
  },
  modal: {
    backgroundColor: Colors.bgElevated,
    borderRadius: Radius.lg,
    padding: Spacing.lg,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  modalTitle: {
    fontSize: 18,
    color: Colors.text,
    ...Fonts.bold,
    marginBottom: 4,
  },
  modalDesc: {
    color: Colors.textSecondary,
    fontSize: 12,
    marginBottom: Spacing.md,
  },
  lbl: {
    color: Colors.textSecondary,
    fontSize: 11,
    ...Fonts.medium,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 4,
    marginTop: Spacing.sm,
  },
  inp: {
    backgroundColor: Colors.bgInput,
    color: Colors.text,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.sm,
    fontSize: 16,
    height: 48,
    ...Fonts.bold,
  },
  acts: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: Spacing.lg,
    gap: Spacing.sm,
  },
  cancelBtn: {
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cancelTxt: { color: Colors.textSecondary, ...Fonts.medium },
  submitBtn: {
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: Radius.md,
    backgroundColor: Colors.primary,
  },
  submitTxt: { color: '#fff', ...Fonts.semibold },
});
