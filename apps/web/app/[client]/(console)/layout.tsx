import { ConsoleShell } from "@/components/console/ConsoleShell";

export default async function ConsoleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ client: string }>;
}) {
  const { client } = await params;
  return <ConsoleShell slug={client}>{children}</ConsoleShell>;
}
