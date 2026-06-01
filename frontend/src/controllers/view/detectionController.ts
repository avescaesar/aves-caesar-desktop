import { DetectionState } from "../../state/detectionState";
import { ImageViewportState } from "../../state/imageViewportState";
import { SpeciesCorrectionState } from "../../state/speciesCorrectionState";
import { ActiveView, type BirdResult, type CollectionOccurrence, type PredictResponse } from "../../types";
import { delay, errorMessage } from "../../utils";
import type { AppControllerContext } from "../core/appControllerContext";
import type { EventBinder } from "../core/eventBinder";
import type { ViewController } from "./viewController";

export type PredictionCorrectionResult = { imagePath: string; birdIndex: number; speciesId: string };

export class DetectionController implements ViewController {
	public readonly view = ActiveView.Detection;
	private cardPulseTimer: number | null = null;
	private correctionSearchRenderTimer: number | null = null;


	public constructor(private readonly context: AppControllerContext, public readonly state: DetectionState, public readonly speciesCorrectionState: SpeciesCorrectionState, private readonly imageViewportState: ImageViewportState, private readonly updateCorrectionOptions: () => void, private readonly refreshCollectionAfterCorrection: (correction: PredictionCorrectionResult | null) => Promise<void>) {}


	public show(): void {
		this.context.state.navigation.activeView = this.view;
		this.state.reset();
		this.speciesCorrectionState.closeEditor();
		this.imageViewportState.reset();
		this.context.render();
	}


	public hide(): void {}


	public bindEvents(bindEvent: EventBinder, appElement: HTMLElement): void {
		document.querySelectorAll<HTMLButtonElement>("[data-action='choose-image']").forEach(button => bindEvent(button, "click", () => void this.chooseImage()));
		bindEvent(document.querySelector<HTMLButtonElement>("#chooseGpx"), "click", () => void this.chooseGpx());
		bindEvent(document.querySelector<HTMLButtonElement>("#predict"), "click", () => void this.predict());
		bindEvent(document.querySelector<HTMLButtonElement>("#predictInline"), "click", () => void this.predict());
		bindEvent(document.querySelector<HTMLInputElement>("#latitude"), "input", event => this.state.latitude = (event.target as HTMLInputElement).value);
		bindEvent(document.querySelector<HTMLInputElement>("#longitude"), "input", event => this.state.longitude = (event.target as HTMLInputElement).value);
		document.querySelectorAll<HTMLElement>(".detection-card").forEach(card => this.bindDetectionCard(card));
		document.querySelectorAll<HTMLButtonElement>(".bird-box__label").forEach(button => this.bindBirdBoxLabel(button));
		const correctionActionElements = document.querySelectorAll<HTMLElement>("[data-action='edit-correction'], [data-action='select-correction-species'], [data-action='clear-correction'], [data-action='cancel-correction']");
		this.logCorrectionEvent("correction_bind_events", { count: correctionActionElements.length, activeView: this.context.state.navigation.activeView, hasResult: Boolean(this.state.result) });
		bindEvent(appElement, "click", event => this.handleCorrectionClick(event));
		bindEvent(appElement, "input", event => this.handleCorrectionInput(event));
	}


	private bindDetectionCard(card: HTMLElement): void {
		if (card.dataset.detectionCardBound === "true") {
			return;
		}

		card.dataset.detectionCardBound = "true";
		card.addEventListener("mouseenter", () => this.highlightBirdBox(card.dataset.birdIndex || ""));
		card.addEventListener("mouseleave", () => this.clearBirdBoxHighlight());
		card.addEventListener("focusin", () => this.highlightBirdBox(card.dataset.birdIndex || ""));
		card.addEventListener("focusout", () => this.clearBirdBoxHighlight());
	}


	private bindBirdBoxLabel(button: HTMLButtonElement): void {
		if (button.dataset.birdBoxLabelBound === "true") {
			return;
		}

		button.dataset.birdBoxLabelBound = "true";
		button.addEventListener("click", () => this.navigateToBirdCard(button.dataset.birdIndex || ""));
	}


