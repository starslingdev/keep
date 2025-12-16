import "@/app/globals.css";

export const metadata = {
  title: "Continuum - AI-Powered Incident Analysis",
  description: "Intelligent Root Cause Analysis for faster incident resolution",
};

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <body className="min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}

