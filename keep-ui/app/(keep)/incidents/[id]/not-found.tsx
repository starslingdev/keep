"use client";

import { Title, Button, Subtitle } from "@tremor/react";
import Image from "next/image";
import { useRouter } from "next/navigation";

export default function NotFound() {
  const router = useRouter();
  return (
    <div className="flex flex-col items-center justify-center h-[calc(100vh-10rem)]">
      <Title>Incident not found</Title>
      <Subtitle>
        The incident you&apos;re looking for doesn&apos;t exist or has been deleted.
      </Subtitle>
      <Image src="/keep.svg" alt="Continuum" width={150} height={150} />
      <Button
        onClick={() => {
          router.push("/incidents");
        }}
        color="violet"
        variant="secondary"
      >
        Go to all incidents
      </Button>
    </div>
  );
}
