import { CollectionState } from "../../state/collectionState";
import { DetectionState } from "../../state/detectionState";
import { ImageViewportState } from "../../state/imageViewportState";
import { SpeciesCorrectionState } from "../../state/speciesCorrectionState";
import { ActiveView, type CollectionJobStatus, type CollectionScanMode } from "../../types";
import { delay, errorMessage } from "../../utils";
import type { AppControllerContext } from "../core/appControllerContext";
import type { DetectionController, PredictionCorrectionResult } from "./detectionController";
import type { EventBinder } from "../core/eventBinder";
import type { ViewController } from "./viewController";

export class CollectionController implements ViewController {
	public readonly view = ActiveView.Collection;
	private collectionJobThreshold: number | null = null;
	private collectionLoadedSignature: string | null = null;
	private collectionLoadingSignature: string | null = null;
	private collectionRefreshRevision = 0;


	public constructor(private readonly context: AppControllerContext, public readonly state: CollectionState, private readonly detectionState: DetectionState, private readonly speciesCorrectionState: SpeciesCorrectionState, private readonly imageViewportState: ImageViewportState, private readonly detectionController: DetectionController) {}


	public bindEvents(bindEvent: EventBinder): void {
		bindEvent(document.querySelector<HTMLInputElement>("#collectionSpeciesSearch"), "input", event => this.updateCollectionSpeciesSearch(event));
		bindEvent(document.querySelector<HTMLSelectElement>("#collectionScanMode"), "change", event => void this.changeCollectionScanMode(event));
		bindEvent(document.querySelector<HTMLElement>(".collection-view"), "click", event => this.handleCollectionClick(event));
	}


	public handleNavigationKey(event: KeyboardEvent): boolean {
		if (this.isTypingTarget(event.target)) {
			return false;
		}

		if (this.context.state.navigation.activeView !== ActiveView.Collection || !this.state.occurrenceOpen) {
			return false;
		}

		if (event.code === "ArrowLeft" && this.state.hasPreviousOccurrence()) {
			event.preventDefault();
			void this.previousCollectionOccurrence();
			return true;
		}

		if (event.code === "ArrowRight" && this.state.hasNextOccurrence()) {
			event.preventDefault();
			void this.nextCollectionOccurrence();
			return true;
		}

		return false;
	}


	public async show(): Promise<void> {
		this.context.state.navigation.activeView = this.view;
		this.state.resetNavigation();
		this.clearDetectionImageAndResult();
		this.context.render();
		await this.loadCollectionIndex();
		this.context.render();
		this.resumeCollectionScanIfEnabled();
	}


	public hide(): void {
		this.stopForNavigation();
	}


	public async preloadCollectionIndex(): Promise<void> {
		await this.loadCollectionIndex();
		if (this.context.state.navigation.activeView === ActiveView.Collection) {
			this.context.render();
		}
	}


	public async chooseCollectionDirectory(): Promise<void> {
		try {
			const path = await this.context.apiClient.chooseDirectory();
			if (path) {
				this.state.directory = path;
				this.clearCollectionStatus();
				this.collectionLoadedSignature = null;
				this.collectionLoadingSignature = null;
				await this.saveCollectionDirectory();
				await this.loadCollectionIndex();
			}
		} catch (error) {
			this.state.error = errorMessage(error);
		}

		this.context.render();
	}


	public async changeCollectionScanMode(event: Event): Promise<void> {
		const scanMode = (event.target as HTMLSelectElement).value as CollectionScanMode;
		this.state.scanMode = scanMode;
		this.clearCollectionStatus();
		this.collectionLoadedSignature = null;
		this.collectionLoadingSignature = null;
		this.context.render();
		try {
			const result = await this.context.apiClient.setCollectionScanMode(scanMode);
			this.state.scanMode = result.collectionScanMode;
			await this.loadCollectionIndex();
		} catch (error) {
			this.state.error = errorMessage(error);
		}

		this.context.render();
	}


	public async refreshAfterThresholdChange(): Promise<void> {
		const refreshRevision = this.collectionRefreshRevision + 1;
		this.collectionRefreshRevision = refreshRevision;
		this.collectionLoadedSignature = null;
		this.collectionLoadingSignature = null;
		if (this.context.state.navigation.activeView !== ActiveView.Collection) {
			return;
		}

		if (this.state.activeJobId) {
			if (!this.state.scanEnabled) {
				await this.refreshRunningCollectionSpecies(this.state.activeJobId);
				this.context.render(true);
				return;
			}

			await this.stopActiveCollectionScan(this.state.activeJobId);
			if (refreshRevision !== this.collectionRefreshRevision) {
				return;
			}

			this.resumeCollectionScanIfEnabled(refreshRevision);
			this.context.render(true);
			return;
		}

		await this.loadCollectionIndex();
		if (refreshRevision !== this.collectionRefreshRevision) {
			return;
		}

		this.resumeCollectionScanIfEnabled(refreshRevision);
	}


