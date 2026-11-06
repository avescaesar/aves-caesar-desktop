import { CollectionState } from "../../state/collectionState";
import { DetectionState } from "../../state/detectionState";
import { ImageViewportState } from "../../state/imageViewportState";
import { SpeciesCorrectionState } from "../../state/speciesCorrectionState";
import { ActiveView, type CollectionJobStatus, type CollectionScanMode } from "../../types";
import { delay, errorMessage } from "../../utils";
import { openEbirdRecordExport } from "./ebirdExport";
import type { AppControllerContext } from "../core/appControllerContext";
import type { DetectionController, PredictionCorrectionResult } from "./detectionController";
import type { EventBinder } from "../core/eventBinder";
import type { ViewController } from "./viewController";

export class CollectionController implements ViewController {
	public readonly view = ActiveView.Collection;
	private collectionSelectionDrag: { startX: number; startY: number; currentX: number; currentY: number; grid: HTMLElement; additive: boolean; moved: boolean; marquee: HTMLElement | null } | null = null;
	private suppressSelectionClick = false;
	private collectionJobThreshold: number | null = null;
	private collectionLoadedSignature: string | null = null;
	private collectionLoadingSignature: string | null = null;
	private collectionRefreshRevision = 0;
	private scanRequestRevision = 0;
	private scanSettingRevision = 0;


	public constructor(private readonly context: AppControllerContext, public readonly state: CollectionState, private readonly detectionState: DetectionState, private readonly speciesCorrectionState: SpeciesCorrectionState, private readonly imageViewportState: ImageViewportState, private readonly detectionController: DetectionController) {}


	public bindEvents(bindEvent: EventBinder): void {
		bindEvent(document.querySelector<HTMLInputElement>("#collectionSpeciesSearch"), "input", event => this.updateCollectionSpeciesSearch(event));
		bindEvent(document.querySelector<HTMLElement>(".collection-view"), "change", event => this.updateCollectionFilters(event));
		bindEvent(document.querySelector<HTMLSelectElement>("#collectionScanMode"), "change", event => void this.changeCollectionScanMode(event));
		bindEvent(document.querySelector<HTMLElement>(".collection-view"), "click", event => this.handleCollectionClick(event));
		bindEvent(document.querySelector<HTMLElement>(".collection-view"), "pointerdown", event => this.beginCollectionSelection(event as PointerEvent));
		bindEvent(document, "pointermove", event => this.updateCollectionSelection(event as PointerEvent));
		bindEvent(document, "pointerup", event => this.finishCollectionSelection(event as PointerEvent));
		bindEvent(document, "pointercancel", event => this.cancelCollectionSelection(event as PointerEvent));
		bindEvent(document, "click", event => this.suppressPostDragClick(event), { capture: true });
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

		const revision = this.scanRequestRevision;
		this.state.starting = true;
		const saved = await this.saveCollectionScanEnabled(true);
		this.state.starting = false;
		if (!saved || revision !== this.scanRequestRevision) {
			this.state.stopping = false;
			this.context.render();
			return;
		}

		await this.runCollectionScanForRevision(null);
	}


	public async stopCollectionScan(): Promise<void> {
		if (this.state.stopping) {
			return;
		}
		this.scanRequestRevision += 1;
		const jobId = this.state.activeJobId;
		if (!jobId && this.state.starting) {
			this.state.stopping = true;
		}
		// Send Stop immediately; saving the preference must not delay cancellation.
		await Promise.all([
			jobId ? this.stopActiveCollectionScan(jobId) : Promise.resolve(),
			this.saveCollectionScanEnabled(false),
		]);
	}


