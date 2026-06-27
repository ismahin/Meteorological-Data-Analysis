import React, { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMapEvents } from "react-leaflet";
import { Activity, CloudRain, Gauge, MapPin, Navigation, Thermometer, Wind } from "lucide-react";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const DEFAULT_LOCATION = { latitude: 23.766667, longitude: 90.383333 };
const VARIABLES = [
  { id: "T2M", label: "Temperature", unit: "deg C", icon: Thermometer },
  { id: "RH2M", label: "Humidity", unit: "%", icon: Gauge },
  { id: "PRECTOTCORR", label: "Rainfall", unit: "mm obs hour", icon: CloudRain },
  { id: "WS10M", label: "Wind", unit: "m/s", icon: Wind },
];
const BOUNDS = {
  latMin: 20.5,
  latMax: 26.8,
  lonMin: 88.0,
  lonMax: 92.8,
};
const BANGLADESH_OUTLINE = [
  [26.62, 88.25],
  [26.25, 89.6],
  [25.45, 90.8],
  [25.2, 92.05],
  [24.35, 92.35],
  [23.45, 91.7],
  [22.2, 92.35],
  [20.75, 92.15],
  [21.55, 90.25],
  [21.85, 89.1],
  [22.8, 88.55],
  [24.1, 88.05],
  [25.3, 88.1],
  [26.62, 88.25],
];

function currentUtc3HourLocalValue() {
  const now = new Date();
  const utc = new Date(Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
    Math.floor(now.getUTCHours() / 3) * 3,
    0,
    0,
  ));
  return utc.toISOString().slice(0, 16);
}

const DEFAULT_TIMESTAMP = currentUtc3HourLocalValue();

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "NA";
  }
  return Number(value).toFixed(digits);
}

function formatTimestamp(value) {
  return value ? value.replace("T", " ").replace(":00Z", " UTC") : "Unavailable";
}

function sourceLabel(estimate) {
  if (!estimate || estimate.status !== "available") return "Unavailable";
  if (estimate.classification === "provisional_forecast") return "Provisional forecast";
  if (estimate.classification === "historical_correction") return "Historical correction";
  return "NASA exact correction";
}

function bmdSourceLabel(status) {
  if (status?.observation_available && status?.source === "OGIMET_SYNOP_BMD_raw") return "Actual BMD SYNOP from OGIMET";
  if (status?.observation_available) return "Actual archived BMD observation";
  if (status?.kind === "model_forecast") return "BMD model forecast (no live observation)";
  return "BMD model estimate (no live observation)";
}

function toUtcIso(utcInputValue) {
  return `${utcInputValue}:00Z`;
}

function validateInputs(location, timestampUtc) {
  const hour = Number(timestampUtc.slice(11, 13));
  const minute = Number(timestampUtc.slice(14, 16));
  if (!timestampUtc || !Number.isFinite(hour) || hour % 3 !== 0 || minute !== 0) {
    return "Timestamp must use a 3-hour UTC step: 00, 03, 06, 09, 12, 15, 18, or 21.";
  }
  if (timestampUtc < "2021-01-01T00") {
    return "Timestamp must be on or after 2021-01-01 00:00 UTC.";
  }
  if (
    location.latitude < BOUNDS.latMin ||
    location.latitude > BOUNDS.latMax ||
    location.longitude < BOUNDS.lonMin ||
    location.longitude > BOUNDS.lonMax
  ) {
    return "Coordinates must be inside the supported Bangladesh bounding box.";
  }
  return "";
}

function MapClick({ onPick }) {
  useMapEvents({
    click(event) {
      onPick({
        latitude: Number(event.latlng.lat.toFixed(6)),
        longitude: Number(event.latlng.lng.toFixed(6)),
      });
    },
  });
  return null;
}

function SelectedLocationMarker({ location }) {
  const icon = useMemo(
    () =>
      L.divIcon({
        className: "selected-location-marker",
        html: `
          <span class="selected-location-halo"></span>
          <span class="selected-location-pin"><span></span></span>
        `,
        iconSize: [46, 46],
        iconAnchor: [23, 36],
        tooltipAnchor: [0, -28],
      }),
    [],
  );

  return (
    <Marker
      position={[location.latitude, location.longitude]}
      icon={icon}
      keyboard={false}
      zIndexOffset={1000}
    >
      <Tooltip direction="top" offset={[0, -12]} opacity={0.96}>
        Selected coordinate
      </Tooltip>
    </Marker>
  );
}