	public async beginCorrectionEdit(birdIndex: number): Promise<void> {
		if (!Number.isInteger(birdIndex) || birdIndex < 0) {
			this.logCorrectionEvent("correction_invalid_bird_index", { birdIndex });
			return;
		}

		this.logCorrectionEvent("correction_begin_edit", { birdIndex });
		this.speciesCorrectionState.openEditor(birdIndex);
		this.speciesCorrectionState.busy = this.speciesCorrectionState.birdNames.length === 0;
		this.context.render();
		try {
			await this.ensureCorrectionBirdNames();
			this.logCorrectionEvent("correction_bird_names_ready", { count: this.speciesCorrectionState.birdNames.length });
		} catch (error) {
			this.logCorrectionEvent("correction_bird_names_failed", { message: errorMessage(error) });
			this.speciesCorrectionState.error = errorMessage(error);
		} finally {
			this.speciesCorrectionState.busy = false;
		}

		this.context.render();
	}


	public updateCorrectionSearch(value: string): void {
		this.speciesCorrectionState.speciesSearchQuery = value;
		if (this.correctionSearchRenderTimer !== null) {
			window.clearTimeout(this.correctionSearchRenderTimer);
		}

		this.correctionSearchRenderTimer = window.setTimeout(() => {
			this.correctionSearchRenderTimer = null;
			this.updateCorrectionOptions();
		}, 200);
	}


	public cancelCorrectionEdit(): void {
		this.speciesCorrectionState.closeEditor();
		this.context.render();
	}


	public async applyPredictionCorrection(speciesId: string): Promise<PredictionCorrectionResult | null> {
		const imagePath = this.state.image?.path;
		const birdIndex = this.speciesCorrectionState.editingBirdIndex;
		if (!imagePath || birdIndex === null) {
			return null;
		}

		this.speciesCorrectionState.busy = true;
		this.context.render();
		try {
			this.logCorrectionEvent("correction_apply", { imagePath, birdIndex, speciesId });
			await this.context.apiClient.setPredictionCorrection(imagePath, birdIndex, speciesId);
			await this.reloadCurrentPrediction();
			const correctedSpeciesId = this.state.result?.birds[birdIndex]?.classification[0]?.species_id ?? speciesId;
			this.speciesCorrectionState.closeEditor();
			this.context.render();
			return { imagePath, birdIndex, speciesId: correctedSpeciesId };
		} catch (error) {
			this.logCorrectionEvent("correction_apply_failed", { imagePath, birdIndex, speciesId, message: errorMessage(error) });
			this.speciesCorrectionState.error = errorMessage(error);
			this.speciesCorrectionState.busy = false;
			this.context.render();
			return null;
		}
	}


	public async clearPredictionCorrection(): Promise<PredictionCorrectionResult | null> {
		const imagePath = this.state.image?.path;
		const birdIndex = this.speciesCorrectionState.editingBirdIndex;
		if (!imagePath || birdIndex === null) {
			return null;
		}

		this.speciesCorrectionState.busy = true;
		this.context.render();
		try {
			this.logCorrectionEvent("correction_clear", { imagePath, birdIndex });
			await this.context.apiClient.clearPredictionCorrection(imagePath, birdIndex);
			await this.reloadCurrentPrediction();
			const speciesId = this.state.result?.birds[birdIndex]?.classification[0]?.species_id ?? "";
			this.speciesCorrectionState.closeEditor();
			this.context.render();
			return speciesId ? { imagePath, birdIndex, speciesId } : null;
		} catch (error) {
			this.logCorrectionEvent("correction_clear_failed", { imagePath, birdIndex, message: errorMessage(error) });
			this.speciesCorrectionState.error = errorMessage(error);
			this.speciesCorrectionState.busy = false;
			this.context.render();
			return null;
		}
	}


	public async chooseImage(): Promise<void> {
		try {
			const image = await this.context.apiClient.chooseImage();
			if (!image) {
				return;
			}

			this.state.selectImage(image);
			this.speciesCorrectionState.closeEditor();
			this.imageViewportState.reset();
		} catch (error) {
			this.state.setRawStatus(errorMessage(error));
		}

		this.context.render();
	}


	public async chooseGpx(): Promise<void> {
		if (!this.state.image) {
			this.state.setStatus("status.selectImageBeforeGpx");
			this.context.render();
			return;
		}

		try {
			const paths = await this.context.apiClient.chooseGpx();
			if (!paths || paths.length === 0) {
				return;
			}

			this.state.gpxPaths = paths;
			const match = await this.context.apiClient.matchGpx(paths, this.state.image.datetime);
			if (!match) {
				this.state.setStatus("status.gpxNoPoint");
			} else {
				this.state.latitude = String(match.latitude);
				this.state.longitude = String(match.longitude);
				if (match.secondsDelta == null) {
					this.state.setStatus("status.gpxFirstPoint");
				} else {
					this.state.setStatus("status.gpxMatched", { seconds: Math.round(match.secondsDelta) });
				}
			}
		} catch (error) {
			this.state.setRawStatus(errorMessage(error));
		}

		this.context.render();
	}