	public stopForNavigation(): void {
		this.scanRequestRevision += 1;
		if (!this.state.activeJobId) {
			this.state.stopping = this.state.starting;
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


	private updateCollectionFilters(event: Event): void {
		const target = event.target;
		if (!(target instanceof HTMLSelectElement || target instanceof HTMLInputElement)) {
			return;
		}

		if (target.id === "collectionFamilyFilter") {
			this.state.familyFilter = target.value;
		} else if (target.id === "collectionDateFrom") {
			this.state.dateFrom = target.value;
		} else if (target.id === "collectionDateTo") {
			this.state.dateTo = target.value;
		} else if (target.id === "collectionGpsFilter") {
			this.state.gpsFilter = target.value === "withGps" || target.value === "withoutGps" ? target.value : "all";
		} else if (target.id === "collectionConfidenceFilter") {
			const value = target.value;
			this.state.confidenceFilter = value === "manual" || value === "low" || value === "medium" || value === "high" ? value : "all";
		} else if (target.id === "collectionSpeciesSort") {
			const value = target.value;
			this.state.speciesSortOrder = value === "family" || value === "date" || value === "location" || value === "imageCount" || value === "confidence" ? value : "name";
		} else {
			return;
		}

		this.context.render();
	}


	private handleCollectionClick(event: Event): void {
		const target = event.target;
		if (!(target instanceof Element)) {
			return;
		}

		const actionElement = target.closest<HTMLElement>("[data-action], #chooseCollectionDirectory, #scanCollection, #stopCollectionScan, #backToCollectionSpecies, #backToCollectionOccurrences, #previousCollectionOccurrence, #nextCollectionOccurrence, #revealCollectionOccurrence, #exportEbirdRecords, #removeSelectedSpecies");
		if (!actionElement) {
			return;
		}

		if (actionElement.dataset.action === "select-collection-species") {
			void this.selectCollectionSpecies(actionElement);
			return;
		}

		if (actionElement.dataset.action === "toggle-ebird-species") {
			const speciesId = actionElement.dataset.speciesId;
			if (speciesId) {
				this.state.toggleSpeciesExportSelection(speciesId);
				this.context.render();
			}
			return;
		}

		if (actionElement.dataset.action === "remove-collection-species") {
			const speciesId = actionElement.dataset.speciesId;
			if (speciesId) {
				this.state.removeSpecies(speciesId);
				this.context.render();
			}
			return;
		}

		if (actionElement.dataset.action === "select-collection-occurrence") {
			void this.selectCollectionOccurrence(actionElement);
			return;
		}

		if (actionElement.dataset.action === "remove-collection-image") {
			const imagePath = actionElement.dataset.imagePath;
			if (imagePath) {
				this.state.removeImage(imagePath);
				this.context.render();
			}
			return;
		}

		if (actionElement.dataset.action === "set-collection-key-photo") {
			const speciesId = actionElement.dataset.speciesId;
			const imagePath = actionElement.dataset.imagePath;
			const birdIndex = Number(actionElement.dataset.birdIndex);
			const occurrence = this.state.species().find(item => item.speciesId === speciesId)?.occurrences.find(item => item.imagePath === imagePath && item.birdIndex === birdIndex);
			if (speciesId && occurrence) {
				this.state.setKeyPhoto(speciesId, occurrence);
				this.context.render();
			}
			return;
		}

		if (actionElement.dataset.action === "restore-collection-items") {
			this.state.restoreRemovedItems();
			this.context.render();
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

		if (actionElement.id === "exportEbirdRecords") {
			openEbirdRecordExport(this.state.selectedExportSpecies());
			return;
		}

		if (actionElement.id === "removeSelectedSpecies") {
			this.state.removeSelectedSpecies();
			this.context.render();
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


	private beginCollectionSelection(event: PointerEvent): void {
		if (event.pointerType !== "mouse" || event.button !== 0 || !(event.target instanceof Element)) {
			return;
		}

		const list = event.target.closest<HTMLElement>(".collection-species-list");
		const grid = list?.querySelector<HTMLElement>(".collection-grid");
		if (!list || !grid || event.target.closest(".collection-species-filters, .collection-export-select, .collection-remove-button, input, select, textarea, a")) {
			return;
		}

		this.collectionSelectionDrag = {
			startX: event.clientX,
			startY: event.clientY,
			currentX: event.clientX,
			currentY: event.clientY,
			grid,
			additive: event.ctrlKey || event.metaKey || event.shiftKey,
			moved: false,
			marquee: null,
		};
	}


	private updateCollectionSelection(event: PointerEvent): void {
		const drag = this.collectionSelectionDrag;
		if (!drag) return;
		drag.currentX = event.clientX;
		drag.currentY = event.clientY;
		if (!drag.moved && Math.hypot(drag.currentX - drag.startX, drag.currentY - drag.startY) < 5) return;

		if (!drag.moved) {
			drag.moved = true;
			drag.marquee = document.createElement("div");
			drag.marquee.className = "collection-selection-marquee";
			document.body.append(drag.marquee);
			document.querySelector(".collection-view")?.classList.add("is-selecting-species");
		}

		event.preventDefault();
		const left = Math.min(drag.startX, drag.currentX);
		const top = Math.min(drag.startY, drag.currentY);
		const width = Math.abs(drag.currentX - drag.startX);
		const height = Math.abs(drag.currentY - drag.startY);
		Object.assign(drag.marquee!.style, { left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px` });
	}


	private finishCollectionSelection(event: PointerEvent): void {
		const drag = this.collectionSelectionDrag;
		if (!drag) return;
		if (drag.moved) {
			this.updateCollectionSelection(event);
			const selection = { left: Math.min(drag.startX, drag.currentX), right: Math.max(drag.startX, drag.currentX), top: Math.min(drag.startY, drag.currentY), bottom: Math.max(drag.startY, drag.currentY) };
			if (!drag.additive) this.state.clearSpeciesExportSelection();
			drag.grid.querySelectorAll<HTMLElement>(".collection-species-card[data-species-id]").forEach(card => {
				const bounds = card.getBoundingClientRect();
				if (bounds.right >= selection.left && bounds.left <= selection.right && bounds.bottom >= selection.top && bounds.top <= selection.bottom) {
					const speciesId = card.dataset.speciesId;
					if (speciesId) this.state.selectedSpeciesIds.add(speciesId);
				}
			});
			this.suppressSelectionClick = true;
			window.setTimeout(() => { this.suppressSelectionClick = false; }, 0);
			this.context.render();
		}
		this.clearCollectionSelectionDrag();
	}


	private cancelCollectionSelection(event: PointerEvent): void {
		if (this.collectionSelectionDrag) this.clearCollectionSelectionDrag();
	}


	private clearCollectionSelectionDrag(): void {
		this.collectionSelectionDrag?.marquee?.remove();
		this.collectionSelectionDrag = null;
		document.querySelector(".collection-view")?.classList.remove("is-selecting-species");
	}


	private suppressPostDragClick(event: Event): void {
		if (!this.suppressSelectionClick || !(event.target instanceof Element) || !event.target.closest(".collection-view")) return;
		event.preventDefault();
		event.stopPropagation();
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

		const revision = this.scanRequestRevision;
		this.state.starting = true;
		let launchPending = true;
		this.state.error = "";
		this.context.render();
		try {
			const jobThreshold = this.context.state.settings.acceptedClassificationThreshold;
			const job = await this.context.apiClient.startCollectionScan(this.state.directory, this.state.scanMode);
			if (revision !== this.scanRequestRevision || !this.state.scanEnabled
				|| (refreshRevision !== null && refreshRevision !== this.collectionRefreshRevision)) {
				await this.context.apiClient.stopCollectionScan(job.jobId);
				return;
			}

			this.collectionJobThreshold = jobThreshold;
			this.state.startScan(job.jobId);
			this.state.starting = false;
			launchPending = false;
			this.clearDetectionResult();
			this.context.render();
			await this.pollCollection(job.jobId);
		} catch (error) {
			if (revision === this.scanRequestRevision) {
				this.state.applyStatus({ state: "error", total: 0, completed: 0, errors: 1, currentFile: "", message: errorMessage(error), error: errorMessage(error), species: [] });
			}
		} finally {
			if (launchPending) {
				this.state.starting = false;
				this.state.stopping = false;
			}
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
		const revision = ++this.scanSettingRevision;
		const previousEnabled = this.state.scanEnabled;
		this.state.scanEnabled = enabled;
		this.context.render();
		try {
			const result = await this.context.apiClient.setCollectionScanEnabled(enabled);
			if (revision === this.scanSettingRevision) {
				this.state.scanEnabled = result.collectionScanEnabled;
			}
			return true;
		} catch (error) {
			if (revision === this.scanSettingRevision) {
				this.state.scanEnabled = previousEnabled;
			}
			this.state.error = errorMessage(error);
			this.context.render();
			return false;
		}
	}


	private async stopActiveCollectionScan(jobId: string): Promise<void> {
		if (this.state.stopping) {
			return;
		}
		this.state.stopping = true;
		this.context.render();
		try {
			const status = await this.context.apiClient.stopCollectionScan(jobId);
			if (this.state.activeJobId === jobId) {
				this.state.applyStatus({ ...status, species: this.state.species() });
			}
		} catch (error) {
			this.state.error = errorMessage(error);
		} finally {
			this.state.stopping = false;
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
					family_name: names?.family_name ?? species.family_name,
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
			if (this.state.activeJobId !== jobId) {
				return;
			}
			if (this.state.stopping) {
				await delay(400);
				continue;
			}
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