function VariableToggle({ item, checked, onChange }) {
  const Icon = item.icon;
  return (
    <label className={`variable-toggle ${checked ? "is-active" : ""}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(item.id, event.target.checked)}
      />
      <Icon size={17} />
      <span>{item.label}</span>
    </label>
  );
}

function MetricRow({ label, value, unit }) {
  return (
    <div className="metric-row">
      <span>{label}</span>
      <strong>
        {value}
        {unit ? <small>{unit}</small> : null}
      </strong>
    </div>
  );
}

function ResultBlock({ variable, estimate }) {
  const meta = VARIABLES.find((item) => item.id === variable);
  const Icon = meta?.icon || Activity;
  const requested = estimate.requested;
  const latest = estimate.latest_nasa;
  const unavailable = requested?.status !== "available";
  const showLatest = latest && latest.timestamp_utc !== requested?.timestamp_utc;
  const isForecast = requested?.classification === "provisional_forecast";
  const isHistorical = requested?.classification === "historical_correction";
  const hasBmdObservation = requested?.bmd_observation_available && requested?.bmd_actual !== null;
  const bmdActualLabel = requested?.bmd_source === "OGIMET_SYNOP_BMD_raw"
    ? "BMD actual (OGIMET SYNOP)"
    : "BMD actual (nearest station)";
  return (
    <section className={`result-block ${unavailable ? "is-unavailable" : ""}`}>
      <header>
        <div>
          <Icon size={18} />
          <h3>{meta?.label || variable}</h3>
        </div>
        <span>{sourceLabel(requested)}</span>
      </header>
      {unavailable ? (
        <div className="unavailable-message">
          <strong>Estimate unavailable</strong>
          <span>{requested?.reason?.replaceAll("_", " ") || "No validated estimate is available."}</span>
        </div>
      ) : (
        <>
          {hasBmdObservation ? (
            <>
              <MetricRow label={bmdActualLabel} value={formatNumber(requested.bmd_actual ?? requested.bmd_raw)} unit={meta?.unit} />
              <MetricRow
                label={isForecast ? "NASA forecast (raw)" : "NASA raw"}
                value={formatNumber((isForecast ? requested.nasa_forecast : requested.nasa_raw) ?? requested.raw_forecast)}
                unit={meta?.unit}
              />
              <MetricRow label="Corrected value" value={formatNumber(requested.corrected_nasa ?? requested.bmd_equivalent)} unit={meta?.unit} />
            </>
          ) : isForecast ? (
            <>
              <MetricRow label="BMD forecast (model)" value={formatNumber(requested.bmd_forecast ?? requested.bmd_equivalent)} unit={meta?.unit} />
              <MetricRow label="NASA forecast (raw)" value={formatNumber(requested.nasa_forecast ?? requested.raw_forecast)} unit={meta?.unit} />
              <MetricRow label="Corrected value" value={formatNumber(requested.corrected_nasa ?? requested.bmd_equivalent)} unit={meta?.unit} />
            </>
          ) : isHistorical ? (
            <>
              <MetricRow label="BMD actual (nearest station)" value={formatNumber(requested.bmd_actual ?? requested.bmd_raw)} unit={meta?.unit} />
              <MetricRow label="NASA raw" value={formatNumber(requested.nasa_raw ?? requested.raw_forecast)} unit={meta?.unit} />
              <MetricRow label="Corrected value" value={formatNumber(requested.corrected_nasa ?? requested.bmd_estimate ?? requested.bmd_equivalent)} unit={meta?.unit} />
            </>
          ) : (
            <>
              <MetricRow label="BMD estimate (model)" value={formatNumber(requested.bmd_estimate ?? requested.bmd_equivalent)} unit={meta?.unit} />
              <MetricRow label="NASA raw" value={formatNumber(requested.nasa_raw ?? requested.raw_forecast)} unit={meta?.unit} />
              <MetricRow label="Corrected value" value={formatNumber(requested.corrected_nasa ?? requested.bmd_estimate ?? requested.bmd_equivalent)} unit={meta?.unit} />
            </>
          )}
          <MetricRow
            label="Corrected-value 90% interval"
            value={`${formatNumber(requested.p05)} to ${formatNumber(requested.p95)}`}
            unit={meta?.unit}
          />
          <MetricRow label="Forecast horizon" value={formatNumber(requested.forecast_horizon_hours, 0)} unit="hours" />
          {isHistorical ? null : <MetricRow label="BMD forecast model" value={requested.model_version} />}
          <MetricRow label="Correction model" value={requested.correction_model_version ?? requested.model_version} />
          {requested.correction_method ? <MetricRow label="Correction method" value={requested.correction_method} /> : null}
          {requested.correction_anchor_station_name ? (
            <MetricRow
              label="Correction anchor"
              value={`${requested.correction_anchor_station_name} (${formatNumber(requested.correction_anchor_distance_km, 2)} km)`}
            />
          ) : null}
        </>
      )}
      {variable === "PRECTOTCORR" && requested?.wet_probability !== null ? (
        <MetricRow
          label="Wet probability"
          value={formatNumber((requested.wet_probability || 0) * 100, 1)}
          unit="%"
        />
      ) : null}
      {showLatest ? (
        <div className="latest-nasa">
          <span>Latest NASA available</span>
          <strong>{formatTimestamp(latest.timestamp_utc)}</strong>
          <small>
            NASA raw {formatNumber(latest.nasa_raw ?? latest.raw_forecast)} {meta?.unit}
            {latest.bmd_actual !== null ? ` · BMD actual ${formatNumber(latest.bmd_actual)} ${meta?.unit}` : ""}
            {latest.bmd_estimate !== null ? ` · NASA corrected using BMD ${formatNumber(latest.corrected_nasa ?? latest.bmd_estimate)} ${meta?.unit}` : ""}
          </small>
        </div>
      ) : null}
    </section>
  );
}

function App() {
  const [stations, setStations] = useState([]);
  const [location, setLocation] = useState(DEFAULT_LOCATION);
  const [timestamp, setTimestamp] = useState(DEFAULT_TIMESTAMP);
  const [selectedVariables, setSelectedVariables] = useState(VARIABLES.map((item) => item.id));
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/stations`)
      .then((response) => response.json())
      .then((payload) => setStations(payload.stations || []))
      .catch(() => setError("Could not load BMD station metadata from the API."));
  }, []);

  const validationError = useMemo(() => validateInputs(location, timestamp), [location, timestamp]);
  const nearestLine = useMemo(() => {
    if (!result?.nearest_station) return null;
    return [
      [location.latitude, location.longitude],
      [result.nearest_station.latitude, result.nearest_station.longitude],
    ];
  }, [location, result]);

  function updateVariable(variable, checked) {
    setSelectedVariables((current) => {
      if (checked) return [...new Set([...current, variable])];
      return current.filter((item) => item !== variable);
    });
  }

  async function runCorrection(event) {
    event.preventDefault();
    setError("");
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!selectedVariables.length) {
      setError("Select at least one variable.");
      return;
    }
    setStatus("loading");
    try {
      const response = await fetch(`${API_BASE}/api/v2/estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          latitude: location.latitude,
          longitude: location.longitude,
          timestamp_utc: toUtcIso(timestamp),
          variables: selectedVariables,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Correction request failed.");
      }
      setResult(payload);
      setStatus("ready");
    } catch (requestError) {
      setError(requestError.message);
      setStatus("error");
    }
  }

  return (
    <main className="app-shell">
      <aside className="control-panel">
        <div className="brand">
          <div className="brand-mark">
            <Navigation size={19} />
          </div>
          <div>
            <h1>NASA-BMD Corrector</h1>
            <p>Bangladesh 3-hour correction and operational forecast</p>
          </div>
        </div>

        <form onSubmit={runCorrection} className="control-form">
          <label>
            Latitude
            <input
              type="number"
              step="0.000001"
              min={BOUNDS.latMin}
              max={BOUNDS.latMax}
              value={location.latitude}
              onChange={(event) => setLocation((current) => ({ ...current, latitude: Number(event.target.value) }))}
            />
          </label>
          <label>
            Longitude
            <input
              type="number"
              step="0.000001"
              min={BOUNDS.lonMin}
              max={BOUNDS.lonMax}
              value={location.longitude}
              onChange={(event) => setLocation((current) => ({ ...current, longitude: Number(event.target.value) }))}
            />
          </label>
          <label>
            Timestamp UTC
            <input
              type="datetime-local"
              min="2021-01-01T00:00"
              step="10800"
              value={timestamp}
              onChange={(event) => setTimestamp(event.target.value)}
            />
            <small className="input-help">UTC only. The browser timezone is ignored.</small>
          </label>

          <div className="variables">
            {VARIABLES.map((item) => (
              <VariableToggle
                key={item.id}
                item={item}
                checked={selectedVariables.includes(item.id)}
                onChange={updateVariable}
              />
            ))}
          </div>

          {validationError || error ? <p className="form-error">{error || validationError}</p> : null}
          <button type="submit" disabled={status === "loading"}>
            {status === "loading" ? "Calculating..." : "Estimate weather"}
          </button>
        </form>

        <div className="credit-note">
          <p>This website is develop by MD Ibrahim Shikder Mahin</p>
          <p>Reasech Assistant at BUBT</p>
          <div>
            <a href="https://www.linkedin.com/in/ismahin/" target="_blank" rel="noreferrer">
              Contact Us
            </a>
            <a href="mailto:mahinshikder01@gmail.com">Email</a>
          </div>
        </div>
      </aside>

      <section className="map-panel">
        <MapContainer
          bounds={[
            [20.55, 88.0],
            [26.7, 92.7],
          ]}
          maxBounds={[
            [19.9, 87.2],
            [27.25, 93.6],
          ]}
          minZoom={6}
          maxZoom={12}
          className="map"
        >
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Polyline positions={BANGLADESH_OUTLINE} pathOptions={{ color: "#0f766e", weight: 2, opacity: 0.75 }} />
          <MapClick onPick={setLocation} />
          {stations.map((station) => (
            <CircleMarker
              key={station.station_id}
              center={[station.latitude, station.longitude]}
              radius={result?.nearest_station?.station_id === station.station_id ? 8 : 5}
              pathOptions={{
                color: result?.nearest_station?.station_id === station.station_id ? "#f97316" : "#0f766e",
                fillColor: result?.nearest_station?.station_id === station.station_id ? "#fb923c" : "#14b8a6",
                fillOpacity: result?.nearest_station?.station_id === station.station_id ? 0.95 : 0.82,
                opacity: 0.95,
                weight: result?.nearest_station?.station_id === station.station_id ? 3 : 2,
              }}
            >
              <Tooltip>{station.station_name}</Tooltip>
            </CircleMarker>
          ))}
          <SelectedLocationMarker location={location} />
          {nearestLine ? (
            <Polyline positions={nearestLine} pathOptions={{ color: "#f97316", weight: 3, dashArray: "8 8" }} />
          ) : null}
        </MapContainer>
        <div className="map-hint">
          <MapPin size={15} />
          <span>Click map to set location</span>
        </div>
        <div className="map-status">
          <MapPin size={16} />
          <div>
            <span>Selected point</span>
            <strong>
              {formatNumber(location.latitude, 5)}, {formatNumber(location.longitude, 5)}
            </strong>
          </div>
        </div>
      </section>

      <aside className="result-panel">
        <header className="result-header">
          <span>Requested-time output</span>
          <strong>{result ? formatTimestamp(result.requested_timestamp_utc) : "No run yet"}</strong>
        </header>

        {result ? (
          <>
            {result.data_warning ? (
              <section className="forecast-warning" role="status">
                <strong>{result.data_warning}</strong>
                <span>
                  NASA data are available through {formatTimestamp(result.latest_nasa_timestamp_utc)}. The requested-time values are model estimates.
                </span>
              </section>
            ) : null}
            <section className="nearest-card">
              <span>{result.mode === "provisional_forecast" ? "Forecast status" : "Data status"}</span>
              <h2>{result.nearest_station.station_name}</h2>
              <p>Nearest BMD reference station · {formatNumber(result.nearest_station.distance_km, 1)} km</p>
              {result.nearest_station.wmo_id ? <p>Nearest WMO ID: {result.nearest_station.wmo_id}</p> : null}
              <p>Latest NASA: {formatTimestamp(result.latest_nasa_timestamp_utc)}</p>
              <p>NASA lag: {formatNumber(result.nasa_data_lag_hours, 1)} hours</p>
              <p>BMD source: {bmdSourceLabel(result.bmd_data_status)}</p>
              <p>BMD archive ends: {formatTimestamp(result.bmd_data_status?.archive_end_utc)}</p>
            </section>
            <div className="results-list">
              {Object.entries(result.estimates).map(([variable, estimate]) => (
                <ResultBlock key={variable} variable={variable} estimate={estimate} />
              ))}
            </div>
          </>
        ) : (
          <div className="empty-state">
            <MapPin size={28} />
            <h2>Select a coordinate and timestamp</h2>
            <p>The system uses NASA POWER history and models validated against BMD observations to return corrected or provisional estimates.</p>
          </div>
        )}
      </aside>
    </main>
  );
}

export default App;
