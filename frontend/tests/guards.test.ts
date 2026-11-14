import { describe, expect, it } from "vitest";
import example from "../../contracts/observation.example.json";
import { isHealthObservation } from "../src/domain/guards";
import { makeObservation } from "./helpers";

describe("isHealthObservation", () => {
  it("accepts the shared contract example produced from the backend model", () => {
    expect(isHealthObservation(example)).toBe(true);
  });

  it("accepts a well-formed observation", () => {
    expect(isHealthObservation(makeObservation())).toBe(true);
  });

  it("rejects wrong schema versions, unknown modules and unknown origins", () => {
    expect(isHealthObservation({ ...makeObservation(), schema_version: 2 })).toBe(false);
    expect(isHealthObservation({ ...makeObservation(), module: "dental" })).toBe(false);
    const base = makeObservation();
    expect(
      isHealthObservation({ ...base, provenance: { ...base.provenance, origin: "guessed" } }),
    ).toBe(false);
  });

  it("rejects non-finite values and non-objects", () => {
    expect(isHealthObservation({ ...makeObservation(), value: Number.NaN })).toBe(false);
    expect(isHealthObservation(null)).toBe(false);
    expect(isHealthObservation([])).toBe(false);
    expect(isHealthObservation("x")).toBe(false);
  });
});
