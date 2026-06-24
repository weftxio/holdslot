"use client";
import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import type { StatusTabKey } from "@/components/console/StatusTab";

const VALID: StatusTabKey[] = ["approval", "booking", "feedback"];

// The Client Action tabs are now real routes (./approval, ./booking, ./feedback). This index
// redirects to the default tab, and translates legacy hash links (/client-status#booking) that may
// live in old emails/bookmarks to the matching route.
export default function ClientStatusIndex() {
  const { client } = useParams<{ client: string }>();
  const router = useRouter();
  useEffect(() => {
    const h = location.hash.slice(1) as StatusTabKey;
    const target = VALID.includes(h) ? h : "approval";
    router.replace(`/${client}/client-status/${target}`);
  }, [client, router]);
  return null;
}
