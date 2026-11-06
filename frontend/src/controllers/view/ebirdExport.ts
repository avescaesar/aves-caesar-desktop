import type { CollectionSpecies } from "../../types";
import { escapeHtml } from "../../utils";
import { BackendApiClient } from "../../backendApiClient";

type ExportObservation = { commonName: string; genus: string; species: string; count: string };
type ChecklistDraft = {
	date: string;
	location: string;
	latitude: string;
	longitude: string;
	startTime: string;
	state: string;
	stateOther: string;
	country: string;
	protocol: string;
	observers: string;
	duration: string;
	complete: string;
	distance: string;
	area: string;
	comments: string;
	observations: ExportObservation[];
};

type BoundaryFeature = [bounds: [number, number, number, number], countryCode: string, regionName: string, regionCode: string, geometry: { type: "Polygon" | "MultiPolygon"; coordinates: number[][][][] }];
type GeographicBoundaries = { regions: BoundaryFeature[]; countries: BoundaryFeature[] };
let geographicBoundariesPromise: Promise<GeographicBoundaries | null> | null = null;

function geographicBoundaries(): Promise<GeographicBoundaries | null> {
	if (!geographicBoundariesPromise) {
		geographicBoundariesPromise = fetch(new URL("geographic-boundaries.json", document.baseURI))
			.then(response => response.ok ? response.json() as Promise<GeographicBoundaries> : null)
			.catch(() => null);
	}
	return geographicBoundariesPromise;
}

function pointInRing(longitude: number, latitude: number, ring: number[][]): boolean {
	let inside = false;
	for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
		const [xi, yi] = ring[i];
		const [xj, yj] = ring[j];
		if ((yi > latitude) !== (yj > latitude) && longitude < (xj - xi) * (latitude - yi) / (yj - yi) + xi) inside = !inside;
	}
	return inside;
}

function pointInGeometry(longitude: number, latitude: number, geometry: BoundaryFeature[4]): boolean {
	const polygons = geometry.type === "Polygon" ? [geometry.coordinates as unknown as number[][][]] : geometry.coordinates as unknown as number[][][][];
	return polygons.some(polygon => pointInRing(longitude, latitude, polygon[0]) && !polygon.slice(1).some(hole => pointInRing(longitude, latitude, hole)));
}

async function locateCoordinates(latitude: number, longitude: number): Promise<BoundaryFeature | null> {
	const boundaries = await geographicBoundaries();
	if (!boundaries) return null;
	const matches = (feature: BoundaryFeature): boolean => {
		const [minLongitude, minLatitude, maxLongitude, maxLatitude] = feature[0];
		return longitude >= minLongitude && longitude <= maxLongitude && latitude >= minLatitude && latitude <= maxLatitude && pointInGeometry(longitude, latitude, feature[4]);
	};
	return boundaries.regions.find(matches) ?? boundaries.countries.find(matches) ?? null;
}

const COUNTRY_NAMES = (() => {
	const names: Array<[string, string]> = [];
	if (typeof Intl.DisplayNames !== "function") return [["CA", "Canada"], ["GB", "United Kingdom"], ["US", "United States"]];
	const displayNames = new Intl.DisplayNames(["en"], { type: "region" });
	const excludedCodes = new Set(["EU", "EZ", "QO", "UN", "XA", "XB", "ZZ"]);
	for (const first of "ABCDEFGHIJKLMNOPQRSTUVWXYZ") {
		for (const second of "ABCDEFGHIJKLMNOPQRSTUVWXYZ") {
			const code = `${first}${second}`;
			if (excludedCodes.has(code)) continue;
			const name = displayNames.of(code);
			if (name && name !== code && name !== "Unknown Region") names.push([code, name]);
		}
	}
	return names.sort((left, right) => left[1].localeCompare(right[1]));
})();

