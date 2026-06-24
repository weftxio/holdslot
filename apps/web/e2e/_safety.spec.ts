import { test, expect } from "@playwright/test";
import { CLIENT, setupApp, API_BASE } from "./_mock";

// Hard safety audit: log EVERY hostname any page in the suite contacts, and assert the app actually
// issued its API calls to the dead 127.0.0.1:9876 base (intercepted), never to api.tryholdslot.com.
test("safety: all requests stay local; API calls target the dead mocked base", async ({ page }) => {
  await setupApp(page);
  const hosts = new Set<string>();
  const apiPaths: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    hosts.add(`${u.protocol}//${u.host}`);
    if (r.url().startsWith(API_BASE)) apiPaths.push(`${r.method()} ${u.pathname}`);
  });
  // Visit a console route that fans out API calls (list = most endpoints) + the brief.
  await page.goto(`/${CLIENT}/workspace/list`);
  await expect(page.getByRole("heading", { name: "Find companies likely to buy" })).toBeVisible();
  await page.goto(`/${CLIENT}/workspace/brief`);
  await expect(page.getByText("Company & Product Basics")).toBeVisible();

  console.log("HOSTS CONTACTED:", JSON.stringify([...hosts].sort()));
  console.log("API CALLS (to dead mocked base):", JSON.stringify([...new Set(apiPaths)].sort(), null, 2));

  // No host other than the local dev server + the dead mocked API base may appear.
  const allowed = new Set(["http://localhost:3100", API_BASE]);
  for (const h of hosts) expect(allowed.has(h), `unexpected host contacted: ${h}`).toBe(true);
  // Prove the app DID call its API (so the mock is what shielded prod), and it hit /me.
  expect(apiPaths.some((p) => p.endsWith("/me"))).toBe(true);
});
