import { test, expect, type Page } from "@playwright/test";
import { CLIENT, setupApp } from "./_mock";

// Route-smoke tests for the refactored Next.js app: prove the newly-split routes render, that the
// index routes redirect to their default tab, that legacy hash links land on the right route, that
// tab-button navigation updates the URL, and that the browser Back button works.
//
// SAFETY: every test installs auth + an API interceptor pointed at the DEAD local base (see _mock.ts)
// and an external-request guard. No request ever reaches api.tryholdslot.com or any real host —
// asserted explicitly at the end of each console test via the offenders array.

let offenders: string[];

test.beforeEach(async ({ page }) => {
  offenders = await setupApp(page);
});

function expectNoExternalRequests() {
  expect(offenders, `requests left the local sandbox: ${offenders.join(", ")}`).toEqual([]);
}

// Wait until the SPA settles on the expected path (redirects + router.push are client-side).
async function expectPath(page: Page, suffix: string) {
  await expect.poll(() => new URL(page.url()).pathname + new URL(page.url()).search).toBe(suffix);
}

// -------------------------------------------------------------------------------------------------
// 3 · Public-route sanity baseline
// -------------------------------------------------------------------------------------------------
test("login renders (public-route baseline)", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.getByPlaceholder("you@company.com")).toBeVisible();
  expectNoExternalRequests();
});

// -------------------------------------------------------------------------------------------------
// 1 · client-status (approval / booking / feedback)
// -------------------------------------------------------------------------------------------------
test.describe("client-status routes", () => {
  test("index redirects to /approval and shows the sendout template + status log", async ({
    page,
  }) => {
    await page.goto(`/${CLIENT}/client-status`);
    await expectPath(page, `/${CLIENT}/client-status/approval`);
    await expect(page.getByRole("heading", { name: "Sendout template" })).toBeVisible();
    await expect(
      page.getByText("Every approval request and how the client responded")
    ).toBeVisible();
    expectNoExternalRequests();
  });

  test("each tab renders its own content", async ({ page }) => {
    await page.goto(`/${CLIENT}/client-status/approval`);
    await expect(page.getByRole("heading", { name: "Sendout template" })).toBeVisible();

    await page.goto(`/${CLIENT}/client-status/booking`);
    // Booking status log — its description is unique to this tab.
    await expect(
      page.getByText("Each prospect", { exact: false }).first()
    ).toBeVisible();
    await expect(page.getByText("suggested meeting time", { exact: false })).toBeVisible();

    await page.goto(`/${CLIENT}/client-status/feedback`);
    await expect(page.getByRole("heading", { name: "Feedback history" })).toBeVisible();
    await expect(page.getByText("Ratings and comments returned by prospects")).toBeVisible();
    expectNoExternalRequests();
  });

  test("topbar tab buttons navigate and Back returns to the previous tab", async ({ page }) => {
    await page.goto(`/${CLIENT}/client-status/approval`);
    await expect(page.getByRole("heading", { name: "Sendout template" })).toBeVisible();

    // Tabs are <button>s portaled into the topbar.
    await page.getByRole("button", { name: "Booking Status" }).click();
    await expectPath(page, `/${CLIENT}/client-status/booking`);
    await expect(page.getByText("suggested meeting time", { exact: false })).toBeVisible();

    await page.getByRole("button", { name: "Meeting Feedback" }).click();
    await expectPath(page, `/${CLIENT}/client-status/feedback`);
    await expect(page.getByRole("heading", { name: "Feedback history" })).toBeVisible();

    // Back → booking (the previous history entry).
    await page.goBack();
    await expectPath(page, `/${CLIENT}/client-status/booking`);
    await expect(page.getByText("suggested meeting time", { exact: false })).toBeVisible();
    expectNoExternalRequests();
  });

  test("legacy hash #booking lands on /booking", async ({ page }) => {
    await page.goto(`/${CLIENT}/client-status#booking`);
    await expectPath(page, `/${CLIENT}/client-status/booking`);
    await expect(page.getByText("suggested meeting time", { exact: false })).toBeVisible();
    expectNoExternalRequests();
  });
});

