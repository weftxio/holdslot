// The Prospect-List data layer (2.4 Stage 2), lifted verbatim from list/page.tsx. Owns the feed
// state (companies · prospects · sourcing docs · ICPs · research spec · master departments) + the
// editable rubric draft it seeds from the loaded doc, the two reloads, and the client-keyed hydrate
// effect. The hydrate also sets `clientRef` (shared with the page's handlers) and — because the App
// Router can't remount this page on the [client] param — the PAGE keeps its own client-reset effect
// for the selection/filter/in-flight state that stays there; this hook only touches the feed.
import { useEffect, useState, type MutableRefObject } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/components/Toast";
import {
  type CompanyApi,
  type FacetOption,
  type ProspectApi,
  type ResearchSpecResult,
  type SourcingDocList,
  getPeopleDepartments,
  getResearchSpec,
  getSourcingDocs,
  listCompanies,
  listIcps,
  listProspects,
} from "@/lib/api";
import type { Icp } from "@/lib/workspace/types";
import { apiToIcp } from "@/lib/workspace/constants";

export function useListData(client: string, clientRef: MutableRefObject<string>) {
  const qc = useQueryClient();
  const toast = useToast();

  // ICPs + research spec — loaded locally on mount: icpNameById/the fIcp filter/ICP labels need
  // `icps`, and the scope-override `effectiveScope` needs `spec`. Additive to the list load below.
  const [icps, setIcps] = useState<Icp[]>(() => {
    const cached = qc.getQueryData<Awaited<ReturnType<typeof listIcps>>>(["icps", client]);
    return cached ? cached.map(apiToIcp) : [];
  });
  const [spec, setSpec] = useState<ResearchSpecResult | null>(() => {
    const cached = qc.getQueryData<Awaited<ReturnType<typeof getResearchSpec>>>([
      "research-spec",
      client,
    ]);
    return cached?.latest ?? null;
  });
  // Prospect list (Phase C — live). Prospects, sourcing docs, and the round-history scoreboard
  // are loaded from the API; selection is by prospect id (in the page).
  const [prospects, setProspects] = useState<ProspectApi[]>(
    () => qc.getQueryData<{ items: ProspectApi[] }>(["prospects", client])?.items ?? []
  );
  const [companies, setCompanies] = useState<CompanyApi[]>(
    () => qc.getQueryData<{ items: CompanyApi[] }>(["companies", client])?.items ?? []
  );
  const [prospectsLoading, setProspectsLoading] = useState(
    () => !qc.getQueryData(["prospects", client])
  );
  const [companiesLoading, setCompaniesLoading] = useState(
    () => !qc.getQueryData(["companies", client])
  );
  const [docs, setDocs] = useState<SourcingDocList | null>(null);
  const [rubricDraft, setRubricDraft] = useState("");
  const [masterDepts, setMasterDepts] = useState<FacetOption[]>([]); // 14 masters, from the backend

  async function reloadProspects() {
    setProspectsLoading(true);
    try {
      // Let errors propagate — a failed reload must surface, never silently blank the list
      // (which reads as "no prospects" and tempts a re-import / re-spend).
      const { items: ps } = await listProspects(client);
      if (clientRef.current !== client) return; // client switched mid-flight — drop stale data
      setProspects(ps);
      // N11 — do NOT wipe the people selection on every reload (a Reveal & score reload blew away
      // the operator's ticks). The prune effect drops only now-excluded ids; ghost ids for removed
      // rows are harmless (selectedProspects filters against the live list). Mirrors reloadCompanies.
      qc.setQueryData(["prospects", client], { items: ps }); // keep the nav cache fresh
    } catch (e) {
      if (clientRef.current === client) {
        toast(e instanceof Error ? e.message : "Couldn’t refresh prospects", "warn");
      }
    } finally {
      if (clientRef.current === client) setProspectsLoading(false);
    }
  }

  async function reloadCompanies() {
    setCompaniesLoading(true);
    try {
      const { items: cs } = await listCompanies(client);
      if (clientRef.current !== client) return;
      setCompanies(cs);
      qc.setQueryData(["companies", client], { items: cs }); // keep the nav cache fresh
    } catch (e) {
      if (clientRef.current === client) {
        toast(e instanceof Error ? e.message : "Couldn’t refresh companies", "warn");
      }
    } finally {
      if (clientRef.current === client) setCompaniesLoading(false);
    }
  }

  // Hydrate companies, the prospect list, and sourcing docs for this client (+ ICPs / research spec /
  // master departments). The page owns the per-client UI reset; this effect owns the feed + clientRef.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!client) return;
    clientRef.current = client;
    let alive = true;
    // Show the list spinner only when there's nothing cached for this client; a warm tab-return
    // renders the cached rows immediately (the fetchQuery calls below resolve from cache, no request).
    setCompaniesLoading(!qc.getQueryData(["companies", client]));
    setProspectsLoading(!qc.getQueryData(["prospects", client]));
    (async () => {
      try {
        // fetchQuery serves the cached payload when fresh (instant, no request) and refetches in the
        // background when stale; the cache lives above the routes, so this is what frees a tab-switch
        // from a full reload. The lists' free DB reads are safe to background-revalidate (no credits).
        const [ps, cs, dl, depts, ics, rs] = await Promise.all([
          qc.fetchQuery({ queryKey: ["prospects", client], queryFn: () => listProspects(client) }),
          qc.fetchQuery({ queryKey: ["companies", client], queryFn: () => listCompanies(client) }),
          qc.fetchQuery({
            queryKey: ["sourcing-docs", client],
            queryFn: () => getSourcingDocs(client),
          }),
          qc
            .fetchQuery({
              queryKey: ["people-departments", client],
              queryFn: () => getPeopleDepartments(client),
            })
            .catch(() => [] as FacetOption[]), // non-fatal: subs-only view
          qc
            .fetchQuery({ queryKey: ["icps", client], queryFn: () => listIcps(client) })
            .catch(() => null),
          qc
            .fetchQuery({
              queryKey: ["research-spec", client],
              queryFn: () => getResearchSpec(client),
            })
            .catch(() => null),
        ]);
        if (!alive) return;
        setProspects(ps.items);
        setCompanies(cs.items);
        setDocs(dl);
        setRubricDraft(dl?.company_fit?.body ?? "");
        setMasterDepts(depts);
        if (ics) setIcps(ics.map(apiToIcp));
        if (rs) setSpec(rs.latest);
      } catch (e) {
        if (alive) toast(e instanceof Error ? e.message : "Couldn’t load prospects", "warn");
      } finally {
        if (alive) {
          setCompaniesLoading(false);
          setProspectsLoading(false);
        }
      }
    })();
    return () => {
      alive = false;
    };
    // qc (QueryClient) and toast (useCallback) are stable, so the effect still only re-runs on a
    // client change.
  }, [client, clientRef, qc, toast]);
  /* eslint-enable react-hooks/set-state-in-effect */

  return {
    icps,
    spec,
    prospects,
    companies,
    prospectsLoading,
    companiesLoading,
    docs,
    setDocs,
    rubricDraft,
    setRubricDraft,
    masterDepts,
    reloadProspects,
    reloadCompanies,
  };
}
