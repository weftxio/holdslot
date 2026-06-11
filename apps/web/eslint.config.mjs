import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

// Flat config (ESLint 10 + Next 16). Replaces the legacy .eslintrc.json
// `{ "extends": "next/core-web-vitals" }`.
const eslintConfig = [
  { ignores: [".next/**", "node_modules/**", "out/**"] },
  ...nextCoreWebVitals,
  {
    rules: {
      // These components deliberately read browser-only state (window.location
      // hash / search params, localStorage) inside an empty-dep useEffect to
      // defer it past SSR and avoid hydration mismatches — the rule's own
      // "synchronize with external systems" exception. Lazy useState() would
      // run server-side where window/localStorage are undefined. Keep as a
      // warning so genuinely-new violations still surface.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default eslintConfig;
