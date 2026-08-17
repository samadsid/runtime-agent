jest.mock("expo-application", () => ({ nativeApplicationVersion: "0.1.0", nativeBuildVersion: "test" }));
jest.mock("@expo/vector-icons/Ionicons", () => {
  const React = require("react");
  const { Text } = require("react-native");
  return ({ name, accessibilityLabel }: { name: string; accessibilityLabel?: string }) => React.createElement(Text, { accessibilityLabel }, name);
});
