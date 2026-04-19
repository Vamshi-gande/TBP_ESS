/**
 * Design system tokens for SENTINEL surveillance app.
 * Dark-mode first — matches the tactical surveillance aesthetic.
 */

export const Colors = {
  // Base palette
  bg:           '#080b10',
  bgCard:       '#0f1318',
  bgElevated:   '#161b22',
  bgInput:      '#1c2128',

  // Accent
  primary:      '#3b82f6',  // Blue-500
  primaryDim:   '#1e3a5f',
  primaryGlow:  'rgba(59, 130, 246, 0.15)',

  // Semantic
  success:      '#22c55e',
  warning:      '#f59e0b',
  danger:       '#ef4444',
  critical:     '#a855f7',  // Purple for critical zones
  info:         '#06b6d4',

  // Text
  text:         '#e6edf3',
  textSecondary:'#8b949e',
  textMuted:    '#484f58',

  // Border
  border:       '#21262d',
  borderFocus:  '#3b82f6',

  // Zone colors (match backend)
  zoneGreen:    '#22c55e',
  zoneAmber:    '#f59e0b',
  zoneRed:      '#ef4444',
  zoneCritical: '#a855f7',
};

export const Fonts = {
  regular:   { fontFamily: 'System', fontWeight: '400' },
  medium:    { fontFamily: 'System', fontWeight: '500' },
  semibold:  { fontFamily: 'System', fontWeight: '600' },
  bold:      { fontFamily: 'System', fontWeight: '700' },
};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const Radius = {
  sm: 6,
  md: 10,
  lg: 16,
  xl: 24,
  full: 999,
};

export const Shadow = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 5,
  },
  glow: {
    shadowColor: Colors.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
  },
};
