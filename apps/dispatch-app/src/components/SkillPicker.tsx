import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SymbolView } from "expo-symbols";
import { getSkills, type Skill } from "../api/skills";
import { pickerBaseStyles } from "../styles/pickerStyles";

interface SkillPickerProps {
  onSelect: (skill: Skill) => void;
  onClose: () => void;
}

export function SkillPicker({ onSelect, onClose }: SkillPickerProps) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const all = await getSkills();
        if (!cancelled) {
          const filtered = all.filter((s) => s.description.length > 0);
          setSkills(filtered);
        }
      } catch (err) {
        console.error("[SkillPicker] Failed to load skills:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const filteredSkills = useMemo(() => {
    if (!query.trim()) return skills;
    const q = query.toLowerCase();
    return skills.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q)
    );
  }, [skills, query]);

  const renderSkill = useCallback(
    ({ item }: { item: Skill }) => {
      const preview = Array.from(item.description).length > 80
        ? Array.from(item.description).slice(0, 80).join("") + "…"
        : item.description;

      return (
        <Pressable
          style={({ pressed }) => [
            pickerBaseStyles.row,
            pressed && pickerBaseStyles.rowPressed,
          ]}
          onPress={() => onSelect(item)}
          accessibilityRole="button"
          accessibilityLabel={`${item.name}: ${item.description}`}
        >
          <View style={[pickerBaseStyles.iconCircle, { backgroundColor: "#7c3aed22" }]}>
            <SymbolView name="hammer.fill" tintColor="#a78bfa" size={16} />
          </View>
          <View style={pickerBaseStyles.itemInfo}>
            <Text style={pickerBaseStyles.itemName} numberOfLines={1}>
              /{item.name}
            </Text>
            <Text style={pickerBaseStyles.preview} numberOfLines={1}>
              {preview}
            </Text>
          </View>
        </Pressable>
      );
    },
    [onSelect]
  );

  return (
    <View style={[pickerBaseStyles.container, localStyles.taller]}>
      <View style={pickerBaseStyles.header}>
        <Text style={pickerBaseStyles.title}>Choose a skill</Text>
        <Pressable
          onPress={onClose}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel="Close skill picker"
        >
          <SymbolView name="xmark" tintColor="#a1a1aa" size={16} weight="semibold" />
        </Pressable>
      </View>
      <View style={localStyles.searchContainer}>
        <SymbolView name="magnifyingglass" tintColor="#52525b" size={14} />
        <TextInput
          style={localStyles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search skills…"
          placeholderTextColor="#52525b"
          autoCorrect={false}
          autoCapitalize="none"
          returnKeyType="done"
          accessibilityLabel="Search skills"
        />
        {query.length > 0 ? (
          <Pressable onPress={() => setQuery("")} hitSlop={8} accessibilityRole="button" accessibilityLabel="Clear search">
            <SymbolView name="xmark.circle.fill" tintColor="#52525b" size={16} />
          </Pressable>
        ) : null}
      </View>
      {loading ? (
        <View style={pickerBaseStyles.loadingContainer}>
          <Text style={pickerBaseStyles.loadingText}>Loading skills…</Text>
        </View>
      ) : filteredSkills.length === 0 ? (
        <View style={pickerBaseStyles.loadingContainer}>
          <Text style={pickerBaseStyles.loadingText}>
            {query ? "No matching skills" : "No skills found"}
          </Text>
        </View>
      ) : (
        <FlatList
          data={filteredSkills}
          keyExtractor={(item) => item.name}
          renderItem={renderSkill}
          style={pickerBaseStyles.list}
          showsVerticalScrollIndicator
          keyboardShouldPersistTaps="handled"
        />
      )}
    </View>
  );
}

const localStyles = StyleSheet.create({
  taller: {
    maxHeight: 320,
  },
  searchContainer: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#27272a",
    borderRadius: 10,
    marginHorizontal: 12,
    marginTop: 8,
    marginBottom: 4,
    paddingHorizontal: 10,
    gap: 6,
    height: 36,
  },
  searchInput: {
    flex: 1,
    color: "#fafafa",
    fontSize: 14,
    paddingVertical: 0,
  },
});
