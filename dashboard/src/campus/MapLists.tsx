import { CAMPUS_FEATURES } from "./features";
import type { PlacedDevice } from "./placement";

const shortName = new Map(CAMPUS_FEATURES.map((f) => [f.id, f.short]));

/**
 * The list route to every interactive map element (spec §10): one button per placed switch
 * and per building. Activating one opens the same popover as the marker on the map.
 */
export function MapLists({
  devices,
  onDevice,
  onBuilding,
}: {
  devices: PlacedDevice[];
  onDevice: (id: string) => void;
  onBuilding: (id: string) => void;
}) {
  return (
    <div className="map-lists">
      {devices.length > 0 && (
        <details>
          <summary>Switches <span className="mono muted">{devices.length}</span></summary>
          <ul aria-label="Switches">
            {devices.map((d) => (
              <li key={d.id}>
                <button type="button" onClick={() => onDevice(d.id)}>
                  <span className="mono">{d.id}</span>
                  <span className="muted">{shortName.get(d.buildingId)}</span>
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
      <details>
        <summary>Buildings <span className="mono muted">{CAMPUS_FEATURES.length}</span></summary>
        <ul aria-label="Buildings">
          {CAMPUS_FEATURES.map((f) => (
            <li key={f.id}>
              <button type="button" onClick={() => onBuilding(f.id)}>{f.name}</button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