	public async predict(): Promise<void> {
		if (!this.state.image) {
			return;
		}

		this.state.loading = true;
		this.state.setStatus("status.predicting");
		this.state.activeJobId = null;
		this.state.result = null;
		this.context.render();

		try {
			const job = await this.context.apiClient.startPredict({ imagePath: this.state.image.path, latitude: this.state.latitude, longitude: this.state.longitude, datetime: this.state.image.datetime });
			this.state.activeJobId = job.jobId;
			await this.pollPrediction(job.jobId);
		} catch (error) {
			this.state.setRawStatus(errorMessage(error));
			this.state.loading = false;
			this.state.activeJobId = null;
			this.context.render();
		}
	}


	public async loadCollectionOccurrencePrediction(occurrence: CollectionOccurrence): Promise<void> {
		this.state.image = { path: occurrence.imagePath, latitude: occurrence.usedLatitude ?? null, longitude: occurrence.usedLongitude ?? null, datetime: occurrence.usedDatetime ?? null, thumbnailDataUrl: occurrence.thumbnailDataUrl };
		this.state.latitude = occurrence.usedLatitude == null ? "" : String(occurrence.usedLatitude);
		this.state.longitude = occurrence.usedLongitude == null ? "" : String(occurrence.usedLongitude);
		this.state.loading = true;
		this.state.result = null;
		this.state.activeJobId = null;
		this.state.setStatus("collection.loadingCachedPrediction");
		this.context.render();
		try {
			const result = await this.context.apiClient.cachedPredictionPreview({ imagePath: occurrence.imagePath, latitude: occurrence.usedLatitude ?? null, longitude: occurrence.usedLongitude ?? null, datetime: occurrence.usedDatetime ?? null });
			this.state.result = this.sortedPredictionResult(await this.withSpeciesNames(result));
			this.applyPredictionResultStatus();
		} catch (error) {
			this.state.setRawStatus(errorMessage(error));
		}

		this.state.loading = false;
		this.state.activeJobId = null;
		this.context.render();
	}


	public applyPredictionResultStatus(): void {
		if (!this.state.result) {
			return;
		}

		if (this.state.result.birds.length === 0) {
			this.state.setStatus("status.noBirdsDetected");
			return;
		}

		this.state.setStatus("status.detected", { count: this.state.result.birds.length });
	}


	private async ensureCorrectionBirdNames(): Promise<void> {
		if (this.speciesCorrectionState.birdNamesLanguage === this.context.state.settings.appLanguage && this.speciesCorrectionState.birdNames.length > 0) {
			return;
		}

		this.logCorrectionEvent("correction_bird_names_loading");
		await this.speciesCorrectionState.loadBirdNamesForLanguage(this.context.state.settings.appLanguage, language => this.context.apiClient.birdNames(language));
	}


	private handleCorrectionClick(event: Event): void {
		const target = event.target;
		if (!(target instanceof Element)) {
			return;
		}

		const actionElement = target.closest<HTMLElement>("[data-action='edit-correction'], [data-action='select-correction-species'], [data-action='clear-correction'], [data-action='cancel-correction']");
		if (!actionElement) {
			return;
		}

		this.logCorrectionEvent("correction_app_click", { action: actionElement.dataset.action, birdIndex: actionElement.dataset.birdIndex, speciesId: actionElement.dataset.speciesId });
		event.preventDefault();
		this.runCorrectionAction(actionElement);
	}


	private runCorrectionAction(actionElement: HTMLElement): void {
		this.logCorrectionEvent("correction_action", { action: actionElement.dataset.action, birdIndex: actionElement.dataset.birdIndex, speciesId: actionElement.dataset.speciesId });
		if (actionElement.dataset.action === "edit-correction") {
			void this.beginCorrectionEdit(Number(actionElement.dataset.birdIndex));
			return;
		}

		if (actionElement.dataset.action === "select-correction-species") {
			void this.applyCorrectionAndRefreshCollection(actionElement.dataset.speciesId || "");
			return;
		}

		if (actionElement.dataset.action === "clear-correction") {
			void this.clearCorrectionAndRefreshCollection();
			return;
		}

		if (actionElement.dataset.action === "cancel-correction") {
			this.cancelCorrectionEdit();
		}
	}


