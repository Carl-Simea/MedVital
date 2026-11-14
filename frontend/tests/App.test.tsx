import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "../src/App";
import { ObservationStore } from "../src/offline/store";
import { freshDbName, makeObservation } from "./helpers";

describe("App", () => {
  it("shows the four independent health modules and the provenance legend", async () => {
    const name = freshDbName();
    render(<App openStore={() => ObservationStore.open(name)} />);

    for (const title of ["Radiation", "Bone health", "Cardiovascular health", "Behavioral health"]) {
      expect(screen.getByRole("heading", { name: title })).toBeTruthy();
    }
    const legend = screen.getByRole("region", { name: "Data provenance legend" });
    expect(legend.querySelectorAll("[data-origin]")).toHaveLength(3);
    expect(screen.getByText(/not a medical device/i)).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("pending").textContent).toContain("0"));
  });

  it("reads counts and pending uploads from local IndexedDB data", async () => {
    const name = freshDbName();
    const seed = await ObservationStore.open(name);
    await seed.record([makeObservation(), makeObservation(), makeObservation({ module: "bone" })]);
    seed.close();

    render(<App openStore={() => ObservationStore.open(name)} />);

    await waitFor(() => expect(screen.getByTestId("pending").textContent).toContain("3"));
    const cardio = document.querySelector('[data-module="cardiovascular"]');
    expect(cardio?.textContent).toContain("2 stored observations");
  });
});
