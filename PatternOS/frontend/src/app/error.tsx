"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error(error);
  }, [error]);

  return (
    <div className="max-w-2xl mx-auto pt-6">
      <Card>
        <CardHeader>
          <CardTitle>Something went wrong</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-muted-foreground">
            Don’t worry — your data is safe. This is usually caused by a temporary connection issue.
          </div>
          <div className="flex gap-2">
            <Button onClick={() => reset()}>Try again</Button>
            <Button variant="outline" onClick={() => (window.location.href = "/status")}>
              Open system status
            </Button>
          </div>
          <div className="text-xs text-muted-foreground break-words">
            {error.message}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

