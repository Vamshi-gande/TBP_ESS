/**
 * Alerts screen — paginated alert list with score badges and snapshot viewer.
 */
import { useCallback, useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Image, Modal, RefreshControl } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, Radius, Fonts, Shadow } from '../../src/theme';
import { getAlerts, getSnapshotUrl } from '../../src/api';

const SCORE_COLORS = [Colors.success, Colors.info, Colors.warning, Colors.danger];
const SCORE_LABELS = ['Silent Log', 'Snapshot', 'WS + WhatsApp', 'Full Alert'];

export default function AlertsScreen() {
  const [alerts, setAlerts] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(0);
  const [snapUri, setSnapUri] = useState(null);
  const PAGE = 30;

  const load = useCallback(async (p = 0) => {
    try {
      const data = await getAlerts(null, PAGE, p * PAGE);
      if (p === 0) setAlerts(data || []);
      else setAlerts(prev => [...prev, ...(data || [])]);
      setPage(p);
    } catch (_) {}
  }, []);

  useFocusEffect(useCallback(() => { load(0); }, [load]));

  const formatTime = (ts) => {
    if (!ts) return '';
    try { const d = new Date(ts); return d.toLocaleString(); } catch (_) { return ts; }
  };

  return (
    <View style={s.container}>
      <FlatList
        data={alerts} keyExtractor={(i, idx) => `${i.id}-${idx}`} contentContainerStyle={s.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(0); setRefreshing(false); }} tintColor={Colors.primary} />}
        onEndReached={() => { if (alerts.length >= PAGE) load(page + 1); }}
        onEndReachedThreshold={0.3}
        renderItem={({ item }) => {
          const scoreColor = SCORE_COLORS[item.suspicion_score] || Colors.textMuted;
          const scoreLabel = SCORE_LABELS[item.suspicion_score] || `Score ${item.suspicion_score}`;
          return (
            <TouchableOpacity
              style={s.card}
              activeOpacity={0.7}
              onPress={() => item.snapshot_path && setSnapUri(getSnapshotUrl(item.id))}
            >
              <View style={s.cardLeft}>
                <View style={[s.scoreBadge, { backgroundColor: scoreColor + '20', borderColor: scoreColor }]}>
                  <Text style={[s.scoreNum, { color: scoreColor }]}>{item.suspicion_score}</Text>
                </View>
              </View>
              <View style={s.cardBody}>
                <Text style={s.alertType}>{item.alert_type || 'detection'}</Text>
                <Text style={s.alertMeta}>{scoreLabel} · Source #{item.source_id}</Text>
                <Text style={s.alertTime}>{formatTime(item.created_at)}</Text>
              </View>
              <View style={s.cardRight}>
                {item.notified && <Ionicons name="checkmark-circle" size={16} color={Colors.success} />}
                {item.snapshot_path && <Ionicons name="image-outline" size={16} color={Colors.textSecondary} />}
              </View>
            </TouchableOpacity>
          );
        }}
        ListEmptyComponent={
          <View style={s.empty}>
            <Ionicons name="shield-checkmark-outline" size={48} color={Colors.textMuted} />
            <Text style={s.emptyT}>No alerts yet</Text>
            <Text style={s.emptyH}>System is monitoring</Text>
          </View>
        }
      />

      {/* Snapshot modal */}
      <Modal visible={!!snapUri} transparent animationType="fade" onRequestClose={() => setSnapUri(null)}>
        <TouchableOpacity style={s.snapOverlay} activeOpacity={1} onPress={() => setSnapUri(null)}>
          <View style={s.snapCard}>
            <Image source={{ uri: snapUri }} style={s.snapImg} resizeMode="contain" />
            <TouchableOpacity style={s.snapClose} onPress={() => setSnapUri(null)}>
              <Ionicons name="close" size={22} color="#fff" />
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  list: { padding: Spacing.md, paddingBottom: 100 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.bgCard, padding: Spacing.md, borderRadius: Radius.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.border, ...Shadow.card },
  cardLeft: { marginRight: Spacing.sm },
  scoreBadge: { width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center', borderWidth: 1 },
  scoreNum: { fontSize: 16, ...Fonts.bold },
  cardBody: { flex: 1 },
  alertType: { color: Colors.text, fontSize: 14, ...Fonts.semibold, textTransform: 'capitalize' },
  alertMeta: { color: Colors.textSecondary, fontSize: 12, marginTop: 2 },
  alertTime: { color: Colors.textMuted, fontSize: 11, marginTop: 2 },
  cardRight: { flexDirection: 'row', gap: 6, alignItems: 'center' },
  empty: { alignItems: 'center', paddingVertical: Spacing.xxl * 2, gap: Spacing.sm },
  emptyT: { color: Colors.textSecondary, fontSize: 15, ...Fonts.medium },
  emptyH: { color: Colors.textMuted, fontSize: 12 },
  snapOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'center', alignItems: 'center', padding: Spacing.lg },
  snapCard: { width: '100%', aspectRatio: 16 / 9, borderRadius: Radius.lg, overflow: 'hidden', backgroundColor: '#000' },
  snapImg: { width: '100%', height: '100%' },
  snapClose: { position: 'absolute', top: 8, right: 8, width: 32, height: 32, borderRadius: 16, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', alignItems: 'center' },
});