const COUNTRY_REGIONS: Record<string, Array<[string, string]>> = {
	US: [["AL", "Alabama"], ["AK", "Alaska"], ["AZ", "Arizona"], ["AR", "Arkansas"], ["CA", "California"], ["CO", "Colorado"], ["CT", "Connecticut"], ["DE", "Delaware"], ["DC", "District of Columbia"], ["FL", "Florida"], ["GA", "Georgia"], ["HI", "Hawaii"], ["ID", "Idaho"], ["IL", "Illinois"], ["IN", "Indiana"], ["IA", "Iowa"], ["KS", "Kansas"], ["KY", "Kentucky"], ["LA", "Louisiana"], ["ME", "Maine"], ["MD", "Maryland"], ["MA", "Massachusetts"], ["MI", "Michigan"], ["MN", "Minnesota"], ["MS", "Mississippi"], ["MO", "Missouri"], ["MT", "Montana"], ["NE", "Nebraska"], ["NV", "Nevada"], ["NH", "New Hampshire"], ["NJ", "New Jersey"], ["NM", "New Mexico"], ["NY", "New York"], ["NC", "North Carolina"], ["ND", "North Dakota"], ["OH", "Ohio"], ["OK", "Oklahoma"], ["OR", "Oregon"], ["PA", "Pennsylvania"], ["RI", "Rhode Island"], ["SC", "South Carolina"], ["SD", "South Dakota"], ["TN", "Tennessee"], ["TX", "Texas"], ["UT", "Utah"], ["VT", "Vermont"], ["VA", "Virginia"], ["WA", "Washington"], ["WV", "West Virginia"], ["WI", "Wisconsin"], ["WY", "Wyoming"]],
	CA: [["AB", "Alberta"], ["BC", "British Columbia"], ["MB", "Manitoba"], ["NB", "New Brunswick"], ["NL", "Newfoundland and Labrador"], ["NS", "Nova Scotia"], ["NT", "Northwest Territories"], ["NU", "Nunavut"], ["ON", "Ontario"], ["PE", "Prince Edward Island"], ["QC", "Quebec"], ["SK", "Saskatchewan"], ["YT", "Yukon"]],
	AU: [["ACT", "Australian Capital Territory"], ["NSW", "New South Wales"], ["NT", "Northern Territory"], ["QLD", "Queensland"], ["SA", "South Australia"], ["TAS", "Tasmania"], ["VIC", "Victoria"], ["WA", "Western Australia"]],
	GB: [["ENG", "England"], ["NIR", "Northern Ireland"], ["SCT", "Scotland"], ["WLS", "Wales"]],
};

function dateValue(value: string | null | undefined): string {
	const match = String(value ?? "").match(/^(\d{4})[:/-](\d{2})[:/-](\d{2})(?:[ T](\d{2}):(\d{2}))?/);
	return match ? `${match[1]}-${match[2]}-${match[3]}` : "";
}

function timeValue(value: string | null | undefined): string {
	const match = String(value ?? "").match(/^[\d:/-]+[ T](\d{2}):(\d{2})/);
	return match ? `${match[1]}:${match[2]}` : "";
}

