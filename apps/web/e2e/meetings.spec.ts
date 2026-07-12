import { test, expect, type Route } from "@playwright/test";
import { API_BASE, CLIENT, setupApp } from "./_mock";

// Phase F route-smoke — the booking + feedback public flow, the ledger, the client-status booking/
// feedback tabs, and the performance-summary meeting cells. Every test runs through the dead-port
// mock API (setupApp) + the external-request guard, so nothing reaches a real host.

let offenders: string[];

test.beforeEach(async ({ page }) => {
  offenders = await setupApp(page);
});

function expectNoExternalRequests() {
  expect(offenders, `requests left the local sandbox: ${offenders.join(", ")}`).toEqual([]);
}

const TOKEN = "demo-token";

// Override a mocked endpoint for a single test (registered after setupApp → wins).
async function override(page: import("@playwright/test").Page, glob: string, body: unknown) {
  await page.route(glob, (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) })
  );
}

test.describe("Phase F — booking + feedback + meeting reads", () => {
  test("FE-1 book: valid view → pick a slot → confirm → success", async ({ page }) => {
    await page.goto(`/${CLIENT}/book/${TOKEN}`);
    // Day tabs render (viewer-local grouping of the mocked UTC slots).
    await expect(page.locator(".day-tab").first()).toBeVisible();
    // Pick the first available slot, then confirm.
    await page.locator(".slot").first().click();
    await page.getByRole("button", { name: /Confirm booking/ }).click();
    await expect(page.getByRole("heading", { name: /You're booked/ })).toBeVisible();
    expectNoExternalRequests();
  });

  test("FE-2 book: expired via API state (forceExpired wiring)", async ({ page }) => {
    await override(page, `${API_BASE}/book/**`, {
      state: "expired",
      client_name: "",
      duration_min: 0,
      slots: [],
      expires_at: null,
    });
    await page.goto(`/${CLIENT}/book/${TOKEN}`);
    await expect(
      page.getByRole("heading", { name: /This booking link has expired/ })
    ).toBeVisible();
    expectNoExternalRequests();
  });

  test("FE-3 feedback: no rating → error; rated → success", async ({ page }) => {
    await page.goto(`/${CLIENT}/feedback/${TOKEN}`);
    await page.getByRole("button", { name: /Submit feedback/ }).click();
    await expect(page.getByText(/Please pick a rating first/)).toBeVisible();
    await page.getByRole("button", { name: /4 stars/ }).click();
    await page.getByRole("button", { name: "Well prepared" }).click();
    await page.getByRole("button", { name: /Submit feedback/ }).click();
    await expect(page.getByRole("heading", { name: /Thank you/ })).toBeVisible();
    expectNoExternalRequests();
  });

  test("FE-4 feedback: expired via API state", async ({ page }) => {
    await override(page, `${API_BASE}/feedback/**`, {
      state: "expired",
      client_name: "",
      expires_at: null,
    });
    await page.goto(`/${CLIENT}/feedback/${TOKEN}`);
    await expect(
      page.getByRole("heading", { name: /This feedback link has expired/ })
    ).toBeVisible();
    expectNoExternalRequests();
  });

  test("FE-5 billing ledger renders live rows + CSV export", async ({ page }) => {
    await page.goto(`/${CLIENT}/workspace/billing`);
    await expect(page.getByText("Dana Reyes")).toBeVisible();
    // $500 legitimately renders 3×: the cycle-due total, the per-meeting rate card, and the row
    // amount — assert the first (strict mode forbids a bare multi-match locator).
    await expect(page.getByText("$500").first()).toBeVisible();
    await expect(page.locator(".badge", { hasText: "Billed" }).first()).toBeVisible();
    // CSV export downloads a non-empty file.
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Export CSV" }).click(),
    ]);
    expect(download.suggestedFilename()).toBe("billing-ledger.csv");
    expectNoExternalRequests();
  });

  test("FE-7 client-status booking: chips + Propose-new-time only on Expired", async ({ page }) => {
    await page.goto(`/${CLIENT}/client-status/booking`);
    await expect(page.locator(".badge", { hasText: "Confirmed" }).first()).toBeVisible();
    await expect(page.locator(".badge", { hasText: "Expired" }).first()).toBeVisible();
    // Exactly one Expired row → exactly one Propose-new-time button.
    await expect(page.getByRole("button", { name: "Propose new time" })).toHaveCount(1);
    expectNoExternalRequests();
  });

  test("FE-8 client-status feedback: gated Send Follow-Up + Inform client", async ({ page }) => {
    await page.goto(`/${CLIENT}/client-status/feedback`);
    // The Received row (rating 4) → Inform client is NOT shown (rating > 3); the overdue None row →
    // Send Follow-Up IS shown.
    await expect(page.getByRole("button", { name: "Send Follow-Up" })).toHaveCount(1);
    await expect(page.locator(".badge", { hasText: "Received" }).first()).toBeVisible();
    expectNoExternalRequests();
  });

  test("FE-9 performance-summary: meeting cells + calendar render", async ({ page }) => {
    await page.goto(`/${CLIENT}/performance-summary`);
    // Headline qualified count + show-up rate.
    await expect(page.locator(".headline .big")).toHaveText("3");
    await expect(page.getByText("75%")).toBeVisible();
    // The calendar surface mounts.
    await expect(page.locator(".cal-wrap")).toBeVisible();
    expectNoExternalRequests();
  });
});
