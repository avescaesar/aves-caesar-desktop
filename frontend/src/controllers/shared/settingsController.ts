import { CollectionState } from "../../state/collectionState";
import { DetectionState } from "../../state/detectionState";
import { loadTranslations } from "../../i18n/translations";
import { SettingsState } from "../../state/settingsState";
import { SpeciesCorrectionState } from "../../state/speciesCorrectionState";
import { type AppLanguagePreference } from "../../types";
import { errorMessage } from "../../utils";
import type { AppControllerContext } from "../core/appControllerContext";
import type { EventBinder } from "../core/eventBinder";
import type { CollectionController } from "../view/collectionController";

const DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD_PERCENT = 50;
const DEFAULT_GPX_MATCH_TOLERANCE_SECONDS = 300;
const MAX_GPX_MATCH_TOLERANCE_SECONDS = 86400;

export class SettingsController {
	private acceptedClassificationThresholdIgnoreChangeUntilMs = 0;
	private acceptedClassificationThresholdSavePromise: Promise<void> = Promise.resolve();


	public constructor(private readonly context: AppControllerContext, public readonly state: SettingsState, private readonly collectionState: CollectionState, private readonly detectionState: DetectionState, private readonly speciesCorrectionState: SpeciesCorrectionState, private readonly collectionController: CollectionController) {}


	public bindEvents(bindEvent: EventBinder): void {
		bindEvent(document.querySelector<HTMLButtonElement>("#openSettings"), "click", () => this.openSettings());
		bindEvent(document.querySelector<HTMLButtonElement>("#closeSettings"), "click", () => this.closeSettings());
		bindEvent(document.querySelector<HTMLButtonElement>("#clearPredictionCache"), "click", () => void this.clearPredictionCache());
		bindEvent(document.querySelector<HTMLButtonElement>("#exportLogs"), "click", () => void this.exportLogs());
		bindEvent(document.querySelector<HTMLSelectElement>("#appLanguagePreference"), "change", event => void this.changeAppLanguagePreference(event));
		bindEvent(document.querySelector<HTMLInputElement>("#acceptedClassificationThreshold"), "input", event => this.updateAcceptedClassificationThresholdPreview(event));
		bindEvent(document.querySelector<HTMLInputElement>("#acceptedClassificationThreshold"), "change", event => void this.changeAcceptedClassificationThreshold(event));
		bindEvent(document.querySelector<HTMLInputElement>("#acceptedClassificationThreshold"), "dblclick", event => void this.resetAcceptedClassificationThreshold(event));
		bindEvent(document.querySelector<HTMLInputElement>("#gpxMatchToleranceSeconds"), "change", event => void this.changeGpxMatchToleranceSeconds(event));
		bindEvent(document.querySelector<HTMLInputElement>("#gpxMatchToleranceSeconds"), "dblclick", event => void this.resetGpxMatchToleranceSeconds(event));
	}


	public openSettings(): void {
		this.state.modalOpen = true;
		this.state.cacheMessage = "";
		this.context.render();
	}


	public closeSettings(): void {
		this.state.modalOpen = false;
		this.context.render();
	}


	public async clearPredictionCache(): Promise<void> {
		this.state.cacheBusy = true;
		this.state.cacheMessage = "";
		this.context.render();
		try {
			const result = await this.context.apiClient.clearPredictionCache();
			this.detectionState.clearResult();
			this.collectionState.clear();
			this.speciesCorrectionState.closeEditor();
			this.state.cacheMessage = this.context.text("settings.cacheCleared", { count: result.clearedEntries, thumbnails: result.clearedCollectionThumbnails });
		} catch (error) {
			this.state.cacheMessage = errorMessage(error);
		}

		this.state.cacheBusy = false;
		this.context.render();
	}


	public async exportLogs(): Promise<void> {
		this.state.logsBusy = true;
		this.state.cacheMessage = "";
		this.context.render();
		try {
			const result = await this.context.apiClient.exportLogs();
			this.state.cacheMessage = this.context.text("settings.logsExported", { count: result.logCount, path: result.zipPath });
		} catch (error) {
			this.state.cacheMessage = errorMessage(error);
		}

		this.state.logsBusy = false;
		this.context.render();
	}


