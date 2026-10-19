import { expect, test } from "@playwright/test";

test("the landing page offers both views", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("enter-store").click();
  await expect(page).toHaveURL(/\/shop$/);
  await page.goto("/");
  await page.getByTestId("enter-ops").click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("a customer order is picked by robots and ships", async ({ page }) => {
  await page.goto("/shop");
  await expect(page.getByTestId("product-MUG-001")).toBeVisible();

  await page.getByRole("button", { name: "Add Ceramic Mug to cart" }).click();
  await page.getByRole("button", { name: "Add Cast Iron Pan to cart" }).click();
  await expect(page.getByTestId("cart-count")).toHaveText("2");
  // Dawn-style "added" popover, then the cart drawer.
  await expect(page.getByRole("status")).toContainText("Item added to your cart");
  await page.getByTestId("cart-button").click();
  await expect(page.getByRole("dialog", { name: "Your cart" })).toBeVisible();
  await expect(page.getByTestId("cart-total")).toContainText("58.98");

  await page.getByLabel("Email for order updates").fill("e2e@example.com");
  await page.getByRole("button", { name: "Place order" }).click();

  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]{36}$/);
  const steps = page.getByTestId("order-steps").locator("li");
  await expect(steps.nth(0)).toHaveAttribute("data-done", "true");
  // The simulation runs at 40 ms/tick in e2e, so shipping takes a few seconds.
  await expect(steps.nth(3)).toHaveAttribute("data-done", "true", { timeout: 45_000 });
  await expect(page.getByText("This order has shipped.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your order has shipped" })).toBeVisible();

  // The cart was consumed by checkout.
  await expect(page.getByTestId("cart-count")).toHaveText("0");
});

test("the last unit can only be bought once", async ({ page, request }) => {
  const api = "http://localhost:8100";
  const products = await (await request.get(`${api}/api/products`)).json();
  const puzzle = products.find((p: { sku: string }) => p.sku === "PZL-024");
  expect(puzzle.stock).toBe(1);

  const buy = (i: number) =>
    request.post(`${api}/api/orders`, {
      data: { customer_email: `racer${i}@example.com`, items: [{ product_id: puzzle.id, quantity: 1 }] },
    });
  const results = await Promise.all([0, 1, 2, 3, 4].map(buy));
  const codes = results.map((r) => r.status()).sort();
  expect(codes).toEqual([201, 409, 409, 409, 409]);

  await page.goto("/shop");
  await expect(page.getByTestId("product-PZL-024")).toContainText("Sold out");
});

test("dashboard streams live robot state", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByTestId("feed-status")).toHaveText(/Live/);
  await expect(page.getByTestId("robot-0")).toBeVisible();
  await expect(page.getByTestId("robot-5")).toBeVisible();
});

test("pathfinding lab compares algorithms", async ({ page }) => {
  await page.goto("/pathfinding");
  // Wait for the search result itself, not just for the cell to render.
  await expect(page.getByTestId("path-expanded")).toHaveText(/^\d+$/);
  await expect(page.getByTestId("path-cost")).toHaveText(/^\d+$/);
  const astar = Number(await page.getByTestId("path-expanded").textContent());
  await page.getByRole("button", { name: "Dijkstra" }).click();
  await expect(page.getByTestId("path-expanded")).not.toHaveText(String(astar));
  const dijkstra = Number(await page.getByTestId("path-expanded").textContent());
  expect(astar).toBeLessThan(dijkstra);
});
