import type { CollectionJobStatus, CollectionOccurrence, CollectionScanMode, CollectionSpecies } from "../types";

export class CollectionState {
	public directory = "";
	public scanMode: CollectionScanMode = "raw_jpeg";
	public scanEnabled = false;
	public activeJobId: string | null = null;
	public starting = false;
	public stopping = false;
	public status: CollectionJobStatus | null = null;
	public error = "";
	public speciesSearchQuery = "";
	public familyFilter = "";
	public dateFrom = "";
	public dateTo = "";
	public gpsFilter: "all" | "withGps" | "withoutGps" = "all";
	public confidenceFilter: "all" | "manual" | "low" | "medium" | "high" = "all";
	public speciesSortOrder: "name" | "family" | "date" | "location" | "imageCount" | "confidence" = "name";
	public selectedSpeciesId: string | null = null;
	public selectedOccurrenceIndex = 0;
	public occurrenceOpen = false;
	public readonly selectedSpeciesIds = new Set<string>();
	private readonly removedSpeciesIds = new Set<string>();
	private readonly removedImagePaths = new Set<string>();
	private readonly sessionKeyPhotos = new Map<string, CollectionOccurrence>();
	private keyPhotoStorageCache: Record<string, { imagePath: string; birdIndex: number }> | null = null;


	public canScan(): boolean {
		return Boolean(this.directory.trim() && !this.activeJobId && !this.starting && !this.stopping);
	}


	public startScan(jobId: string): void {
		const previousStatus = this.status;
		this.activeJobId = jobId;
		this.error = "";
		this.status = { state: "running", total: previousStatus?.total ?? 0, completed: previousStatus?.completed ?? 0, errors: previousStatus?.errors ?? 0, currentFile: "", message: "", species: previousStatus?.species ?? [] };
		this.speciesSearchQuery = "";
		this.familyFilter = "";
		this.dateFrom = "";
		this.dateTo = "";
		this.gpsFilter = "all";
		this.confidenceFilter = "all";
		this.speciesSortOrder = "name";
		this.selectedSpeciesId = null;
		this.selectedOccurrenceIndex = 0;
		this.occurrenceOpen = false;
		this.selectedSpeciesIds.clear();
	}


	public applyStatus(status: CollectionJobStatus): void {
		if (status.state === "running" && this.status) {
			const previousSpecies = this.status.species;
			const previousCompleted = this.status.completed;
			if (previousSpecies.length > 0 && (status.species.length === 0 || status.completed < previousCompleted)) {
				status = { ...status, species: previousSpecies };
			}

			if (previousSpecies.length > 0 && status.completed < previousCompleted) {
				status = { ...status, completed: Math.min(previousCompleted, status.total || previousCompleted) };
			}
		}

		this.status = status;
		this.error = status.state === "error" ? status.error || status.message : "";
		if (status.state !== "running") {
			this.activeJobId = null;
		}
	}


	public clear(): void {
		this.status = null;
		this.speciesSearchQuery = "";
		this.familyFilter = "";
		this.dateFrom = "";
		this.dateTo = "";
		this.gpsFilter = "all";
		this.confidenceFilter = "all";
		this.speciesSortOrder = "name";
		this.removedSpeciesIds.clear();
		this.removedImagePaths.clear();
		this.selectedSpeciesId = null;
		this.selectedOccurrenceIndex = 0;
		this.occurrenceOpen = false;
		this.selectedSpeciesIds.clear();
		this.error = "";
	}


	public resetNavigation(): void {
		this.speciesSearchQuery = "";
		this.selectedSpeciesId = null;
		this.selectedOccurrenceIndex = 0;
		this.occurrenceOpen = false;
	}


	public species(): CollectionSpecies[] {
		return this.status?.species ?? [];
	}


	public visibleSpecies(): CollectionSpecies[] {
		return this.species().flatMap(species => {
			if (this.removedSpeciesIds.has(species.speciesId) || (this.familyFilter && species.family_name !== this.familyFilter)) {
				return [];
			}

			const occurrences = this.visibleOccurrences(species).filter(occurrence => !this.removedImagePaths.has(this.imagePathKey(occurrence.imagePath)));
			if (occurrences.length === 0) {
				return [];
			}

			const keyPhoto = this.keyPhotoOccurrence(species);
			return [{ ...species, thumbnailDataUrl: keyPhoto?.thumbnailDataUrl ?? species.thumbnailDataUrl, occurrences, occurrenceCount: occurrences.length, imageCount: new Set(occurrences.map(occurrence => this.imagePathKey(occurrence.imagePath))).size }];
		});
	}