// -------------------------------------------------------------------------------------------------
// 2 · workspace (brief / list / batches / campaign / replies / summaries / billing)
// -------------------------------------------------------------------------------------------------
// A stable, load-independent element per tab (avoids brittle coupling to async-fetched data).
const WORKSPACE_TABS: { key: string; assert: (page: Page) => Promise<void> }[] = [
  {
    key: "brief",
    assert: async (page) =>
      void (await expect(page.getByText("Company & Product Basics")).toBeVisible()),
  },
  {
    key: "list",
    assert: async (page) =>
      void (await expect(
        page.getByRole("heading", { name: "Find companies likely to buy" })
      ).toBeVisible()),
  },
  {
    key: "batches",
    assert: async (page) =>
      void (await expect(page.getByText("Batch 1").first()).toBeVisible()),
  },
  {
    key: "campaign",
    // The campaign selector + the "Edit campaign name" input are always rendered; assert the input
    // (a real visible element, unlike <option>s which Playwright treats as hidden).
    assert: async (page) =>
      void (await expect(page.getByRole("textbox", { name: "Edit campaign name" })).toBeVisible()),
  },
  {
    key: "replies",
    // The reply-queue header badge ("All handled" / "N awaiting review") is always present.
    assert: async (page) =>
      void (await expect(
        page.getByText(/awaiting review|All handled/).first()
      ).toBeVisible()),
  },
  {
    key: "summaries",
    assert: async (page) =>
      void (await expect(page.getByText("Meeting summaries, newest first")).toBeVisible()),
  },
  {
    key: "billing",
    assert: async (page) =>
      void (await expect(page.getByText("Meetings billed").first()).toBeVisible()),
  },
];

test.describe("workspace routes", () => {
  test("index redirects to /brief", async ({ page }) => {
    await page.goto(`/${CLIENT}/workspace`);
    await expectPath(page, `/${CLIENT}/workspace/brief`);
    await expect(page.getByText("Company & Product Basics")).toBeVisible();
    expectNoExternalRequests();
  });

  test("each of the 7 tab routes renders without error", async ({ page }) => {
    for (const { key, assert } of WORKSPACE_TABS) {
      await page.goto(`/${CLIENT}/workspace/${key}`);
      await expectPath(page, `/${CLIENT}/workspace/${key}`);
      await assert(page);
    }
    expectNoExternalRequests();
  });

  test("tab-button navigation updates the URL and Back works", async ({ page }) => {
    await page.goto(`/${CLIENT}/workspace/brief`);
    await expect(page.getByText("Company & Product Basics")).toBeVisible();

    // Tabs are <button>s portaled into the topbar; labels come from TABS in lib/workspace/constants.
    await page.getByRole("button", { name: "Approval Batches" }).click();
    await expectPath(page, `/${CLIENT}/workspace/batches`);
    await expect(page.getByText("Batch 1").first()).toBeVisible();

    await page.getByRole("button", { name: "Billing Ledger" }).click();
    await expectPath(page, `/${CLIENT}/workspace/billing`);
    await expect(page.getByText("Meetings billed").first()).toBeVisible();

    // Back → batches.
    await page.goBack();
    await expectPath(page, `/${CLIENT}/workspace/batches`);
    await expect(page.getByText("Batch 1").first()).toBeVisible();
    expectNoExternalRequests();
  });

  test("legacy hash #batches lands on /batches", async ({ page }) => {
    await page.goto(`/${CLIENT}/workspace#batches`);
    await expectPath(page, `/${CLIENT}/workspace/batches`);
    await expect(page.getByText("Batch 1").first()).toBeVisible();
    expectNoExternalRequests();
  });

  test("deep-link ?batch=Batch 3#batches lands on /batches with the query preserved", async ({
    page,
  }) => {
    await page.goto(`/${CLIENT}/workspace?batch=Batch%203#batches`);
    // The index redirect preserves location.search, so the query survives onto the batches route.
    await expect
      .poll(() => new URL(page.url()).pathname)
      .toBe(`/${CLIENT}/workspace/batches`);
    await expect
      .poll(() => new URL(page.url()).searchParams.get("batch"))
      .toBe("Batch 3");
    await expect(page.getByText("Batch 3").first()).toBeVisible();
    expectNoExternalRequests();
  });
});
