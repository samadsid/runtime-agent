import { expect, test } from "@playwright/test";

test("continues a browser conversation through FastAPI", async ({ page }) => {
  await page.goto("/");
  const composer = page.getByLabel("Message Commerce Assistant");
  await composer.fill("Mujhe chicken breast chahiye");
  await composer.press("Enter");
  await expect(page.getByText("Available products:")).toBeVisible();
  await expect(page.getByText("1. Chicken Breast - ₹320.00/kg")).toBeVisible();
  await expect(page.getByText("Conversation saved")).toBeVisible();

  await page.reload();
  await expect(page.getByText("1. Chicken Breast - ₹320.00/kg")).toBeVisible();
  await composer.fill("5 kg add kar do");
  await composer.press("Enter");
  await expect(page.getByText("Continued the same conversation.")).toBeVisible();

  await page.getByRole("button", { name: "New chat" }).click();
  await page.getByRole("button", { name: "Start new chat" }).click();
  await expect(page.getByText("Welcome")).toBeVisible();
});