	public setKeyPhoto(speciesId: string, occurrence: CollectionOccurrence): void {
		const species = this.species().find(item => item.speciesId === speciesId);
		if (!species?.occurrences.some(item => item.imagePath === occurrence.imagePath && item.birdIndex === occurrence.birdIndex)) return;
		const identity = this.keyPhotoStorageIdentity(speciesId);
		this.sessionKeyPhotos.set(identity, occurrence);
		const saved = this.savedKeyPhotos();
		saved[identity] = { imagePath: occurrence.imagePath, birdIndex: occurrence.birdIndex };
		try {
			window.localStorage.setItem("avesCaesar.keyPhotos", JSON.stringify(saved));
		} catch {
			// The selected cover remains active for this session if browser storage is unavailable.
		}
	}


	public isKeyPhoto(speciesId: string, occurrence: CollectionOccurrence): boolean {
		const chosen = this.keyPhotoOccurrence(this.species().find(item => item.speciesId === speciesId));
		return Boolean(chosen && chosen.imagePath === occurrence.imagePath && chosen.birdIndex === occurrence.birdIndex);
	}


	public visibleOccurrences(species: CollectionSpecies): CollectionOccurrence[] {
		return species.occurrences.filter(occurrence => {
			const date = this.captureDate(occurrence.usedDatetime);
			if (this.dateFrom && (!date || date < this.dateFrom)) {
				return false;
			}
			if (this.dateTo && (!date || date > this.dateTo)) {
				return false;
			}

			const hasGps = typeof occurrence.usedLatitude === "number" && typeof occurrence.usedLongitude === "number";
			if ((this.gpsFilter === "withGps" && !hasGps) || (this.gpsFilter === "withoutGps" && hasGps)) {
				return false;
			}

			const confidence = occurrence.confidence;
			if (this.confidenceFilter === "manual" && occurrence.classification.manual !== true) {
				return false;
			}
			if (this.confidenceFilter === "low" && (occurrence.classification.manual === true || confidence >= 0.5)) {
				return false;
			}
			if (this.confidenceFilter === "medium" && (occurrence.classification.manual === true || confidence < 0.5 || confidence >= 0.8)) {
				return false;
			}
			if (this.confidenceFilter === "high" && (occurrence.classification.manual === true || confidence < 0.8)) {
				return false;
			}

			return true;
		});
	}


	public removeSpecies(speciesId: string): void {
		this.removedSpeciesIds.add(speciesId);
		this.selectedSpeciesIds.delete(speciesId);
		if (this.selectedSpeciesId === speciesId) {
			this.resetNavigation();
		}
	}


	public toggleSpeciesExportSelection(speciesId: string): void {
		if (this.selectedSpeciesIds.has(speciesId)) {
			this.selectedSpeciesIds.delete(speciesId);
		} else if (this.species().some(item => item.speciesId === speciesId)) {
			this.selectedSpeciesIds.add(speciesId);
		}
	}


	public clearSpeciesExportSelection(): void {
		this.selectedSpeciesIds.clear();
	}


	public removeSelectedSpecies(): void {
		for (const speciesId of [...this.selectedSpeciesIds]) {
			this.removeSpecies(speciesId);
		}
	}


	public selectedExportSpecies(): CollectionSpecies[] {
		return this.visibleSpecies().filter(species => this.selectedSpeciesIds.has(species.speciesId));
	}


	public removeImage(imagePath: string): void {
		this.removedImagePaths.add(this.imagePathKey(imagePath));
		this.selectedOccurrenceIndex = 0;
		this.occurrenceOpen = false;
	}


	public hasRemovedItems(): boolean {
		return this.removedSpeciesIds.size > 0 || this.removedImagePaths.size > 0;
	}


	public restoreRemovedItems(): void {
		this.removedSpeciesIds.clear();
		this.removedImagePaths.clear();
		this.resetNavigation();
	}


	private imagePathKey(imagePath: string): string {
		return imagePath.replace(/\\/g, "/").toLocaleLowerCase();
	}


	private keyPhotoOccurrence(species: CollectionSpecies | undefined): CollectionOccurrence | null {
		if (!species) return null;
		const identity = this.keyPhotoStorageIdentity(species.speciesId);
		const saved = this.sessionKeyPhotos.get(identity) ?? this.savedKeyPhoto(identity, species);
		if (!saved || this.removedImagePaths.has(this.imagePathKey(saved.imagePath))) return null;
		return species.occurrences.find(item => item.imagePath === saved.imagePath && item.birdIndex === saved.birdIndex) ?? null;
	}


