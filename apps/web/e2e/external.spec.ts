import { test, expect } from "@playwright/test";
import { CLIENT, setupApp } from "./_mock";

// Route-smoke for the 3 external (token) pages — approve / book / feedback. Each renders a valid
// card and an expired state (driven by ?state=expired, read by ExternalShell/useLinkState). These
// pages don't call the API, but setupApp still installs the external-request guard so the suite
// proves nothing escapes the local sandbox here either.

let offenders: string[];

test.beforeEach(async ({ page }) => {
  offenders = await setupApp(page);
});

function expectNoExternalRequests() {
  expect(offenders, `requests left the local sandbox: ${offenders.join(", ")}`).toEqual([]);
}

const TOKEN = "demo-token";
// footBy is rendered only in the valid (non-expired, non-done) state; expiredTitle is the <h1> of
// the expired pane — so each uniquely identifies the state the page settled on.
const EXTERNAL = [
  { route: "approve", footBy: "Sent securely by HoldSlot", expiredTitle: "This link has expired" },
  { route: "book", footBy: "Scheduling by HoldSlot", expiredTitle: "This booking link has expired" },
  {
    route: "feedback",
    footBy: "Feedback by HoldSlot",
    expiredTitle: "This feedback link has expired",
  },
];

test.describe("external token routes", () => {
  for (const { route, footBy, expiredTitle } of EXTERNAL) {
    test(`${route} renders the valid card`, async ({ page }) => {
      await page.goto(`/${CLIENT}/${route}/${TOKEN}`);
      await expect(page.getByText(footBy)).toBeVisible();
      // The expired pane must not be in the DOM in the valid state.
      await expect(page.getByRole("heading", { name: expiredTitle })).toHaveCount(0);
      expectNoExternalRequests();
    });

    test(`${route} renders the expired state via ?state=expired`, async ({ page }) => {
      await page.goto(`/${CLIENT}/${route}/${TOKEN}?state=expired`);
      await expect(page.getByRole("heading", { name: expiredTitle })).toBeVisible();
      expectNoExternalRequests();
    });
  }
});