function timeInMinutes(value: string | null | undefined): number | null {
	const match = String(value ?? "").match(/^[\d:/-]+[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?/);
	if (!match) return null;
	const hours = Number(match[1]);
	const minutes = Number(match[2]);
	const seconds = Number(match[3] ?? "0");
	if (hours > 23 || minutes > 59 || seconds > 59) return null;
	return hours * 60 + minutes + seconds / 60;
}

function roundedCoordinate(value: number | null | undefined): string {
	return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "";
}

function preciseCoordinate(value: number): string {
	return Number.isFinite(value) ? value.toFixed(5) : "";
}

function speciesNames(item: CollectionSpecies): { commonName: string; genus: string; species: string } {
	const words = String(item.name_lat ?? "").trim().split(/\s+/);
	return {
		commonName: item.name_language === "en" ? String(item.name ?? "") : "",
		genus: words.length > 0 && words[0] !== "" ? words[0] : "",
		species: words.length > 1 ? words.slice(1).join(" ") : "",
	};
}

function draftChecklists(selected: CollectionSpecies[]): ChecklistDraft[] {
	type ChecklistSeed = { date: string; locationKey: string; times: Set<string>; captureMinutes: number[]; coordinates: Array<[number, number]>; observations: Map<string, ExportObservation>; photoBirds: Map<string, Map<string, Set<number>>> };
	const groups = new Map<string, ChecklistSeed>();
	for (const item of selected) {
		const names = speciesNames(item);
		for (const occurrence of item.occurrences) {
			const date = dateValue(occurrence.usedDatetime);
			const latitude = roundedCoordinate(occurrence.usedLatitude);
			const longitude = roundedCoordinate(occurrence.usedLongitude);
			const time = timeValue(occurrence.usedDatetime);
			const locationKey = latitude && longitude ? `${latitude}|${longitude}` : "";
			const key = `${date}\u0000${locationKey}`;
			let group = groups.get(key);
			if (!group) {
				group = { date, locationKey, times: new Set<string>(), captureMinutes: [], coordinates: [], observations: new Map<string, ExportObservation>(), photoBirds: new Map<string, Map<string, Set<number>>>() };
				groups.set(key, group);
			}
			if (time) group.times.add(time);
			const capturedAtMinutes = timeInMinutes(occurrence.usedDatetime);
			if (capturedAtMinutes !== null) group.captureMinutes.push(capturedAtMinutes);
			if (locationKey && typeof occurrence.usedLatitude === "number" && typeof occurrence.usedLongitude === "number") {
				group.coordinates.push([occurrence.usedLatitude, occurrence.usedLongitude]);
			}
			if (!group.observations.has(item.speciesId)) group.observations.set(item.speciesId, { ...names, count: "X" });
			let photos = group.photoBirds.get(item.speciesId);
			if (!photos) {
				photos = new Map<string, Set<number>>();
				group.photoBirds.set(item.speciesId, photos);
			}
			const photoKey = occurrence.imagePath.replace(/\\/g, "/").toLocaleLowerCase();
			let birdIndices = photos.get(photoKey);
			if (!birdIndices) {
				birdIndices = new Set<number>();
				photos.set(photoKey, birdIndices);
			}
			birdIndices.add(occurrence.birdIndex);
		}
	}

	for (const group of [...groups.values()].filter(item => !item.locationKey)) {
		const knownLocations = [...groups.values()].filter(item => item.date === group.date && item.locationKey);
		if (knownLocations.length !== 1) continue;
		const known = knownLocations[0];
		for (const [speciesId, observation] of group.observations) {
			if (!known.observations.has(speciesId)) known.observations.set(speciesId, observation);
		}
		for (const [speciesId, photos] of group.photoBirds) {
			let knownPhotos = known.photoBirds.get(speciesId);
			if (!knownPhotos) {
				knownPhotos = new Map<string, Set<number>>();
				known.photoBirds.set(speciesId, knownPhotos);
			}
			for (const [photoPath, birdIndices] of photos) {
				let knownBirdIndices = knownPhotos.get(photoPath);
				if (!knownBirdIndices) {
					knownBirdIndices = new Set<number>();
					knownPhotos.set(photoPath, knownBirdIndices);
				}
				for (const birdIndex of birdIndices) knownBirdIndices.add(birdIndex);
			}
		}
		for (const time of group.times) known.times.add(time);
		known.captureMinutes.push(...group.captureMinutes);
		known.coordinates.push(...group.coordinates);
		groups.delete(`${group.date}\u0000`);
	}

	return [...groups.values()].sort((left, right) => (left.date || "9999").localeCompare(right.date || "9999") || left.locationKey.localeCompare(right.locationKey)).map(group => {
		for (const [speciesId, observation] of group.observations) {
			const perPhotoCounts = [...(group.photoBirds.get(speciesId)?.values() ?? [])].map(birds => birds.size);
			if (perPhotoCounts.length > 0) observation.count = String(Math.max(...perPhotoCounts));
		}
		const latitude = group.coordinates.length ? preciseCoordinate(group.coordinates.reduce((sum, point) => sum + point[0], 0) / group.coordinates.length) : "";
		const longitude = group.coordinates.length ? preciseCoordinate(group.coordinates.reduce((sum, point) => sum + point[1], 0) / group.coordinates.length) : "";
		const earliestCapture = group.captureMinutes.length ? Math.min(...group.captureMinutes) : null;
		const latestCapture = group.captureMinutes.length ? Math.max(...group.captureMinutes) : null;
		const elapsedMinutes = earliestCapture !== null && latestCapture !== null ? latestCapture - earliestCapture : null;
		return {
			date: group.date,
			location: "",
			latitude,
			longitude,
			startTime: [...group.times].sort()[0] ?? "",
			state: "",
			stateOther: "",
			country: "",
			protocol: "Historical",
			observers: "1",
			duration: elapsedMinutes === null ? "" : String(elapsedMinutes > 0 ? Math.max(1, Math.round(elapsedMinutes)) : 0),
			complete: "N",
			distance: "",
			area: "",
			comments: "",
			observations: [...group.observations.values()].sort((a, b) => (a.commonName || `${a.genus} ${a.species}`).localeCompare(b.commonName || `${b.genus} ${b.species}`)),
		};
	});
}

function textInput(label: string, key: string, value: string, type = "text", placeholder = ""): string {
	return `<label class="ebird-field"><span>${label}</span><input data-checklist-field="${key}" type="${type}" value="${escapeHtml(value)}" placeholder="${escapeHtml(placeholder)}" /></label>`;
}

function renderCountryField(draft: ChecklistDraft): string {
	const options = COUNTRY_NAMES.map(([code, name]) => `<option value="${code}" ${draft.country === code ? "selected" : ""}>${escapeHtml(name)} (${code})</option>`).join("");
	return `<label class="ebird-field"><span>Country</span><select data-checklist-field="country"><option value="">Select country</option>${options}</select></label>`;
}

function renderStateField(draft: ChecklistDraft): string {
	const regions = COUNTRY_REGIONS[draft.country] ?? [];
	const savedCode = draft.state === "__custom__" ? "__custom__" : draft.state;
	const useCustom = savedCode === "__custom__" || Boolean(savedCode && !regions.some(([code]) => code === savedCode));
	const selected = useCustom ? "__custom__" : savedCode;
	const options = regions.map(([code, name]) => `<option value="${code}" ${selected === code ? "selected" : ""}>${escapeHtml(name)} (${code})</option>`).join("");
	const customOption = `<option value="__custom__" ${useCustom ? "selected" : ""}>Other / enter code</option>`;
	const otherInput = useCustom ? textInput("Other state / province code", "stateOther", draft.stateOther || (draft.state !== "__custom__" ? draft.state : ""), "text", "1–3 character code") : "";
	return `<label class="ebird-field"><span>State / province</span><select data-checklist-field="state"><option value="">Select state / province</option>${options}${customOption}</select></label>${otherInput}`;
}

function coordinateInput(label: string, key: string, value: string, min: number, max: number): string {
	return `<label class="ebird-field"><span>${label} (${min} to ${max})</span><input data-checklist-field="${key}" data-coordinate type="text" inputmode="decimal" maxlength="12" pattern="-?([0-9]+(\\.[0-9]+)?|\\.[0-9]+)" value="${escapeHtml(value)}" placeholder="Decimal degrees" /></label>`;
}

function renderChecklist(draft: ChecklistDraft, index: number): string {
	const rows = draft.observations.map((observation, observationIndex) => `<tr><td>${escapeHtml(observation.commonName || `${observation.genus} ${observation.species}`)}</td><td><input aria-label="Count for ${escapeHtml(observation.commonName || observation.genus)}" data-observation-index="${observationIndex}" type="text" value="${escapeHtml(observation.count)}" /></td><td><button type="button" class="secondary-action" data-remove-observation="${observationIndex}" title="Remove this species from this checklist">Remove</button></td></tr>`).join("");
	const needsTimedEffort = draft.protocol === "Stationary" || draft.protocol === "Traveling";
	const completeField = draft.protocol === "Incidental"
		? `<label class="ebird-field"><span>All observations reported?</span><select data-checklist-field="complete" disabled><option value="N" selected>No / incomplete</option></select></label>`
		: `<label class="ebird-field"><span>All observations reported?</span><select data-checklist-field="complete"><option value="N" ${draft.complete === "N" ? "selected" : ""}>No / incomplete</option><option value="Y" ${draft.complete === "Y" ? "selected" : ""}>Yes / complete</option></select></label>`;
	return `<details class="ebird-checklist" open data-checklist-index="${index}">
		<summary>Checklist ${index + 1} · ${draft.observations.length} species</summary>
		<div class="ebird-fields">
			${textInput("Date (required)", "date", draft.date, "date")}
			${textInput("Location name (required)", "location", draft.location, "text", "Enter the birding place or eBird hotspot")}
			${coordinateInput("Latitude", "latitude", draft.latitude, -90, 90)}
			${coordinateInput("Longitude", "longitude", draft.longitude, -180, 180)}
			${textInput(`Start time${needsTimedEffort ? " (required)" : ""}`, "startTime", draft.startTime, "time")}
			<label class="ebird-field"><span>Protocol</span><select data-checklist-field="protocol"><option ${draft.protocol === "Historical" ? "selected" : ""}>Historical</option><option ${draft.protocol === "Incidental" ? "selected" : ""}>Incidental</option><option ${draft.protocol === "Stationary" ? "selected" : ""}>Stationary</option><option ${draft.protocol === "Traveling" ? "selected" : ""}>Traveling</option></select></label>
			${renderCountryField(draft)}
			${renderStateField(draft)}
			<p class="ebird-location-hint">Country and state / province are filled from GPS coordinates using offline map data. You can change them manually.</p>
			${textInput("Observers (required)", "observers", draft.observers, "number")}
			${textInput(`Duration (minutes)${needsTimedEffort ? " (required)" : ""}`, "duration", draft.duration, "number")}
			${completeField}
			${textInput(`Distance (miles)${draft.protocol === "Traveling" ? " (required)" : ""}`, "distance", draft.distance, "number")}
			${textInput("Area (acres)", "area", draft.area, "number")}
			<label class="ebird-field ebird-field--wide"><span>Checklist comments</span><input data-checklist-field="comments" value="${escapeHtml(draft.comments)}" /></label>
		</div>
		<table class="ebird-species-table"><thead><tr><th>Species</th><th>Count</th><th></th></tr></thead><tbody>${rows}</tbody></table>
	</details>`;
}

function readDrafts(backdrop: HTMLElement, drafts: ChecklistDraft[]): void {
	backdrop.querySelectorAll<HTMLElement>(".ebird-checklist").forEach((checklistElement, checklistIndex) => {
		const draft = drafts[checklistIndex];
		checklistElement.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[data-checklist-field]").forEach(input => {
			const key = input.dataset.checklistField as keyof ChecklistDraft;
			if (key !== "observations") (draft[key] as string) = input.value;
		});
		checklistElement.querySelectorAll<HTMLInputElement>("[data-observation-index]").forEach(input => {
			draft.observations[Number(input.dataset.observationIndex)].count = input.value.trim();
		});
	});
}

