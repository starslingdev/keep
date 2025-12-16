import { redirect } from "next/navigation";
import { NextRequest } from "next/server";

type RouteContext = {
  params: Promise<{ id: string }>;
};

// This is just a redirect from legacy route
export async function GET(request: NextRequest, context: RouteContext) {
  const params = await context.params;
  redirect(`/incidents/${params.id}/alerts`);
}
