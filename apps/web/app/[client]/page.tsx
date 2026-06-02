import { redirect } from "next/navigation";

export default async function ClientIndex({ params }: { params: Promise<{ client: string }> }) {
  const { client } = await params;
  redirect(`/${client}/overview`);
}