function csvCell(value: string): string {
	return value.replace(/[\r\n"]+/g, " ").replace(/,/g, " ").trim();
}

function validCoordinate(value: string, minimum: number, maximum: number): boolean {
	if (!value) return true;
	if (!/^-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$/.test(value)) return false;
	const coordinate = Number(value);
	return Number.isFinite(coordinate) && coordinate >= minimum && coordinate <= maximum;
}

function recordRows(drafts: ChecklistDraft[]): string {
	const rows: string[] = [];
	for (const draft of drafts) {
		for (const observation of draft.observations) {
			rows.push([
				observation.commonName, observation.genus, observation.species, observation.count, "",
				draft.location, draft.latitude, draft.longitude, draft.date ? draft.date.split("-").slice(1).concat(draft.date.split("-")[0]).join("/") : "",
				draft.startTime, draft.state === "__custom__" ? draft.stateOther : draft.state, draft.country, draft.protocol, draft.observers, draft.duration, draft.complete,
				draft.distance, draft.area, draft.comments,
			].map(value => csvCell(String(value))).join(","));
		}
	}
	return `${rows.join("\r\n")}\r\n`;
}

export function openEbirdRecordExport(selected: CollectionSpecies[]): void {
	const drafts = draftChecklists(selected);
	if (drafts.length === 0) return;
	const backdrop = document.createElement("div");
	backdrop.className = "modal-backdrop ebird-export-backdrop";
	backdrop.innerHTML = `<section class="ebird-export-modal" role="dialog" aria-modal="true" aria-labelledby="ebirdExportTitle">
		<header><div><h2 id="ebirdExportTitle">Export eBird Record Format</h2><p>Review the proposed checklists and the counts filled from photo detections.</p></div><button type="button" class="secondary-action" data-close-ebird>Close</button></header>
		<div class="ebird-export-notice">Species counts are prefilled from detections in the selected photos. If a species appears in multiple photos in one checklist, the count uses the highest count from a single photo to reduce repeat counting; review and adjust the count as needed. Duration (minutes) is prefilled from the first and last captured-photo times; review it if your birding period was longer or shorter. Photos are separated into checklists by capture date and GPS cells rounded to 0.01°. Each cell is about 1.1 km north–south; east–west width varies with latitude. This is an automatic grouping aid, not eBird’s location boundary. Confirm each checklist represents one eBird location. The selected photos span ${new Set(selected.flatMap(item => item.occurrences.map(occurrence => dateValue(occurrence.usedDatetime)).filter(Boolean))).size || "unknown"} date(s) and ${new Set(selected.flatMap(item => item.occurrences.map(occurrence => {
			const latitude = roundedCoordinate(occurrence.usedLatitude);
			const longitude = roundedCoordinate(occurrence.usedLongitude);
			return latitude && longitude ? `${latitude},${longitude}` : "";
		}).filter(Boolean))).size || "unknown"} GPS location(s). Confirm they belong to the same birding event before exporting. Enter the location even when GPS is unavailable. Photo export converts non-JPEG files to JPEG and keeps every exported image below 9.5 MB. Only export birds you personally observed alive in the wild.</div>
		<div class="ebird-checklists">${drafts.map(renderChecklist).join("")}</div>
		<div class="ebird-export-progress" data-ebird-progress hidden role="status" aria-live="polite"><progress max="100" value="0" data-ebird-progress-value aria-label="Photo export progress"></progress><span data-ebird-progress-label>Preparing export...</span></div>
		<footer><span data-ebird-error role="alert"></span><button type="button" class="secondary-action" data-close-ebird>Cancel</button><button type="button" class="secondary-action" data-export-ebird-csv>Export checklist</button><button type="button" class="toolbar-button is-primary" data-export-ebird-package>Export checklist + photos</button></footer>
	</section>`;
	document.body.append(backdrop);
	const close = (): void => backdrop.remove();
	backdrop.addEventListener("change", event => {
		const target = event.target;
		if (!(target instanceof HTMLSelectElement || target instanceof HTMLInputElement)) return;
		readDrafts(backdrop, drafts);
		const checklist = target.closest<HTMLElement>(".ebird-checklist");
		const draft = drafts[Number(checklist?.dataset.checklistIndex)];
		if (!draft) return;
		if (target instanceof HTMLInputElement && (target.dataset.checklistField === "latitude" || target.dataset.checklistField === "longitude")) {
			if (!validCoordinate(draft.latitude, -90, 90) || !validCoordinate(draft.longitude, -180, 180) || !draft.latitude || !draft.longitude) return;
			const latitude = Number(draft.latitude);
			const longitude = Number(draft.longitude);
			void locateCoordinates(latitude, longitude).then(match => {
				if (!match || !backdrop.isConnected || draft.latitude !== String(latitude) || draft.longitude !== String(longitude)) return;
				draft.country = match[1];
				const regions = COUNTRY_REGIONS[draft.country] ?? [];
				if (match[3] && regions.some(([code]) => code === match[3])) {
					draft.state = match[3];
					draft.stateOther = "";
				} else if (match[3] && /^[A-Za-z0-9]{1,3}$/.test(match[3])) {
					draft.state = "__custom__";
					draft.stateOther = match[3];
				} else {
					draft.state = "";
					draft.stateOther = "";
				}
				const list = backdrop.querySelector<HTMLElement>(".ebird-checklists");
				if (list) list.innerHTML = drafts.map(renderChecklist).join("");
			});
			return;
		}
		if (!(target instanceof HTMLSelectElement)) return;
		if (target.dataset.checklistField === "protocol") {
			if (draft.protocol === "Incidental") draft.complete = "N";
			const list = backdrop.querySelector<HTMLElement>(".ebird-checklists");
			if (list) list.innerHTML = drafts.map(renderChecklist).join("");
			return;
		}
		if (target.dataset.checklistField !== "country") return;
		const previousState = draft.state === "__custom__" ? draft.stateOther : draft.state;
		draft.country = target.value;
		const regions = COUNTRY_REGIONS[draft.country] ?? [];
		if (previousState && regions.some(([code]) => code === previousState)) {
			draft.state = previousState;
			draft.stateOther = "";
		} else if (previousState) {
			draft.state = "__custom__";
			draft.stateOther = previousState;
		} else {
			draft.state = "";
			draft.stateOther = "";
		}
		const list = backdrop.querySelector<HTMLElement>(".ebird-checklists");
		if (list) list.innerHTML = drafts.map(renderChecklist).join("");
	});
	for (const draft of drafts) {
		if (!validCoordinate(draft.latitude, -90, 90) || !validCoordinate(draft.longitude, -180, 180) || !draft.latitude || !draft.longitude) continue;
		void locateCoordinates(Number(draft.latitude), Number(draft.longitude)).then(match => {
			if (!match || !backdrop.isConnected || draft.country) return;
			draft.country = match[1];
			const regions = COUNTRY_REGIONS[draft.country] ?? [];
			if (match[3] && regions.some(([code]) => code === match[3])) {
				draft.state = match[3];
			} else if (match[3] && /^[A-Za-z0-9]{1,3}$/.test(match[3])) {
				draft.state = "__custom__";
				draft.stateOther = match[3];
			}
			const list = backdrop.querySelector<HTMLElement>(".ebird-checklists");
			if (list) list.innerHTML = drafts.map(renderChecklist).join("");
		});
	}
	backdrop.addEventListener("click", event => {
		const target = event.target;
		if (!(target instanceof Element)) return;
		if (target.closest("[data-close-ebird]")) close();
		const removeObservation = target.closest<HTMLElement>("[data-remove-observation]");
		if (removeObservation) {
			readDrafts(backdrop, drafts);
			const checklistElement = removeObservation.closest<HTMLElement>(".ebird-checklist");
			const checklistIndex = Number(checklistElement?.dataset.checklistIndex);
			drafts[checklistIndex]?.observations.splice(Number(removeObservation.dataset.removeObservation), 1);
			const list = backdrop.querySelector<HTMLElement>(".ebird-checklists");
			if (list) list.innerHTML = drafts.map(renderChecklist).join("");
			return;
		}
		const csvExport = target.closest<HTMLButtonElement>("[data-export-ebird-csv]");
		const packageExport = target.closest<HTMLButtonElement>("[data-export-ebird-package]");
		if (csvExport || packageExport) {
			const error = backdrop.querySelector<HTMLElement>("[data-ebird-error]");
			error?.classList.remove("is-success");
			if (error) error.textContent = "";
			readDrafts(backdrop, drafts);
			const invalid = drafts.find(draft => {
				const badCoordinates = !validCoordinate(draft.latitude, -90, 90) || !validCoordinate(draft.longitude, -180, 180) || Boolean(draft.latitude) !== Boolean(draft.longitude);
				const stateCode = draft.state === "__custom__" ? draft.stateOther : draft.state;
				const badRegionCode = Boolean(stateCode) && !/^[A-Za-z0-9]{1,3}$/.test(stateCode);
				const needsTimedEffort = draft.protocol === "Stationary" || draft.protocol === "Traveling";
				const badStartTime = needsTimedEffort && !draft.startTime;
				const duration = Number(draft.duration);
				const badDuration = needsTimedEffort && (!draft.duration || !Number.isInteger(duration) || duration <= 0);
				const distance = Number(draft.distance);
				const badDistance = draft.protocol === "Traveling" && (!draft.distance || !Number.isFinite(distance) || distance <= 0);
				const observers = Number(draft.observers);
				const badObservers = !Number.isInteger(observers) || observers < 1;
				return !draft.date || !draft.location.trim() || badCoordinates || badRegionCode || badStartTime || badDuration || badDistance || badObservers || draft.observations.some(observation => !observation.count || (!Number.isInteger(Number(observation.count)) && observation.count.toUpperCase() !== "X") || Number(observation.count) < 1);
			});
			if (invalid) {
				if (error) error.textContent = "Check the required date, location, observers, valid coordinates and region code, species counts, and effort fields required by the selected protocol.";
				return;
			}
			const button = csvExport ?? packageExport;
			if (button) button.disabled = true;
			if (csvExport) {
				void new BackendApiClient().saveEbirdCsv(recordRows(drafts)).then(result => {
					if (result) close();
				}).catch(() => {
					if (error) error.textContent = "Could not save the checklist CSV. Try again or check the destination folder.";
				}).finally(() => {
					if (button?.isConnected) button.disabled = false;
				});
				return;
			}
			const photoFiles = selected.map(item => ({
				name: item.name_language === "en" && item.name ? item.name : item.name_lat || item.speciesId,
				imagePaths: [...new Set(item.occurrences.map(occurrence => occurrence.imagePath))],
			}));
			const exportDates = [...new Set(drafts.map(draft => draft.date).filter(Boolean))].sort();
			const exportLocations = [...new Set(drafts.map(draft => draft.location.trim()).filter(Boolean))];
			const packageDate = exportDates.length > 1 ? `${exportDates[0]}_to_${exportDates[exportDates.length - 1]}` : exportDates[0] || drafts[0].date;
			const packageLocation = exportLocations.length === 1 ? exportLocations[0] : "multiple-locations";
			const client = new BackendApiClient();
			const progress = backdrop.querySelector<HTMLProgressElement>("[data-ebird-progress-value]");
			const progressLabel = backdrop.querySelector<HTMLElement>("[data-ebird-progress-label]");
			const progressPanel = backdrop.querySelector<HTMLElement>("[data-ebird-progress]");
			void client.startEbirdPackageExport(recordRows(drafts), packageDate, packageLocation, photoFiles).then(job => {
				if (!job) return;
				if (progressPanel) progressPanel.hidden = false;
				backdrop.querySelectorAll<HTMLButtonElement>("[data-close-ebird], [data-export-ebird-csv], [data-export-ebird-package]").forEach(item => { item.disabled = true; });
				if (button) button.textContent = "Exporting photos…";
				const poll = async (): Promise<void> => {
					const status = await client.ebirdExportStatus(job.jobId);
					if (progress) progress.value = Math.max(0, Math.min(100, status.progress));
					if (progressLabel) progressLabel.textContent = status.total ? `${status.processed} of ${status.total} photos · ${status.current}` : status.current;
					if (status.state === "running") {
						window.setTimeout(() => { void poll().catch(fail); }, 250);
						return;
					}
					if (status.state === "done" && status.result) {
						if (progress) progress.value = 100;
						if (button) button.textContent = "Export complete";
						if (error) {
							error.classList.add("is-success");
							error.textContent = `Exported the checklist and ${status.result.photoCount} photos (${status.result.convertedPhotoCount} converted to JPEG) to ${status.result.path}`;
						}
						backdrop.querySelectorAll<HTMLButtonElement>("[data-close-ebird]").forEach(item => { item.disabled = false; });
						return;
					}
					throw new Error(status.error || status.current || "Photo export failed.");
				};
				const fail = (reason: unknown): void => {
					if (error) error.textContent = reason instanceof Error ? reason.message : "Could not export the checklist and photos. Check the destination folder and try again.";
					backdrop.querySelectorAll<HTMLButtonElement>("[data-close-ebird], [data-export-ebird-csv], [data-export-ebird-package]").forEach(item => { item.disabled = false; });
					if (button) button.textContent = "Export checklist + photos";
				};
				void poll().catch(fail);
			}).catch(reason => {
				if (error) error.textContent = reason instanceof Error ? reason.message : "Could not start the photo export.";
			}).finally(() => {
				if (button?.isConnected && !backdrop.querySelector("[data-ebird-progress]:not([hidden])")) button.disabled = false;
			});
		}
	});
}