	public async changeAppLanguagePreference(event: Event): Promise<void> {
		const preference = (event.target as HTMLSelectElement).value as AppLanguagePreference;
		try {
			const result = await this.context.apiClient.setAppLanguagePreference(preference);
			this.state.setAppLanguagePreference(result.appLanguagePreference);
			this.speciesCorrectionState.resetCurrentBirdNames();
			await loadTranslations(this.state.appLanguage);
			await this.collectionController.refreshAfterLanguageChange();
		} catch (error) {
			this.state.cacheMessage = errorMessage(error);
		} finally {
			this.context.render();
		}
	}


	public async changeAcceptedClassificationThreshold(event: Event): Promise<void> {
		if (Date.now() < this.acceptedClassificationThresholdIgnoreChangeUntilMs) {
			return;
		}

		const input = event.target as HTMLInputElement;
		await this.saveAcceptedClassificationThreshold(this.thresholdPercentFromInput(input));
	}


	public async resetAcceptedClassificationThreshold(event: Event): Promise<void> {
		event.preventDefault();
		this.acceptedClassificationThresholdIgnoreChangeUntilMs = Date.now() + 250;
		const input = event.target as HTMLInputElement;
		this.updateAcceptedClassificationThresholdInput(input, DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD_PERCENT);
		await this.saveAcceptedClassificationThreshold(DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD_PERCENT);
	}


	public updateAcceptedClassificationThresholdPreview(event: Event): void {
		const input = event.target as HTMLInputElement;
		const thresholdPercent = this.thresholdPercentFromInput(input);
		this.updateAcceptedClassificationThresholdInput(input, thresholdPercent);
	}


	public async changeGpxMatchToleranceSeconds(event: Event): Promise<void> {
		const input = event.target as HTMLInputElement;
		await this.saveGpxMatchToleranceSeconds(this.gpxMatchToleranceSecondsFromInput(input));
	}


	public async resetGpxMatchToleranceSeconds(event: Event): Promise<void> {
		event.preventDefault();
		const input = event.target as HTMLInputElement;
		input.value = String(DEFAULT_GPX_MATCH_TOLERANCE_SECONDS);
		await this.saveGpxMatchToleranceSeconds(DEFAULT_GPX_MATCH_TOLERANCE_SECONDS);
	}


	private updateAcceptedClassificationThresholdInput(input: HTMLInputElement, thresholdPercent: number): void {
		input.value = String(thresholdPercent);
		input.style.setProperty("--threshold-percent", `${thresholdPercent}%`);
		this.state.acceptedClassificationThreshold = thresholdPercent / 100;
		const output = document.querySelector<HTMLOutputElement>("#acceptedClassificationThresholdValue");
		if (output) {
			output.textContent = `${thresholdPercent}%`;
		}
	}


	private async saveAcceptedClassificationThreshold(thresholdPercent: number): Promise<void> {
		const threshold = thresholdPercent / 100;
		this.state.acceptedClassificationThreshold = threshold;
		const savePromise = this.acceptedClassificationThresholdSavePromise.then(async () => {
			const result = await this.context.apiClient.setAcceptedClassificationThreshold(threshold);
			this.state.acceptedClassificationThreshold = result.acceptedClassificationThreshold;
			await this.collectionController.refreshAfterThresholdChange();
		});
		this.acceptedClassificationThresholdSavePromise = savePromise.then(() => undefined, () => undefined);

		try {
			await savePromise;
		} catch (error) {
			this.state.cacheMessage = errorMessage(error);
		} finally {
			this.context.render();
		}
	}


	private thresholdPercentFromInput(input: HTMLInputElement): number {
		const value = Number(input.value);
		return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD_PERCENT;
	}


	private gpxMatchToleranceSecondsFromInput(input: HTMLInputElement): number {
		const value = Number(input.value);
		return Number.isFinite(value) ? Math.round(Math.max(1, Math.min(MAX_GPX_MATCH_TOLERANCE_SECONDS, value))) : DEFAULT_GPX_MATCH_TOLERANCE_SECONDS;
	}


	private async saveGpxMatchToleranceSeconds(seconds: number): Promise<void> {
		this.state.gpxMatchToleranceSeconds = seconds;
		try {
			const result = await this.context.apiClient.setGpxMatchToleranceSeconds(seconds);
			this.state.gpxMatchToleranceSeconds = result.gpxMatchToleranceSeconds;
		} catch (error) {
			this.state.cacheMessage = errorMessage(error);
		} finally {
			this.context.render();
		}
	}

}
