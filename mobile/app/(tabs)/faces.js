/**
 * Face Registration — list registered faces, register new ones via camera/gallery.
 */
import { useCallback, useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, TextInput, Modal, Image, RefreshControl, Alert, ActivityIndicator } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { Colors, Spacing, Radius, Fonts, Shadow } from '../../src/theme';
import { getFaces, registerFace, deleteFace } from '../../src/api';

export default function FacesScreen() {
  const [faces, setFaces] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(async () => {
    try { setFaces((await getFaces()) || []); } catch (_) {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const handleDelete = (id, name) => {
    Alert.alert('Remove Face', `Delete "${name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => { await deleteFace(id).catch(() => {}); load(); } },
    ]);
  };

  return (
    <View style={s.container}>
      <FlatList
        data={faces} keyExtractor={i => String(i.id)} contentContainerStyle={s.list} numColumns={2} columnWrapperStyle={s.row}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={Colors.primary} />}
        ListHeaderComponent={
          <View style={s.hdrRow}>
            <Text style={s.heading}>Registered Residents</Text>
            <TouchableOpacity onPress={() => setShowAdd(true)}><Ionicons name="person-add" size={22} color={Colors.primary} /></TouchableOpacity>
          </View>
        }
        renderItem={({ item }) => (
          <View style={s.card}>
            <View style={s.avatar}>
              <Ionicons name="person" size={32} color={Colors.primaryDim} />
            </View>
            <Text style={s.name} numberOfLines={1}>{item.name}</Text>
            <Text style={s.meta}>ID {item.id}</Text>
            <TouchableOpacity style={s.delBtn} onPress={() => handleDelete(item.id, item.name)}>
              <Ionicons name="close-circle" size={20} color={Colors.danger} />
            </TouchableOpacity>
          </View>
        )}
        ListEmptyComponent={<View style={s.empty}><Ionicons name="people-outline" size={48} color={Colors.textMuted} /><Text style={s.emptyT}>No faces registered</Text><Text style={s.emptyH}>Tap the + icon to add a resident</Text></View>}
      />
      <RegisterModal visible={showAdd} onClose={() => setShowAdd(false)} onAdded={load} />
    </View>
  );
}

function RegisterModal({ visible, onClose, onAdded }) {
  const [name, setName] = useState('');
  const [imageUri, setImageUri] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const pickImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.8 });
    if (!result.canceled && result.assets?.length) setImageUri(result.assets[0].uri);
  };

  const submit = async () => {
    if (!name.trim() || !imageUri) { setError('Name and photo are required'); return; }
    setError(''); setBusy(true);
    try {
      await registerFace(name.trim(), imageUri);
      setName(''); setImageUri(null); onClose(); onAdded();
    } catch (e) { setError(e.message); }
    setBusy(false);
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={s.overlay}>
        <View style={s.modal}>
          <Text style={s.modalTitle}>Register Face</Text>
          {error ? <Text style={s.err}>{error}</Text> : null}
          <Text style={s.lbl}>Name</Text>
          <TextInput style={s.inp} value={name} onChangeText={setName} placeholder="John Doe" placeholderTextColor={Colors.textMuted} />
          <Text style={s.lbl}>Photo</Text>
          <TouchableOpacity style={s.photoPicker} onPress={pickImage}>
            {imageUri ? <Image source={{ uri: imageUri }} style={s.photoPreview} /> : <><Ionicons name="camera-outline" size={28} color={Colors.textMuted} /><Text style={s.photoHint}>Tap to select</Text></>}
          </TouchableOpacity>
          <View style={s.acts}>
            <TouchableOpacity style={s.cancelBtn} onPress={onClose}><Text style={s.cancelTxt}>Cancel</Text></TouchableOpacity>
            <TouchableOpacity style={s.submitBtn} onPress={submit} disabled={busy}>
              {busy ? <ActivityIndicator color="#fff" size="small" /> : <Text style={s.submitTxt}>Register</Text>}
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
  row: { gap: Spacing.sm },
  hdrRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.md },
  heading: { color: Colors.text, fontSize: 16, ...Fonts.semibold },
  card: { flex: 1, backgroundColor: Colors.bgCard, borderRadius: Radius.md, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.border, alignItems: 'center', ...Shadow.card, maxWidth: '49%' },
  avatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: Colors.primaryGlow, justifyContent: 'center', alignItems: 'center', marginBottom: Spacing.sm },
  name: { color: Colors.text, fontSize: 14, ...Fonts.semibold, textAlign: 'center' },
  meta: { color: Colors.textMuted, fontSize: 11, marginTop: 2 },
  delBtn: { position: 'absolute', top: 8, right: 8 },
  empty: { alignItems: 'center', paddingVertical: Spacing.xxl * 2, gap: Spacing.sm },
  emptyT: { color: Colors.textSecondary, fontSize: 15, ...Fonts.medium },
  emptyH: { color: Colors.textMuted, fontSize: 12 },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', paddingHorizontal: Spacing.lg },
  modal: { backgroundColor: Colors.bgElevated, borderRadius: Radius.lg, padding: Spacing.lg, borderWidth: 1, borderColor: Colors.border },
  modalTitle: { fontSize: 18, color: Colors.text, ...Fonts.bold, marginBottom: Spacing.md },
  err: { color: Colors.danger, fontSize: 13, marginBottom: Spacing.sm },
  lbl: { color: Colors.textSecondary, fontSize: 11, ...Fonts.medium, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 4, marginTop: Spacing.sm },
  inp: { backgroundColor: Colors.bgInput, color: Colors.text, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border, padding: Spacing.sm, fontSize: 14, height: 44 },
  photoPicker: { height: 120, backgroundColor: Colors.bgInput, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border, justifyContent: 'center', alignItems: 'center', marginTop: 4, overflow: 'hidden' },
  photoPreview: { width: '100%', height: '100%' },
  photoHint: { color: Colors.textMuted, fontSize: 12, marginTop: 4 },
  acts: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: Spacing.lg, gap: Spacing.sm },
  cancelBtn: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border },
  cancelTxt: { color: Colors.textSecondary, ...Fonts.medium },
  submitBtn: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: Radius.md, backgroundColor: Colors.primary },
  submitTxt: { color: '#fff', ...Fonts.semibold },
});
