/**
 * ROI Editor — list/create/delete ROI zones per source.
 */
import { useCallback, useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, TextInput, Modal, RefreshControl, Alert } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, Radius, Fonts, Shadow } from '../../src/theme';
import { getSources, getROIs, saveROI, deleteROI } from '../../src/api';

const ZONE_COLORS = { green: Colors.zoneGreen, amber: Colors.zoneAmber, red: Colors.zoneRed, critical: Colors.zoneCritical };

export default function ROIScreen() {
  const [sources, setSources] = useState([]);
  const [selSrc, setSelSrc] = useState(null);
  const [zones, setZones] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  const loadSources = useCallback(async () => {
    try { setSources((await getSources()) || []); } catch (_) {}
  }, []);

  useFocusEffect(useCallback(() => { loadSources(); }, [loadSources]));

  const loadZones = async (srcId) => {
    try { setZones((await getROIs(srcId)) || []); } catch (_) { setZones([]); }
  };

  const pickSource = (src) => { setSelSrc(src); loadZones(src.id); };

  const handleDelete = (id, label) => {
    Alert.alert('Delete Zone', `Remove "${label}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => { await deleteROI(id).catch(() => {}); loadZones(selSrc.id); } },
    ]);
  };

  if (!selSrc) {
    return (
      <View style={s.container}>
        <FlatList
          data={sources} keyExtractor={i => String(i.id)} contentContainerStyle={s.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await loadSources(); setRefreshing(false); }} tintColor={Colors.primary} />}
          ListHeaderComponent={<Text style={s.heading}>Select a source to manage zones</Text>}
          renderItem={({ item }) => (
            <TouchableOpacity style={s.srcCard} onPress={() => pickSource(item)}>
              <Ionicons name="videocam-outline" size={20} color={Colors.primary} />
              <Text style={s.srcName}>{item.name}</Text>
              <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
            </TouchableOpacity>
          )}
          ListEmptyComponent={<View style={s.empty}><Ionicons name="scan-outline" size={48} color={Colors.textMuted} /><Text style={s.emptyT}>No sources available</Text></View>}
        />
      </View>
    );
  }

  return (
    <View style={s.container}>
      <View style={s.hdr}>
        <TouchableOpacity onPress={() => setSelSrc(null)} style={s.back}><Ionicons name="chevron-back" size={22} color={Colors.text} /></TouchableOpacity>
        <Text style={s.hdrTitle}>{selSrc.name} — Zones</Text>
        <TouchableOpacity onPress={() => setShowAdd(true)}><Ionicons name="add-circle" size={24} color={Colors.primary} /></TouchableOpacity>
      </View>
      <FlatList
        data={zones} keyExtractor={i => String(i.id)} contentContainerStyle={s.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await loadZones(selSrc.id); setRefreshing(false); }} tintColor={Colors.primary} />}
        renderItem={({ item }) => (
          <View style={s.zoneCard}>
            <View style={[s.zoneDot, { backgroundColor: ZONE_COLORS[item.zone_type] || Colors.textMuted }]} />
            <View style={s.zoneInfo}>
              <Text style={s.zoneLabel}>{item.label}</Text>
              <Text style={s.zoneMeta}>{item.zone_type} · ({item.x},{item.y}) {item.width}×{item.height}</Text>
            </View>
            <TouchableOpacity onPress={() => handleDelete(item.id, item.label)}><Ionicons name="trash-outline" size={18} color={Colors.danger} /></TouchableOpacity>
          </View>
        )}
        ListEmptyComponent={<View style={s.empty}><Ionicons name="scan-outline" size={48} color={Colors.textMuted} /><Text style={s.emptyT}>No zones defined</Text><Text style={s.emptyH}>Tap + to create a zone</Text></View>}
      />
      <AddZoneModal visible={showAdd} sourceId={selSrc.id} onClose={() => setShowAdd(false)} onAdded={() => loadZones(selSrc.id)} />
    </View>
  );
}

function AddZoneModal({ visible, sourceId, onClose, onAdded }) {
  const [label, setLabel] = useState('');
  const [type, setType] = useState('green');
  const [x, setX] = useState('0'); const [y, setY] = useState('0');
  const [w, setW] = useState('200'); const [h, setH] = useState('200');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!label.trim()) return;
    setBusy(true);
    try {
      await saveROI({ source_id: sourceId, label: label.trim(), zone_type: type, x: +x, y: +y, width: +w, height: +h });
      setLabel(''); onClose(); onAdded();
    } catch (_) {}
    setBusy(false);
  };

  const types = ['green', 'amber', 'red', 'critical'];

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={s.overlay}>
        <View style={s.modal}>
          <Text style={s.modalTitle}>New Zone</Text>
          <Text style={s.lbl}>Label</Text>
          <TextInput style={s.inp} value={label} onChangeText={setLabel} placeholder="Front yard" placeholderTextColor={Colors.textMuted} />
          <Text style={s.lbl}>Type</Text>
          <View style={s.typeRow}>
            {types.map(t => (
              <TouchableOpacity key={t} style={[s.typeBtn, type === t && { borderColor: ZONE_COLORS[t] }]} onPress={() => setType(t)}>
                <View style={[s.typeDot, { backgroundColor: ZONE_COLORS[t] }]} />
                <Text style={[s.typeTxt, type === t && { color: Colors.text }]}>{t}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={s.coordRow}>
            <View style={s.coordCol}><Text style={s.lbl}>X</Text><TextInput style={s.inp} value={x} onChangeText={setX} keyboardType="numeric" /></View>
            <View style={s.coordCol}><Text style={s.lbl}>Y</Text><TextInput style={s.inp} value={y} onChangeText={setY} keyboardType="numeric" /></View>
            <View style={s.coordCol}><Text style={s.lbl}>W</Text><TextInput style={s.inp} value={w} onChangeText={setW} keyboardType="numeric" /></View>
            <View style={s.coordCol}><Text style={s.lbl}>H</Text><TextInput style={s.inp} value={h} onChangeText={setH} keyboardType="numeric" /></View>
          </View>
          <View style={s.modalActs}>
            <TouchableOpacity style={s.cancelBtn} onPress={onClose}><Text style={s.cancelTxt}>Cancel</Text></TouchableOpacity>
            <TouchableOpacity style={s.submitBtn} onPress={submit} disabled={busy}><Text style={s.submitTxt}>{busy ? '...' : 'Save'}</Text></TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  list: { padding: Spacing.md, paddingBottom: 100 },
  heading: { color: Colors.textSecondary, fontSize: 14, marginBottom: Spacing.md, ...Fonts.medium },
  srcCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.bgCard, padding: Spacing.md, borderRadius: Radius.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.border, gap: Spacing.sm },
  srcName: { flex: 1, color: Colors.text, fontSize: 15, ...Fonts.semibold },
  hdr: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, backgroundColor: Colors.bgCard, borderBottomWidth: 1, borderBottomColor: Colors.border },
  back: { padding: Spacing.sm },
  hdrTitle: { flex: 1, color: Colors.text, fontSize: 15, ...Fonts.semibold, marginLeft: Spacing.xs },
  zoneCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.bgCard, padding: Spacing.md, borderRadius: Radius.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.border, gap: Spacing.sm },
  zoneDot: { width: 10, height: 10, borderRadius: 5 },
  zoneInfo: { flex: 1 },
  zoneLabel: { color: Colors.text, fontSize: 14, ...Fonts.semibold },
  zoneMeta: { color: Colors.textSecondary, fontSize: 11, marginTop: 2 },
  empty: { alignItems: 'center', paddingVertical: Spacing.xxl * 2, gap: Spacing.sm },
  emptyT: { color: Colors.textSecondary, fontSize: 15, ...Fonts.medium },
  emptyH: { color: Colors.textMuted, fontSize: 12 },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', paddingHorizontal: Spacing.lg },
  modal: { backgroundColor: Colors.bgElevated, borderRadius: Radius.lg, padding: Spacing.lg, borderWidth: 1, borderColor: Colors.border },
  modalTitle: { fontSize: 18, color: Colors.text, ...Fonts.bold, marginBottom: Spacing.md },
  lbl: { color: Colors.textSecondary, fontSize: 11, ...Fonts.medium, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 4, marginTop: Spacing.sm },
  inp: { backgroundColor: Colors.bgInput, color: Colors.text, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border, padding: Spacing.sm, fontSize: 14, height: 44 },
  typeRow: { flexDirection: 'row', gap: Spacing.sm, marginTop: 4 },
  typeBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: Radius.full, borderWidth: 1, borderColor: Colors.border },
  typeDot: { width: 8, height: 8, borderRadius: 4 },
  typeTxt: { fontSize: 12, color: Colors.textSecondary, ...Fonts.medium, textTransform: 'capitalize' },
  coordRow: { flexDirection: 'row', gap: Spacing.sm, marginTop: 4 },
  coordCol: { flex: 1 },
  modalActs: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: Spacing.lg, gap: Spacing.sm },
  cancelBtn: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border },
  cancelTxt: { color: Colors.textSecondary, ...Fonts.medium },
  submitBtn: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: Radius.md, backgroundColor: Colors.primary },
  submitTxt: { color: '#fff', ...Fonts.semibold },
});
