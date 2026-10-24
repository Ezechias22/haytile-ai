import React from 'react';
import {
  ScrollView,
  View,
  Text,
  Pressable,
  TextInput,
  StyleSheet,
  type TextInputProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { useApp } from './client';
export const theme = {
  bg: '#0e0e17',
  panel: '#191522',
  line: '#3a2d47',
  text: '#f3edf8',
  muted: '#a593b7',
  accent: '#b491f7',
};
export function Screen({ children }: { children: React.ReactNode }) {
  const { locale } = useApp();
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.bg }}
      contentContainerStyle={{
        padding: 22,
        paddingBottom: 50,
        direction: locale === 'ar' ? 'rtl' : 'ltr',
      }}
      keyboardShouldPersistTaps="handled"
    >
      {children}
    </ScrollView>
  );
}
export function Heading({ children }: { children: React.ReactNode }) {
  return <Text style={s.heading}>{children}</Text>;
}
export function Copy({ children }: { children: React.ReactNode }) {
  return <Text style={s.copy}>{children}</Text>;
}
export function Card({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return <View style={[s.card, style]}>{children}</View>;
}
export function Button({
  title,
  onPress,
  disabled = false,
  secondary = false,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        s.button,
        secondary && s.secondary,
        { opacity: disabled ? 0.35 : pressed ? 0.7 : 1 },
      ]}
    >
      <Text style={[s.buttonText, secondary && { color: theme.text }]}>{title}</Text>
    </Pressable>
  );
}
export function Input({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={{ marginBottom: 16 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor="#776582"
        {...props}
        style={[
          s.input,
          props.multiline && { minHeight: 170, textAlignVertical: 'top' },
          props.style,
        ]}
      />
    </View>
  );
}
export function Chips({
  items,
  value,
  onChange,
}: {
  items: Record<string, string>;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <View style={s.chips}>
      {Object.entries(items).map(([k, v]) => (
        <Pressable
          accessibilityRole="button"
          key={k}
          onPress={() => onChange(k)}
          style={[s.chip, value === k && { borderColor: theme.accent, backgroundColor: '#362546' }]}
        >
          <Text style={{ color: value === k ? theme.accent : theme.muted, fontSize: 12 }}>{v}</Text>
        </Pressable>
      ))}
    </View>
  );
}
export const s = StyleSheet.create({
  heading: {
    fontSize: 30,
    fontWeight: '700',
    letterSpacing: -1,
    color: theme.text,
    marginBottom: 12,
  },
  copy: { fontSize: 13, lineHeight: 22, color: theme.muted, marginBottom: 18 },
  card: {
    backgroundColor: theme.panel,
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 16,
    padding: 20,
    marginBottom: 18,
  },
  button: {
    backgroundColor: theme.accent,
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
    marginVertical: 6,
  },
  secondary: { backgroundColor: '#2a2038', borderWidth: 1, borderColor: '#533a65' },
  buttonText: { fontSize: 13, fontWeight: '700', color: '#23172e' },
  input: {
    backgroundColor: '#110e1a',
    borderColor: theme.line,
    borderWidth: 1,
    borderRadius: 9,
    color: theme.text,
    fontSize: 14,
    padding: 13,
  },
  label: { fontSize: 12, color: theme.muted, marginBottom: 7 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 20 },
  chip: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.line,
  },
  title: { fontSize: 17, fontWeight: '600', color: theme.text, marginBottom: 7 },
  error: { color: '#f0a4bb', fontSize: 12, lineHeight: 20, marginBottom: 12 },
});