	public async refreshAfterCorrection(): Promise<void> {
		if (this.context.state.navigation.activeView !== ActiveView.Collection || !this.state.directory.trim()) {
			return;
		}

		this.collectionLoadedSignature = null;
		this.collectionLoadingSignature = null;
		await this.loadCollectionIndex();
	}


	public async refreshAfterLanguageChange(): Promise<void> {
		this.collectionLoadedSignature = null;
		this.collectionLoadingSignature = null;
		if (this.state.status) {
			this.state.applyStatus(await this.withSpeciesNames(this.state.status));
		}

		if (!this.state.activeJobId) {
			await this.loadCollectionIndex();
		}
	}


	public async refreshAfterPredictionCorrection(correction: PredictionCorrectionResult | null): Promise<void> {
		if (!correction || this.context.state.navigation.activeView !== ActiveView.Collection) {
			return;
		}

		await this.refreshAfterCorrection();
		this.state.syncSelectionToOccurrence(correction.imagePath, correction.birdIndex, correction.speciesId);
		this.context.render();
	}


	public resumeCollectionScanIfEnabled(refreshRevision: number | null = null): void {
		const directory = this.state.directory.trim();
		if (this.context.state.navigation.activeView !== ActiveView.Collection || !directory || !this.state.scanEnabled || this.state.activeJobId || this.context.state.runtime.isDetecting()) {
			return;
		}

		void this.runCollectionScanForRevision(refreshRevision);
	}


	public async runCollectionScan(): Promise<void> {
		if (!this.state.canScan()) {
			return;
		}

		const saved = await this.saveCollectionScanEnabled(true);
		if (!saved) {
			return;
		}

		await this.runCollectionScanForRevision(null);
	}


	public async stopCollectionScan(): Promise<void> {
		await this.saveCollectionScanEnabled(false);
		const jobId = this.state.activeJobId;
		if (!jobId) {
			this.context.render();
			return;
		}

		await this.stopActiveCollectionScan(jobId);
	}


	public stopForNavigation(): void {
		if (!this.state.activeJobId) {
			return;
		}

		void this.stopActiveCollectionScan(this.state.activeJobId);
	}


	public async selectCollectionSpecies(button: HTMLElement): Promise<void> {
		const speciesId = button.dataset.speciesId;
		if (!speciesId) {
			return;
		}

		this.state.selectSpecies(speciesId);
		this.clearDetectionImageAndResult();
		this.context.render();
	}


	public async selectCollectionOccurrence(button: HTMLElement): Promise<void> {
		const index = Number(button.dataset.occurrenceIndex);
		const occurrence = this.state.selectOccurrence(index);
		if (occurrence) {
			this.clearDetectionResult();
		}

		this.context.render();
		if (occurrence) {
			await this.detectionController.loadCollectionOccurrencePrediction(occurrence);
		}
	}


	public backToCollectionSpecies(): void {
		this.state.selectedSpeciesId = null;
		this.state.selectedOccurrenceIndex = 0;
		this.state.occurrenceOpen = false;
		this.clearDetectionImageAndResult();
		this.context.render();
	}


	public backToCollectionOccurrences(): void {
		this.state.closeOccurrence();
		this.clearDetectionImageAndResult();
		this.context.render();
	}


	public async previousCollectionOccurrence(): Promise<void> {
		const occurrence = this.state.previousOccurrence();
		if (occurrence) {
			this.clearDetectionResult();
			await this.detectionController.loadCollectionOccurrencePrediction(occurrence);
		}
	}


	public async nextCollectionOccurrence(): Promise<void> {
		const occurrence = this.state.nextOccurrence();
		if (occurrence) {
			this.clearDetectionResult();
			await this.detectionController.loadCollectionOccurrencePrediction(occurrence);
		}
	}


	public async revealCollectionOccurrence(): Promise<void> {
		const occurrence = this.state.selectedOccurrence();
		if (!occurrence) {
			return;
		}

		try {
			await this.context.apiClient.revealInFileExplorer(occurrence.imagePath);
		} catch (error) {
			this.state.error = errorMessage(error);
			this.context.render();
		}
	}


	private updateCollectionSpeciesSearch(event: Event): void {
		const input = event.target as HTMLInputElement;
		const selectionStart = input.selectionStart ?? input.value.length;
		const selectionEnd = input.selectionEnd ?? selectionStart;
		this.state.speciesSearchQuery = input.value;
		this.context.render();
		this.restoreCollectionSpeciesSearchFocus(selectionStart, selectionEnd);
	}


