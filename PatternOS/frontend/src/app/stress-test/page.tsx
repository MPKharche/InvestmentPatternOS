"use client";
import { useEffect, useState } from "react";
import { stressTestApi, type PortfolioOut } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Upload, FileText } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import Link from "next/link";

export default function StressTestPortfoliosPage() {
  const [portfolios, setPortfolios] = useState<PortfolioOut[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    loadPortfolios();
  }, []);

  const loadPortfolios = async () => {
    setLoading(true);
    try {
      const data = await stressTestApi.getPortfolios();
      setPortfolios(data);
    } catch {
      toast.error("Failed to load portfolios");
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePortfolio = () => {
    router.push("/stress-test/portfolio/new");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Loading portfolios...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Portfolios</h1>
        <Button onClick={handleCreatePortfolio}>
          <Upload className="h-4 w-4 mr-2" /> New Portfolio
        </Button>
      </div>

      {portfolios.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No portfolios yet. Create your first portfolio to get started.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Your Portfolios</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Positions</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {portfolios.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <a href={`/stress-test/portfolio/${p.id}`} className="hover:underline">
                        {p.name}
                      </a>
                    </TableCell>
                    <TableCell className="text-xs">{p.positions_json.length} positions</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(p.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="flex gap-2">
                      <Link href={`/stress-test/portfolio/${p.id}`}>
                        <Button variant="outline" size="sm">View</Button>
                      </Link>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => {
                          if (window.confirm("Delete this portfolio?")) {
                            // TODO: implement delete
                            toast.error("Delete not implemented yet");
                          }
                        }}
                      >
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