	private savedKeyPhoto(identity: string, species: CollectionSpecies): CollectionOccurrence | null {
		const value = this.savedKeyPhotos()[identity];
		return value ? species.occurrences.find(item => item.imagePath === value.imagePath && item.birdIndex === value.birdIndex) ?? null : null;
	}


	private savedKeyPhotos(): Record<string, { imagePath: string; birdIndex: number }> {
		if (this.keyPhotoStorageCache) return this.keyPhotoStorageCache;
		try {
			const value = window.localStorage.getItem("avesCaesar.keyPhotos");
			const parsed: unknown = value ? JSON.parse(value) : {};
			this.keyPhotoStorageCache = parsed && typeof parsed === "object" ? parsed as Record<string, { imagePath: string; birdIndex: number }> : {};
		} catch {
			this.keyPhotoStorageCache = {};
		}
		return this.keyPhotoStorageCache;
	}


	private keyPhotoStorageIdentity(speciesId: string): string {
		return `${this.directory.replace(/\\/g, "/").toLocaleLowerCase()}|${speciesId}`;
	}


	private captureDate(value: string | null | undefined): string {
		const match = String(value || "").match(/^(\d{4})[:/-](\d{2})[:/-](\d{2})/);
		return match ? `${match[1]}-${match[2]}-${match[3]}` : "";
	}


	public selectedSpecies(): CollectionSpecies | null {
		if (!this.selectedSpeciesId) {
			return null;
		}

		return this.visibleSpecies().find(item => item.speciesId === this.selectedSpeciesId) ?? null;
	}


	public selectedOccurrence(): CollectionOccurrence | null {
		const species = this.selectedSpecies();
		if (!species || species.occurrences.length === 0) {
			return null;
		}

		const index = Number.isInteger(this.selectedOccurrenceIndex) ? this.selectedOccurrenceIndex : 0;
		return species.occurrences[Math.min(index, species.occurrences.length - 1)] ?? null;
	}


	public selectSpecies(speciesId: string): void {
		this.selectedSpeciesId = speciesId;
		this.selectedOccurrenceIndex = 0;
		this.occurrenceOpen = false;
	}


	public selectOccurrence(index: number): CollectionOccurrence | null {
		const species = this.selectedSpecies();
		if (!species || !Number.isInteger(index) || index < 0 || index >= species.occurrences.length) {
			return null;
		}

		this.selectedOccurrenceIndex = index;
		this.occurrenceOpen = true;
		return species.occurrences[index];
	}


	public closeOccurrence(): void {
		this.occurrenceOpen = false;
	}


	public syncSelectionToOccurrence(imagePath: string, birdIndex: number, speciesId: string): void {
		const species = this.species().find(item => item.speciesId === speciesId);
		if (!species) {
			return;
		}

		const occurrenceIndex = species.occurrences.findIndex(item => item.imagePath === imagePath && item.birdIndex === birdIndex);
		if (occurrenceIndex < 0) {
			return;
		}

		this.selectedSpeciesId = species.speciesId;
		this.selectedOccurrenceIndex = occurrenceIndex;
		this.occurrenceOpen = true;
	}


	public previousOccurrence(): CollectionOccurrence | null {
		const species = this.selectedSpecies();
		if (!species || this.selectedOccurrenceIndex <= 0) {
			return null;
		}

		const nextIndex = this.selectedOccurrenceIndex - 1;
		return this.selectOccurrence(nextIndex);
	}


	public nextOccurrence(): CollectionOccurrence | null {
		const species = this.selectedSpecies();
		if (!species || this.selectedOccurrenceIndex >= species.occurrences.length - 1) {
			return null;
		}

		const nextIndex = this.selectedOccurrenceIndex + 1;
		return this.selectOccurrence(nextIndex);
	}


	public hasPreviousOccurrence(): boolean {
		return this.selectedOccurrenceIndex > 0;
	}


	public hasNextOccurrence(): boolean {
		const species = this.selectedSpecies();
		return Boolean(species && this.selectedOccurrenceIndex < species.occurrences.length - 1);
	}


	public estimatedFinishMs(nowMs = Date.now()): number | null {
		if (!this.status || this.status.state !== "running") {
			return null;
		}

		const { total, cached, processed, processingElapsedSeconds } = this.status;
		if (cached === undefined || processed === undefined || processingElapsedSeconds === undefined
			|| ![total, cached, processed, processingElapsedSeconds].every(Number.isFinite)
			|| cached < 0 || processed <= 0 || processingElapsedSeconds <= 0) {
			return null;
		}

		// Use this worker's measurements even when the UI retains an older collection.
		const remainingImages = total - cached - processed;
		return remainingImages > 0
			? nowMs + processingElapsedSeconds * 1000 / processed * remainingImages
			: null;
	}
}
