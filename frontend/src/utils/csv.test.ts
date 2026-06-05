import { describe, expect, it, vi } from "vitest";
import { serializeCsv } from "./csv";

describe("serializeCsv", () => {
  it("builds header and rows with UTF-8 BOM", () => {
    const csv = serializeCsv(
      [
        { header: "Symbol", value: (r) => r.symbol },
        { header: "Qty", value: (r) => r.qty },
      ],
      [
        { symbol: "BTC-USDT-PERP", qty: 1.5 },
        { symbol: "ETH-USDT-PERP", qty: 2 },
      ]
    );

    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv).toContain("Symbol,Qty");
    expect(csv).toContain("BTC-USDT-PERP,1.5");
    expect(csv).toContain("ETH-USDT-PERP,2");
  });

  it("escapes commas, quotes, and newlines", () => {
    const csv = serializeCsv(
      [{ header: "Note", value: (r) => r.note }],
      [{ note: 'say "hi", world\nnext' }]
    );

    expect(csv).toContain('"say ""hi"", world\nnext"');
  });

  it("renders null and undefined as empty cells", () => {
    const csv = serializeCsv(
      [
        { header: "A", value: () => null },
        { header: "B", value: () => undefined },
        { header: "C", value: () => "ok" },
      ],
      [{}]
    );

    expect(csv.endsWith(",,ok")).toBe(true);
  });
});

describe("exportCsv", () => {
  it("creates a download link and revokes the object URL", async () => {
    const { exportCsv } = await import("./csv");

    const createObjectURL = vi.fn(() => "blob:mock");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", {
      createObjectURL,
      revokeObjectURL,
    });

    const click = vi.fn();
    const anchor = {
      href: "",
      download: "",
      click,
    };
    const appendChild = vi.fn();
    const removeChild = vi.fn();
    vi.stubGlobal("document", {
      createElement: vi.fn(() => anchor),
      body: { appendChild, removeChild },
    });

    exportCsv("test.csv", [{ header: "X", value: () => 1 }], [{}]);

    expect(createObjectURL).toHaveBeenCalled();
    expect(anchor.download).toBe("test.csv");
    expect(click).toHaveBeenCalled();
    expect(removeChild).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");

    vi.unstubAllGlobals();
  });
});