	private handleCorrectionInput(event: Event): void {
		const target = event.target;
		if (!(target instanceof HTMLInputElement) || !target.classList.contains("correction-search-input")) {
			return;
		}

		this.updateCorrectionSearch(target.value);
	}


	private async applyCorrectionAndRefreshCollection(speciesId: string): Promise<void> {
		if (!speciesId) {
			return;
		}

		const correction = await this.applyPredictionCorrection(speciesId);
		await this.refreshCollectionAfterCorrection(correction);
	}


	private async clearCorrectionAndRefreshCollection(): Promise<void> {
		const correction = await this.clearPredictionCorrection();
		await this.refreshCollectionAfterCorrection(correction);
	}


	private logCorrectionEvent(event: string, payload: Record<string, unknown> = {}): void {
		this.context.apiClient.logFrontendEvent(event, payload);
	}


	private async reloadCurrentPrediction(): Promise<void> {
		const image = this.state.image;
		if (!image) {
			return;
		}

		const result = await this.context.apiClient.cachedPredictionPreview({ imagePath: image.path, latitude: this.state.latitude, longitude: this.state.longitude, datetime: image.datetime });
		this.state.result = this.sortedPredictionResult(await this.withSpeciesNames(result));
		this.applyPredictionResultStatus();
	}


	private async pollPrediction(jobId: string): Promise<void> {
		while (this.state.activeJobId === jobId) {
			const status = await this.context.apiClient.predictionStatus(jobId);
			if (this.state.activeJobId !== jobId) {
				return;
			}

			if (status.state === "running") {
				await delay(250);
				continue;
			}

			if (status.state === "done" && status.result) {
				this.state.result = this.sortedPredictionResult(await this.withSpeciesNames(status.result));
				this.applyPredictionResultStatus();
			} else {
				if (status.error) {
					this.state.setRawStatus(status.error);
				} else {
					this.state.setStatus("status.predictionFailed");
				}
			}

			this.state.loading = false;
			this.state.activeJobId = null;
			this.context.render();
			return;
		}
	}


	private highlightBirdBox(index: string): void {
		document.querySelectorAll<HTMLElement>(".bird-box").forEach(box => box.classList.toggle("is-highlighted", box.dataset.birdIndex === index));
	}


	private clearBirdBoxHighlight(): void {
		document.querySelectorAll<HTMLElement>(".bird-box").forEach(box => box.classList.remove("is-highlighted"));
	}


	private navigateToBirdCard(index: string): void {
		const cards = Array.from(document.querySelectorAll<HTMLElement>(".detection-card"));
		const card = cards.find(item => item.dataset.birdIndex === index);
		if (!card) {
			return;
		}

		if (card instanceof HTMLDetailsElement) {
			card.open = true;
		}

		this.highlightBirdBox(index);
		card.scrollIntoView({ behavior: "smooth", block: "center" });
		card.classList.remove("is-pulsed");
		void card.offsetWidth;
		card.classList.add("is-pulsed");

		if (this.cardPulseTimer !== null) {
			window.clearTimeout(this.cardPulseTimer);
		}

		this.cardPulseTimer = window.setTimeout(() => {
			card.classList.remove("is-pulsed");
			this.clearBirdBoxHighlight();
			this.cardPulseTimer = null;
		}, 1000);
	}


	private sortedPredictionResult(result: PredictResponse): PredictResponse {
		return { ...result, birds: [...result.birds].sort((firstBird, secondBird) => this.birdLeft(firstBird) - this.birdLeft(secondBird) || this.birdTop(firstBird) - this.birdTop(secondBird)) };
	}


	private async withSpeciesNames(result: PredictResponse): Promise<PredictResponse> {
		await this.ensureCorrectionBirdNames();
		const birdNamesBySpecies = new Map(this.speciesCorrectionState.birdNames.map(item => [item.species_id, item]));
		return {
			...result,
			birds: result.birds.map(bird => ({
				...bird,
				classification: bird.classification.map(classification => {
					const names = birdNamesBySpecies.get(classification.species_id);
					return names ? { ...classification, name: names.name, name_language: names.name_language, name_lat: names.name_lat } : classification;
				}),
			})),
		};
	}


	private birdLeft(bird: BirdResult): number {
		return bird.box[0] ?? 0;
	}


	private birdTop(bird: BirdResult): number {
		return bird.box[1] ?? 0;
	}
}

