/**
 * Dashboard / Home — system overview with source cards and live stats.
 */
import { useCallback, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  Image,
  TextInput,
  Modal,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, Radius, Fonts, Shadow } from '../../src/theme';
import {
  getSources,
  getAlerts,
  connectCamera,
  deleteSource,
  getPreviewUrl,
  healthCheck,
} from '../../src/api';
import { useAuth } from '../../src/AuthContext';

export default function DashboardScreen() {
  const { logout } = useAuth();
  const [sources, setSources] = useState([]);
  const [alertCount, setAlertCount] = useState(0);
  const [health, setHealth] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, a, h] = await Promise.all([
        getSources().catch(() => []),
        getAlerts(null, 1, 0).catch(() => []),
        healthCheck().catch(() => null),
      ]);
      setSources(s || []);
      setAlertCount(Array.isArray(a) ? a.length : 0);
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

  const handleDelete = (id, name) => {
    Alert.alert('Remove Source', `Disconnect "${name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          await deleteSource(id).catch(() => {});
          load();
        },
      },
    ]);
  };

  const renderSource = ({ item }) => (
    <View style={styles.sourceCard}>
      <Image
        source={{ uri: getPreviewUrl(item.id) }}
        style={styles.preview}
        resizeMode="cover"
      />
      <View style={styles.sourceInfo}>
        <Text style={styles.sourceName} numberOfLines={1}>{item.name}</Text>
        <View style={styles.sourceMetaRow}>
          <View style={[styles.statusDot, { backgroundColor: Colors.success }]} />
          <Text style={styles.sourceType}>{item.source_type || 'camera'}</Text>
        </View>
      </View>
      <TouchableOpacity onPress={() => handleDelete(item.id, item.name)} style={styles.deleteBtn}>
        <Ionicons name="trash-outline" size={18} color={Colors.danger} />
      </TouchableOpacity>
    </View>
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={sources}
        keyExtractor={(i) => String(i.id)}
        renderItem={renderSource}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.primary} />}
        ListHeaderComponent={
          <>
            {/* Stats Row */}
            <View style={styles.statsRow}>
              <StatCard icon="videocam" label="Sources" value={sources.length} color={Colors.primary} />
              <StatCard icon="notifications" label="Alerts" value={alertCount} color={Colors.warning} />
              <StatCard
                icon="pulse"
                label="Server"
                value={health ? 'OK' : '—'}
                color={health ? Colors.success : Colors.textMuted}
              />
            </View>

            {/* Section header */}
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>Active Sources</Text>
              <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
                <Ionicons name="add-circle" size={24} color={Colors.primary} />
              </TouchableOpacity>
            </View>
          </>
        }
        ListEmptyComponent={
          <View style={styles.emptyWrap}>
            <Ionicons name="videocam-off-outline" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyText}>No sources connected</Text>
            <Text style={styles.emptyHint}>Tap + to add a camera or upload a video</Text>
          </View>
        }
        ListFooterComponent={
          <TouchableOpacity style={styles.logoutBtn} onPress={logout}>
            <Ionicons name="log-out-outline" size={18} color={Colors.danger} />
            <Text style={styles.logoutText}>Sign Out</Text>
          </TouchableOpacity>
        }
      />

      <AddSourceModal visible={showAdd} onClose={() => setShowAdd(false)} onAdded={load} />
    </View>
  );
}

function StatCard({ icon, label, value, color }) {
  return (
    <View style={styles.statCard}>
      <Ionicons name={icon} size={20} color={color} />
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function AddSourceModal({ visible, onClose, onAdded }) {
  const [name, setName] = useState('');
  const [uri, setUri] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!name.trim()) { setError('Name is required'); return; }
    setError('');
    setBusy(true);
    try {
      const type = uri.trim() ? 'ip_camera' : 'webcam';
      await connectCamera(name.trim(), type, uri.trim() || '0');
      setName('');
      setUri('');
      onClose();
      onAdded();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.modalOverlay}>
        <View style={styles.modalCard}>
          <Text style={styles.modalTitle}>Add Source</Text>

          {error ? <Text style={styles.modalError}>{error}</Text> : null}

          <Text style={styles.label}>Name</Text>
          <TextInput
            style={styles.modalInput}
            value={name}
            onChangeText={setName}
            placeholder="Front Door"
            placeholderTextColor={Colors.textMuted}
          />

          <Text style={styles.label}>URI (blank for webcam)</Text>
          <TextInput
            style={styles.modalInput}
            value={uri}
            onChangeText={setUri}
            placeholder="rtsp://... or http://..."
            placeholderTextColor={Colors.textMuted}
            autoCapitalize="none"
          />

          <View style={styles.modalActions}>
            <TouchableOpacity style={styles.modalCancel} onPress={onClose}>
              <Text style={styles.modalCancelText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.modalSubmit} onPress={submit} disabled={busy}>
              {busy ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.modalSubmitText}>Connect</Text>}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  list: { padding: Spacing.md, paddingBottom: 100 },

  // Stats
  statsRow: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.lg },
  statCard: {
    flex: 1,
    backgroundColor: Colors.bgCard,
    borderRadius: Radius.md,
    padding: Spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 4,
  },
  statValue: { fontSize: 22, ...Fonts.bold },
  statLabel: { fontSize: 11, color: Colors.textSecondary, ...Fonts.medium, textTransform: 'uppercase', letterSpacing: 0.5 },

  // Section
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.sm },
  sectionTitle: { fontSize: 15, color: Colors.text, ...Fonts.semibold },
  addBtn: { padding: Spacing.xs },

  // Source cards
  sourceCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bgCard,
    borderRadius: Radius.md,
    padding: Spacing.sm,
    marginBottom: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadow.card,
  },
  preview: {
    width: 72,
    height: 48,
    borderRadius: Radius.sm,
    backgroundColor: Colors.bgInput,
  },
  sourceInfo: { flex: 1, marginLeft: Spacing.sm },
  sourceName: { fontSize: 14, color: Colors.text, ...Fonts.semibold },
  sourceMetaRow: { flexDirection: 'row', alignItems: 'center', marginTop: 2, gap: 4 },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  sourceType: { fontSize: 11, color: Colors.textSecondary },
  deleteBtn: { padding: Spacing.sm },

  // Empty
  emptyWrap: { alignItems: 'center', paddingVertical: Spacing.xxl, gap: Spacing.sm },
  emptyText: { color: Colors.textSecondary, fontSize: 15, ...Fonts.medium },
  emptyHint: { color: Colors.textMuted, fontSize: 12 },

  // Logout
  logoutBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: Spacing.xl,
    gap: Spacing.sm,
    padding: Spacing.md,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.2)',
  },
  logoutText: { color: Colors.danger, fontSize: 14, ...Fonts.medium },

  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    paddingHorizontal: Spacing.lg,
  },
  modalCard: {
    backgroundColor: Colors.bgElevated,
    borderRadius: Radius.lg,
    padding: Spacing.lg,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  modalTitle: { fontSize: 18, color: Colors.text, ...Fonts.bold, marginBottom: Spacing.md },
  modalError: { color: Colors.danger, fontSize: 13, marginBottom: Spacing.sm },
  label: { color: Colors.textSecondary, fontSize: 11, ...Fonts.medium, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 4, marginTop: Spacing.sm },
  modalInput: {
    backgroundColor: Colors.bgInput,
    color: Colors.text,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.sm,
    fontSize: 14,
    height: 44,
  },
  modalActions: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: Spacing.lg, gap: Spacing.sm },
  modalCancel: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border },
  modalCancelText: { color: Colors.textSecondary, ...Fonts.medium },
  modalSubmit: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: Radius.md, backgroundColor: Colors.primary },
  modalSubmitText: { color: '#fff', ...Fonts.semibold },
});
