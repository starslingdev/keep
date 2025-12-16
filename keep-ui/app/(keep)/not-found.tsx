"use client";

import { Title, Button, Subtitle } from "@tremor/react";
import Image from "next/image";
import { useRouter } from "next/navigation";

export default function NotFound() {
  const router = useRouter();
  return (
    <div className="flex flex-col items-center justify-center h-full">
      <Title>404 Page not found</Title>
      <Subtitle>
        The page you&apos;re looking for doesn&apos;t exist or has been moved.
      </Subtitle>
      <Image src="/keep.svg" alt="Continuum" width={150} height={150} />
      <Button
        onClick={() => {
          router.back();
        }}
        color="violet"
        variant="secondary"
      >
        Go back
      </Button>
    </div>
  );
}