	private handleCollectionClick(event: Event): void {
		const target = event.target;
		if (!(target instanceof Element)) {
			return;
		}

		const actionElement = target.closest<HTMLElement>("[data-action], #chooseCollectionDirectory, #scanCollection, #stopCollectionScan, #backToCollectionSpecies, #backToCollectionOccurrences, #previousCollectionOccurrence, #nextCollectionOccurrence, #revealCollectionOccurrence");
		if (!actionElement) {
			return;
		}

		if (actionElement.dataset.action === "select-collection-species") {
			void this.selectCollectionSpecies(actionElement);
			return;
		}

		if (actionElement.dataset.action === "select-collection-occurrence") {
			void this.selectCollectionOccurrence(actionElement);
			return;
		}

		if (actionElement.id === "chooseCollectionDirectory") {
			void this.chooseCollectionDirectory();
			return;
		}

		if (actionElement.id === "scanCollection") {
			void this.runCollectionScan();
			return;
		}

		if (actionElement.id === "stopCollectionScan") {
			void this.stopCollectionScan();
			return;
		}

		if (actionElement.id === "backToCollectionSpecies") {
			this.backToCollectionSpecies();
			return;
		}

		if (actionElement.id === "backToCollectionOccurrences") {
			this.backToCollectionOccurrences();
			return;
		}

		if (actionElement.id === "previousCollectionOccurrence") {
			void this.previousCollectionOccurrence();
			return;
		}

		if (actionElement.id === "nextCollectionOccurrence") {
			void this.nextCollectionOccurrence();
			return;
		}

		if (actionElement.id === "revealCollectionOccurrence") {
			void this.revealCollectionOccurrence();
		}
	}


	private restoreCollectionSpeciesSearchFocus(selectionStart: number, selectionEnd: number): void {
		const restore = (): void => {
			const input = document.querySelector<HTMLInputElement>("#collectionSpeciesSearch");
			if (!input) {
				return;
			}

			const nextSelectionStart = Math.min(selectionStart, input.value.length);
			const nextSelectionEnd = Math.min(selectionEnd, input.value.length);
			input.focus({ preventScroll: true });
			input.setSelectionRange(nextSelectionStart, nextSelectionEnd);
		};

		restore();
		window.requestAnimationFrame(restore);
	}


	private isTypingTarget(target: EventTarget | null): boolean {
		if (!(target instanceof HTMLElement)) {
			return false;
		}

		return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target.isContentEditable;
	}


	private async runCollectionScanForRevision(refreshRevision: number | null): Promise<void> {
		if (!this.state.canScan()) {
			return;
		}

		this.state.error = "";
		this.context.render();
		try {
			const jobThreshold = this.context.state.settings.acceptedClassificationThreshold;
			const job = await this.context.apiClient.startCollectionScan(this.state.directory, this.state.scanMode);
			if (refreshRevision !== null && refreshRevision !== this.collectionRefreshRevision) {
				await this.context.apiClient.stopCollectionScan(job.jobId);
				return;
			}

			this.collectionJobThreshold = jobThreshold;
			this.state.startScan(job.jobId);
			this.clearDetectionResult();
			this.context.render();
			await this.pollCollection(job.jobId);
		} catch (error) {
			this.state.applyStatus({ state: "error", total: 0, completed: 0, errors: 1, currentFile: "", message: errorMessage(error), error: errorMessage(error), species: [] });
			this.context.render();
		}
	}


	private async saveCollectionDirectory(): Promise<void> {
		await this.context.apiClient.setCollectionDirectory(this.state.directory);
	}


	private clearCollectionStatus(clearDetection = true): void {
		this.state.clear();
		if (clearDetection) {
			this.clearDetectionImageAndResult();
		}
	}


	private clearDetectionResult(): void {
		this.detectionState.clearResult();
		this.speciesCorrectionState.closeEditor();
		this.imageViewportState.reset();
	}


	private clearDetectionImageAndResult(): void {
		this.detectionState.clearImageAndResult();
		this.speciesCorrectionState.closeEditor();
		this.imageViewportState.reset();
	}


	private async saveCollectionScanEnabled(enabled: boolean): Promise<boolean> {
		const previousEnabled = this.state.scanEnabled;
		this.state.scanEnabled = enabled;
		this.context.render();
		try {
			const result = await this.context.apiClient.setCollectionScanEnabled(enabled);
			this.state.scanEnabled = result.collectionScanEnabled;
			return true;
		} catch (error) {
			this.state.scanEnabled = previousEnabled;
			this.state.error = errorMessage(error);
			this.context.render();
			return false;
		}
	}


