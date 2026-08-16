import { fireEvent, render } from "@testing-library/react-native";
import { Button, StatusBadge } from ".";

test("status badges expose a text status instead of color alone", async () => {
  const screen = await render(<StatusBadge status="OUT_FOR_DELIVERY" />);
  expect(screen.getByLabelText("Status: Out for delivery")).toBeTruthy();
  expect(screen.getByText("Out for delivery")).toBeTruthy();
});

test("button exposes disabled accessibility state and prevents presses", async () => {
  const onPress = jest.fn();
  const screen = await render(<Button label="Confirm" disabled onPress={onPress} />);
  fireEvent.press(screen.getByRole("button", { name: "Confirm" }));
  expect(onPress).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Confirm" }).props.accessibilityState).toEqual({ disabled: true });
});
