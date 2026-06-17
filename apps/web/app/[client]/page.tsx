import { redirect } from "next/navigation";
import { DEFAULT_CLIENT_PAGE } from "@/lib/client";

export default async function ClientIndex({ params }: { params: Promise<{ client: string }> }) {
  const { client } = await params;
  redirect(`/${client}/${DEFAULT_CLIENT_PAGE}`);
}
