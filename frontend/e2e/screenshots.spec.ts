import { expect, test, type Page } from "@playwright/test";

// Regenerates the README screenshots from the real running app:
//   SCREENSHOTS=1 npx playwright test screenshots
// Skipped in normal test runs.
test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to regenerate docs/screenshots");
test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });

const API = "http://localhost:8100";
const OUT = "../docs/screenshots";

async function imagesLoaded(page: Page) {
  await page.waitForFunction(() => [...document.images].every((i) => i.complete && i.naturalWidth > 0));
}

test("capture README screenshots", async ({ page, request }) => {
  test.setTimeout(120_000);
  // Normal speed so robots are mid-route, not teleporting.
  await request.post(`${API}/api/simulation/commands`, { data: { action: "speed", tick_interval_ms: 250 } });

  await page.goto("/");
  await imagesLoaded(page);
  await page.screenshot({ path: `${OUT}/landing.png` });

  await page.goto("/shop");
  await imagesLoaded(page);
  await page.screenshot({ path: `${OUT}/store.png` });

  // A handful of customers order at once so the floor is busy.
  const products = await (await request.get(`${API}/api/products`)).json();
  const ids: number[] = products.slice(0, 12).map((p: { id: number }) => p.id);
  let tracked = "";
  for (let i = 0; i < 6; i++) {
    const res = await request.post(`${API}/api/orders`, {
      data: {
        customer_email: `shot${i}@example.com`,
        items: [
          { product_id: ids[i], quantity: 1 },
          { product_id: ids[i + 6], quantity: 1 },
        ],
      },
    });
    if (i === 0) tracked = (await res.json()).id;
  }

  await page.goto(`/orders/${tracked}`);
  await expect(page.getByRole("heading", { name: /picking|packing/i })).toBeVisible({ timeout: 20_000 });
  await imagesLoaded(page);
  await page.screenshot({ path: `${OUT}/order.png` });

  await page.goto("/dashboard");
  await expect(page.getByTestId("feed-status")).toHaveText(/Live/);
  await page.getByLabel("Show planned paths").check();
  await page.locator("tr[aria-selected]").nth(1).click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/console.png` });

  await page.goto("/pathfinding");
  await expect(page.getByTestId("path-expanded")).toHaveText(/^\d+$/);
  await page.screenshot({ path: `${OUT}/pathfinding.png` });
});