	private async stopActiveCollectionScan(jobId: string): Promise<void> {
		try {
			const status = await this.withSpeciesNames(await this.context.apiClient.stopCollectionScan(jobId));
			this.state.applyStatus(status);
		} catch (error) {
			this.state.error = errorMessage(error);
		}

		this.context.render();
	}


	private async loadCollectionIndex(): Promise<void> {
		const signature = this.collectionSignature();
		if (!signature || this.state.activeJobId || this.collectionLoadedSignature === signature || this.collectionLoadingSignature === signature) {
			return;
		}

		this.collectionLoadingSignature = signature;
		try {
			const status = await this.withSpeciesNames(await this.context.apiClient.collectionIndex(this.state.directory, this.state.scanMode));
			if (this.state.activeJobId) {
				return;
			}

			if (status.state === "done") {
				this.state.applyStatus(status);
				this.collectionLoadedSignature = signature;
			} else {
				this.clearCollectionStatus(this.context.state.navigation.activeView === ActiveView.Collection);
				this.collectionLoadedSignature = null;
			}
		} catch (error) {
			this.state.error = errorMessage(error);
		} finally {
			if (this.collectionLoadingSignature === signature) {
				this.collectionLoadingSignature = null;
			}
		}
	}


	private collectionSignature(): string | null {
		const directory = this.state.directory.trim();
		if (!directory) {
			return null;
		}

		return `${directory}\n${this.state.scanMode}\n${this.context.state.settings.acceptedClassificationThreshold}\n${this.context.state.settings.appLanguage}`;
	}


	private async withSpeciesNames(status: CollectionJobStatus): Promise<CollectionJobStatus> {
		await this.ensureBirdNames();
		const birdNamesBySpecies = new Map(this.speciesCorrectionState.birdNames.map(item => [item.species_id, item]));
		return {
			...status,
			species: status.species.map(species => {
				const names = birdNamesBySpecies.get(species.speciesId);
				return {
					...species,
					name: names?.name ?? species.name,
					name_language: names?.name_language ?? species.name_language,
					name_lat: names?.name_lat ?? species.name_lat,
					occurrences: species.occurrences.map(occurrence => {
						const occurrenceNames = birdNamesBySpecies.get(occurrence.classification.species_id);
						return {
							...occurrence,
							classification: occurrenceNames ? { ...occurrence.classification, name: occurrenceNames.name, name_language: occurrenceNames.name_language, name_lat: occurrenceNames.name_lat } : occurrence.classification,
						};
					}),
				};
			}),
		};
	}


	private async ensureBirdNames(): Promise<void> {
		if (this.speciesCorrectionState.birdNamesLanguage === this.context.state.settings.appLanguage && this.speciesCorrectionState.birdNames.length > 0) {
			return;
		}

		await this.speciesCorrectionState.loadBirdNamesForLanguage(this.context.state.settings.appLanguage, language => this.context.apiClient.birdNames(language));
	}


	private async refreshRunningCollectionSpecies(jobId: string): Promise<void> {
		const runningStatus = this.state.status;
		if (!runningStatus || runningStatus.state !== "running") {
			return;
		}

		try {
			const cachedStatus = await this.withSpeciesNames(await this.context.apiClient.collectionIndex(this.state.directory, this.state.scanMode));
			if (this.state.activeJobId !== jobId) {
				return;
			}

			const latestStatus = this.state.status;
			if (!latestStatus || latestStatus.state !== "running") {
				return;
			}

			this.state.status = { ...latestStatus, species: cachedStatus.state === "done" ? cachedStatus.species : [] };
			if (this.state.selectedSpeciesId && !this.state.status.species.some(item => item.speciesId === this.state.selectedSpeciesId)) {
				this.state.selectedSpeciesId = null;
				this.state.selectedOccurrenceIndex = 0;
				this.state.occurrenceOpen = false;
				this.clearDetectionImageAndResult();
			}
		} catch (error) {
			this.state.error = errorMessage(error);
		}
	}


	private async pollCollection(jobId: string): Promise<void> {
		while (this.state.activeJobId === jobId) {
			const status = await this.withSpeciesNames(await this.context.apiClient.collectionStatus(jobId));
			this.state.applyStatus(status);
			if (status.state === "running" && this.collectionJobThreshold !== this.context.state.settings.acceptedClassificationThreshold) {
				await this.refreshRunningCollectionSpecies(jobId);
			}

			this.context.render(true);

			if (status.state !== "running") {
				this.collectionJobThreshold = null;
				if (status.state === "done") {
					await this.saveCollectionScanEnabled(false);
					this.collectionLoadedSignature = null;
					this.collectionLoadingSignature = null;
					await this.loadCollectionIndex();
					this.context.render(true);
				}

				return;
			}

			await delay(400);
		}
	}
}
