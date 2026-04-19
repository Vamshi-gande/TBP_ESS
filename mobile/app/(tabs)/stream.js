/**
 * Live Stream screen — select a source and watch MJPEG feed.
 */
import { useCallback, useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Image, RefreshControl, Platform } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, Radius, Fonts, Shadow } from '../../src/theme';
import { getSources, getStreamUrl, getPreviewUrl } from '../../src/api';

export default function StreamScreen() {
  const [sources, setSources] = useState([]);
  const [selected, setSelected] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setSources((await getSources()) || []); } catch (_) {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (selected) {
    const url = getStreamUrl(selected.id);
    return (
      <View style={s.container}>
        <View style={s.hdr}>
          <TouchableOpacity onPress={() => setSelected(null)} style={s.back}>
            <Ionicons name="chevron-back" size={22} color={Colors.text} />
          </TouchableOpacity>
          <Text style={s.hdrTitle} numberOfLines={1}>{selected.name}</Text>
          <View style={s.liveBadge}><View style={s.liveDot} /><Text style={s.liveText}>LIVE</Text></View>
        </View>
        <View style={s.streamWrap}>
          {Platform.OS === 'web'
            ? <img src={url} alt="stream" style={{ width:'100%', height:'100%', objectFit:'contain', background:'#000' }} />
            : <Image source={{ uri: url }} style={s.streamImg} resizeMode="contain" />}
        </View>
      </View>
    );
  }

  return (
    <View style={s.container}>
      <FlatList
        data={sources} keyExtractor={i => String(i.id)} contentContainerStyle={s.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={Colors.primary} />}
        renderItem={({ item }) => (
          <TouchableOpacity style={s.card} onPress={() => setSelected(item)} activeOpacity={0.7}>
            <Image source={{ uri: getPreviewUrl(item.id) }} style={s.cardImg} resizeMode="cover" />
            <View style={s.overlay}><View style={s.playCircle}><Ionicons name="play" size={28} color="#fff" /></View></View>
            <View style={s.cardFoot}><Text style={s.cardName}>{item.name}</Text><Text style={s.cardType}>{item.source_type}</Text></View>
          </TouchableOpacity>
        )}
        ListEmptyComponent={<View style={s.empty}><Ionicons name="videocam-off-outline" size={48} color={Colors.textMuted} /><Text style={s.emptyT}>No active streams</Text></View>}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  list: { padding: Spacing.md, paddingBottom: 100 },
  card: { backgroundColor: Colors.bgCard, borderRadius: Radius.lg, overflow: 'hidden', marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.border, ...Shadow.card },
  cardImg: { width: '100%', height: 180, backgroundColor: Colors.bgInput },
  overlay: { ...StyleSheet.absoluteFillObject, height: 180, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.35)' },
  playCircle: { width: 56, height: 56, borderRadius: 28, backgroundColor: 'rgba(59,130,246,0.8)', justifyContent: 'center', alignItems: 'center', paddingLeft: 3 },
  cardFoot: { padding: Spacing.md, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardName: { fontSize: 15, color: Colors.text, ...Fonts.semibold },
  cardType: { fontSize: 12, color: Colors.textSecondary, textTransform: 'uppercase' },
  hdr: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: Spacing.sm, paddingVertical: Spacing.sm, backgroundColor: Colors.bgCard, borderBottomWidth: 1, borderBottomColor: Colors.border },
  back: { padding: Spacing.sm },
  hdrTitle: { flex: 1, color: Colors.text, fontSize: 15, ...Fonts.semibold, marginLeft: Spacing.xs },
  liveBadge: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(239,68,68,0.15)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: Radius.full, gap: 4 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.danger },
  liveText: { color: Colors.danger, fontSize: 11, ...Fonts.bold, letterSpacing: 1 },
  streamWrap: { flex: 1, backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' },
  streamImg: { width: '100%', height: '100%' },
  empty: { alignItems: 'center', paddingVertical: Spacing.xxl * 2, gap: Spacing.sm },
  emptyT: { color: Colors.textSecondary, fontSize: 15, ...Fonts.medium },
});
