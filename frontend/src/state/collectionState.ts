import type { CollectionJobStatus, CollectionOccurrence, CollectionScanMode, CollectionSpecies } from "../types";

export class CollectionState {
	public directory = "";
	public scanMode: CollectionScanMode = "raw_jpeg";
	public scanEnabled = false;
	public activeJobId: string | null = null;
	public status: CollectionJobStatus | null = null;
	public error = "";
	public startedAtMs: number | null = null;
	public etaCompletedBaseline = 0;
	public speciesSearchQuery = "";
	public selectedSpeciesId: string | null = null;
	public selectedOccurrenceIndex = 0;
	public occurrenceOpen = false;


	public canScan(): boolean {
		return Boolean(this.directory.trim() && !this.activeJobId);
	}


	public startScan(jobId: string): void {
		const previousStatus = this.status;
		this.activeJobId = jobId;
		this.error = "";
		this.startedAtMs = Date.now();
		this.etaCompletedBaseline = previousStatus?.completed ?? 0;
		this.status = { state: "running", total: previousStatus?.total ?? 0, completed: previousStatus?.completed ?? 0, errors: previousStatus?.errors ?? 0, currentFile: "", message: "", species: previousStatus?.species ?? [] };
		this.speciesSearchQuery = "";
		this.selectedSpeciesId = null;
		this.selectedOccurrenceIndex = 0;
		this.occurrenceOpen = false;
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
			this.etaCompletedBaseline = 0;
		}
	}


	public clear(): void {
		this.status = null;
		this.speciesSearchQuery = "";
		this.selectedSpeciesId = null;
		this.selectedOccurrenceIndex = 0;
		this.occurrenceOpen = false;
		this.error = "";
		this.etaCompletedBaseline = 0;
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


	public selectedSpecies(): CollectionSpecies | null {
		if (!this.selectedSpeciesId) {
			return null;
		}

		return this.species().find(item => item.speciesId === this.selectedSpeciesId) ?? null;
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
		if (!this.status || this.status.state !== "running" || this.startedAtMs === null) {
			return null;
		}

		if (this.status.total <= 0 || this.status.completed <= 0 || this.status.completed >= this.status.total) {
			return null;
		}

		const elapsedMs = nowMs - this.startedAtMs;
		if (elapsedMs <= 0) {
			return null;
		}

		const completedSinceStart = this.status.completed - this.etaCompletedBaseline;
		if (completedSinceStart <= 0) {
			return null;
		}

		const averageMsPerImage = elapsedMs / completedSinceStart;
		const remainingImages = this.status.total - this.status.completed;
		return nowMs + averageMsPerImage * remainingImages;
	}
}
