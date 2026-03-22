import React, { useEffect, useRef } from "react";
import { Animated, StyleSheet, View } from "react-native";

interface RecordingIndicatorProps {
  isActive: boolean;
}

const BAR_COUNT = 4;
const BAR_WIDTH = 3;
const BAR_GAP = 3;
const MAX_HEIGHT = 20;
const MIN_HEIGHT = 4;

/**
 * Animated bars that pulse to indicate active recording.
 */
export function RecordingIndicator({ isActive }: RecordingIndicatorProps) {
  const anims = useRef(
    Array.from({ length: BAR_COUNT }, () => new Animated.Value(MIN_HEIGHT)),
  ).current;

  useEffect(() => {
    if (!isActive) {
      // Reset all bars to minimum
      anims.forEach((a) => a.setValue(MIN_HEIGHT));
      return;
    }

    // Create staggered looping animations
    const animations = anims.map((anim, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * 120),
          Animated.timing(anim, {
            toValue: MAX_HEIGHT,
            duration: 300,
            useNativeDriver: false,
          }),
          Animated.timing(anim, {
            toValue: MIN_HEIGHT,
            duration: 300,
            useNativeDriver: false,
          }),
        ]),
      ),
    );

    const composite = Animated.parallel(animations);
    composite.start();

    return () => {
      composite.stop();
    };
  }, [isActive, anims]);

  return (
    <View style={styles.container}>
      {anims.map((anim, i) => (
        <Animated.View
          key={i}
          style={[
            styles.bar,
            {
              height: anim,
              backgroundColor: isActive ? "#ef4444" : "#52525b",
            },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    height: MAX_HEIGHT,
    gap: BAR_GAP,
  },
  bar: {
    width: BAR_WIDTH,
    borderRadius: BAR_WIDTH / 2,
  },
});
