import { fireEvent, render } from "@testing-library/react-native";
import type { PropsWithChildren } from "react";

import { Button, StatusBadge, ThemeProvider } from "@/design-system";
import { presentOrderStatus } from "@/features/presentation/status";

function Wrapper({ children }: PropsWithChildren) { return <ThemeProvider>{children}</ThemeProvider>; }

test("status badges expose a text status instead of color alone", async () => {
  const screen = await render(<StatusBadge {...presentOrderStatus("OUT_FOR_DELIVERY")} />, { wrapper: Wrapper });
  expect(screen.getByLabelText("Status: Out for delivery")).toBeTruthy();
  expect(screen.getByText("Out for delivery")).toBeTruthy();
});

test("button exposes disabled accessibility state and prevents presses", async () => {
  const onPress = jest.fn();
  const screen = await render(<Button label="Confirm" disabled onPress={onPress} />, { wrapper: Wrapper });
  fireEvent.press(screen.getByRole("button", { name: "Confirm" }));
  expect(onPress).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Confirm" }).props.accessibilityState).toEqual({ disabled: true, busy: false });
});
