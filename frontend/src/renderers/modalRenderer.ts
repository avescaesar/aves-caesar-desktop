import { iconArchive, iconDownload, iconGlobe, iconPlay, iconPlug, iconRefresh, iconSquare, iconTrash, iconX } from "../icons";
import type { CollectionState } from "../state/collectionState";
import type { DetectionState } from "../state/detectionState";
import type { LightroomState } from "../state/lightroomState";
import type { OrganizationState } from "../state/organizationState";
import type { RuntimeState } from "../state/runtimeState";
import type { SettingsState } from "../state/settingsState";
import type { SpeciesCorrectionState } from "../state/speciesCorrectionState";
import type { UpdateState } from "../state/updateState";
import type { BirdName, BirdResult, Classification } from "../types";
import { escapeHtml, formatTimeOfDay } from "../utils";
import type { RendererContext } from "./rendererContext";

const ORGANIZATION_DOM = {
	vertical: "organization",
	entities: {
		progress: "progress",
		destinationConflict: "destination-conflict",
	},
	actions: {
		close: "close",
		cancel: "cancel",
		confirm: "confirm",
		stop: "stop",
	},
} as const;

export class ModalRenderer {
	private static readonly CORRECTION_SUGGESTION_LIMIT = 8;


	public constructor(private readonly context: RendererContext, private readonly states: ModalRendererStates) {}


	public render(): string {
		return `
				${this.renderNonEmptyDestinationModal()}
				${this.renderOrganizationProgressModal()}
				${this.renderCorrectionModal()}
				${this.renderSettingsModal()}
				${this.renderLightroomUpgradeModal()}
				${this.renderUpdateModal()}
		`;
	}


	public updateCorrectionOptions(): boolean {
		const options = document.querySelector<HTMLElement>(".correction-options");
		if (!options) {
			return false;
		}

		options.innerHTML = this.renderCorrectionOptionsContent();
		return true;
	}


	private renderNonEmptyDestinationModal(): string {
		if (!this.states.organization.confirmNonEmptyOpen) {
			return "";
		}

		return `
		<div class="modal-backdrop">
			<section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="nonEmptyDestinationTitle">
				<header>
					<div>
						<h2 id="nonEmptyDestinationTitle">${this.context.text("organization.destinationNotEmptyTitle")}</h2>
						<p>${this.context.text("organization.destinationNotEmptyBody")}</p>
					</div>
					<button ${this.organizationDomAttributes(ORGANIZATION_DOM.entities.destinationConflict, ORGANIZATION_DOM.actions.close)} class="icon-button" type="button" aria-label="${this.context.text("common.cancel")}">${iconX()}</button>
				</header>
				<footer>
					<button ${this.organizationDomAttributes(ORGANIZATION_DOM.entities.destinationConflict, ORGANIZATION_DOM.actions.cancel)} class="secondary-action" type="button">${this.context.text("common.cancel")}</button>
					<button ${this.organizationDomAttributes(ORGANIZATION_DOM.entities.destinationConflict, ORGANIZATION_DOM.actions.confirm)} class="toolbar-button is-primary" type="button">${iconPlay()}<span>${this.context.text("organization.runAnyway")}</span></button>
				</footer>
			</section>
		</div>
	`;
	}


	private renderSettingsModal(): string {
		if (!this.states.settings.modalOpen) {
			return "";
		}

		const thresholdPercent = Math.round(this.states.settings.acceptedClassificationThreshold * 100);
		const cacheClearDisabled = this.cacheClearDisabled();
		return `
		<div class="modal-backdrop">
			<section class="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
				<header>
					<div>
						<h2 id="settingsTitle">${this.context.text("settings.title")}</h2>
						<p>${this.context.text("settings.cacheDescription")}</p>
					</div>
					<button id="closeSettings" class="icon-button" type="button" aria-label="${this.context.text("common.close")}">${iconX()}</button>
				</header>
				${this.renderRuntimeRow()}
				<div class="settings-row">
					<div>
						<strong>${iconGlobe()}<span>${this.context.text("settings.languageTitle")}</span></strong>
						<span>${this.context.text("settings.languageHelp")}</span>
					</div>
					<select id="appLanguagePreference" class="settings-select" aria-label="${this.context.text("settings.languageTitle")}">
						${this.renderAppLanguageOptions()}
					</select>
				</div>
				<div class="settings-row">
					<div>
						<strong>${this.context.text("settings.thresholdTitle")}</strong>
						<span>${this.context.text("settings.thresholdHelp")}</span>
					</div>
					<label class="threshold-control">
						<input id="acceptedClassificationThreshold" type="range" min="0" max="100" step="1" value="${thresholdPercent}" style="--threshold-percent: ${thresholdPercent}%;" aria-label="${this.context.text("settings.thresholdTitle")}" />
						<output id="acceptedClassificationThresholdValue" for="acceptedClassificationThreshold">${thresholdPercent}%</output>
					</label>
				</div>
				<div class="settings-row">
					<div>
						<strong>${this.context.text("settings.gpxToleranceTitle")}</strong>
						<span>${this.context.text("settings.gpxToleranceHelp")}</span>
					</div>
					<label class="settings-number-control">
						<input id="gpxMatchToleranceSeconds" class="settings-number" type="number" min="1" max="86400" step="1" value="${this.states.settings.gpxMatchToleranceSeconds}" aria-label="${this.context.text("settings.gpxToleranceTitle")}" />
						<span>${this.context.text("settings.gpxToleranceUnit")}</span>
					</label>
				</div>
				<div class="settings-row">
					<div>
						<strong>${this.context.text("settings.cacheTitle")}</strong>
						<span>${this.context.text("settings.cacheHelp")}</span>
					</div>
					<button id="clearPredictionCache" class="secondary-action" type="button" ${cacheClearDisabled ? "disabled" : ""}>${iconTrash()}<span>${this.states.settings.cacheBusy ? this.context.text("settings.clearingCache") : this.context.text("settings.clearCache")}</span></button>
				</div>
				<div class="settings-row">
					<div>
						<strong>${iconArchive()}<span>${this.context.text("settings.logsTitle")}</span></strong>
						<span>${this.context.text("settings.logsHelp")}</span>
					</div>
					<button id="exportLogs" class="secondary-action" type="button" ${this.states.settings.logsBusy ? "disabled" : ""}>${iconArchive()}<span>${this.states.settings.logsBusy ? this.context.text("settings.exportingLogs") : this.context.text("settings.exportLogs")}</span></button>
				</div>
				${this.states.settings.cacheMessage ? `<p class="settings-message">${escapeHtml(this.states.settings.cacheMessage)}</p>` : ""}
			</section>
		</div>
	`;
	}


	private renderLightroomUpgradeModal(): string {
		const plugin = this.states.lightroom.info?.plugin;
		if (!this.states.lightroom.upgradePromptOpen || !plugin) {
			return "";
		}

		const installedVersion = this.renderVersionLabel(plugin.installedVersion);
		const availableVersion = this.renderVersionLabel(plugin.availableVersion);
		const error = this.states.lightroom.upgradeError ? `<p class="modal-error">${escapeHtml(this.states.lightroom.upgradeError)}</p>` : "";
		return `
		<div class="modal-backdrop">
			<section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="lightroomUpgradeTitle">
				<header>
					<div>
						<h2 id="lightroomUpgradeTitle">${this.context.text("lightroom.upgradeTitle")}</h2>
						<p>${this.context.text("lightroom.upgradeBody", { installed: installedVersion, available: availableVersion })}</p>
					</div>
					<button id="closeLightroomUpgrade" class="icon-button" type="button" aria-label="${this.context.text("lightroom.upgradeDismiss")}" ${this.states.lightroom.busy ? "disabled" : ""}>${iconX()}</button>
				</header>
				${error}
				<footer>
					<button id="ignoreLightroomUpgrade" class="secondary-action" type="button" ${this.states.lightroom.busy ? "disabled" : ""}>${this.context.text("lightroom.upgradeDismiss")}</button>
					<button id="confirmLightroomUpgrade" class="toolbar-button is-primary" type="button" ${this.states.lightroom.busy ? "disabled" : ""}>${iconPlug()}<span>${this.context.text("lightroom.upgradeConfirm")}</span></button>
				</footer>
			</section>
		</div>
	`;
	}


	private renderUpdateModal(): string {
		const update = this.states.update.info;
		if (!this.states.update.promptOpen || !update?.availableVersion) {
			return "";
		}

		const error = this.states.update.message ? `<p class="modal-error">${escapeHtml(this.states.update.message)}</p>` : "";
		const cancelButton = this.states.update.busy ? `<button id="cancelUpdateInstall" class="secondary-action" type="button">${iconSquare()}<span>${this.context.text("common.stop")}</span></button>` : "";
		return `
		<div class="modal-backdrop">
			<section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="updatePromptTitle">
				<header>
					<div>
						<h2 id="updatePromptTitle">${this.context.text("update.title")}</h2>
						<p>${this.context.text("update.body", { current: this.renderVersionLabel(update.currentVersion), available: this.renderVersionLabel(update.availableVersion) })}</p>
					</div>
					<button id="closeUpdatePrompt" class="icon-button" type="button" aria-label="${this.context.text("common.close")}">${iconX()}</button>
				</header>
				${this.renderUpdateProgress()}
				${error}
				<footer>
					${cancelButton}
					<button id="installUpdate" class="toolbar-button is-primary" type="button" ${this.states.update.busy ? "disabled" : ""}>${iconDownload()}<span>${this.states.update.busy ? this.context.text("update.installing") : this.context.text("update.install")}</span></button>
				</footer>
			</section>
		</div>
	`;
	}


	private renderUpdateProgress(): string {
		const status = this.states.update.installStatus;
		if (!this.states.update.busy || !status) {
			return "";
		}

		const isDownloading = status.state === "downloading";
		const percent = isDownloading ? Math.max(1, status.progressPercent ?? 1) : status.progressPercent ?? 0;
		const label = status.progressPercent === null ? this.context.text("update.progressIndeterminate") : this.context.text("update.progressPercent", { percent });
		return `
		<div class="update-progress-block">
			<div class="progress-track update-progress" role="progressbar" aria-label="${this.context.text("update.progressLabel")}" aria-valuemin="0" aria-valuemax="100" ${status.progressPercent === null ? "" : `aria-valuenow="${percent}"`}>
				<span style="width: ${percent}%;"></span>
			</div>
			<p>${escapeHtml(this.updateStatusLabel(status.state))} ${escapeHtml(label)}</p>
			${this.renderUpdateDownloadDetails()}
		</div>
	`;
	}


	private renderUpdateDownloadDetails(): string {
		const status = this.states.update.installStatus;
		if (!status || status.state !== "downloading") {
			return "";
		}

		const completed = this.formatUpdateMegabytes(status.completedBytes);
		const speed = this.formatUpdateMegabytes(status.downloadSpeedBytesPerSecond ?? 0);
		const text = status.totalBytes === null
			? this.context.text("update.downloadDetailsUnknownTotal", { completed, speed })
			: this.context.text("update.downloadDetails", { completed, total: this.formatUpdateMegabytes(status.totalBytes), speed });
		return `<p>${escapeHtml(text)}</p>`;
	}


	private formatUpdateMegabytes(bytes: number): string {
		const megabytes = Math.max(0, bytes) / (1024 * 1024);
		return new Intl.NumberFormat(this.context.locale(), { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(megabytes);
	}


	private updateStatusLabel(state: string): string {
		if (state === "checking") {
			return this.context.text("update.status.checking");
		}

		if (state === "downloading") {
			return this.context.text("update.status.downloading");
		}

		if (state === "verifying") {
			return this.context.text("update.status.verifying");
		}

		if (state === "installing") {
			return this.context.text("update.status.installing");
		}

		return this.context.text("update.status.preparing");
	}


	private renderAppLanguageOptions(): string {
		const preference = this.states.settings.appLanguagePreference();
		const systemOption = `<option value="system" ${preference === "system" ? "selected" : ""}>${this.context.text("settings.languageSystem")}</option>`;
		const languageOptions = this.states.settings.availableAppLanguages.map(language => {
			const label = this.context.languageName(language);
			return `<option value="${escapeHtml(language)}" ${preference === language ? "selected" : ""}>${escapeHtml(label)}</option>`;
		}).join("");
		return `${systemOption}${languageOptions}`;
	}


	private renderCorrectionModal(): string {
		const birdIndex = this.states.speciesCorrection.editingBirdIndex;
		if (birdIndex === null) {
			return "";
		}

		const bird = this.states.detection.result?.birds[birdIndex] ?? null;
		const title = this.context.text("correction.edit");
		return `
		<div class="modal-backdrop">
			<section class="correction-modal" role="dialog" aria-modal="true" aria-labelledby="correctionTitle">
				<header>
					<div>
						<h2 id="correctionTitle">${title}</h2>
						${this.renderCorrectionCurrentSpecies(bird)}
					</div>
					<button class="icon-button" data-action="cancel-correction" type="button" aria-label="${this.context.text("common.close")}">${iconX()}</button>
				</header>
				${this.renderCorrectionEditor(bird)}
			</section>
		</div>
	`;
	}


	private renderCorrectionCurrentSpecies(bird: BirdResult | null): string {
		const best = bird?.classification[0];
		if (!best) {
			return "";
		}

		return `<p>${escapeHtml(this.classificationDisplayName(best))}${best.name_lat ? ` - ${escapeHtml(best.name_lat)}` : ""}</p>`;
	}


	private renderCorrectionEditor(bird: BirdResult | null): string {
		const clear = bird?.manualCorrection ? `<button class="secondary-action" data-action="clear-correction" type="button" ${this.states.speciesCorrection.busy ? "disabled" : ""}>${this.context.text("correction.clear")}</button>` : "";
		const error = this.states.speciesCorrection.error ? `<p class="correction-error">${escapeHtml(this.states.speciesCorrection.error)}</p>` : "";
		return `
		<section class="correction-editor">
			<input class="correction-search-input" type="search" value="${escapeHtml(this.states.speciesCorrection.speciesSearchQuery)}" placeholder="${escapeHtml(this.context.text("correction.searchPlaceholder"))}" ${this.states.speciesCorrection.busy ? "disabled" : ""} />
			<div class="correction-options">${this.renderCorrectionOptionsContent()}</div>
			<div class="correction-actions">
				${clear}
				<button class="secondary-action" data-action="cancel-correction" type="button" ${this.states.speciesCorrection.busy ? "disabled" : ""}>${this.context.text("common.cancel")}</button>
			</div>
			${error}
		</section>
	`;
	}


	private cacheClearDisabled(): boolean {
		return this.states.settings.cacheBusy || this.states.detection.loading || Boolean(this.states.detection.activeJobId || this.states.organization.activeJobId || this.states.collection.activeJobId);
	}


	private renderCorrectionOptionsContent(): string {
		const query = this.normalizedSearchText(this.states.speciesCorrection.speciesSearchQuery.trim());
		const suggestions = query ? this.sortedBirdNames(this.filteredBirdNames(query)).slice(0, ModalRenderer.CORRECTION_SUGGESTION_LIMIT) : [];
		const suggestionRows = suggestions.map(item => this.renderCorrectionBirdName(item)).join("");
		const empty = this.renderCorrectionEmptyMessage(suggestions.length, query);
		return `${suggestionRows}${empty}`;
	}


	private renderCorrectionBirdName(item: BirdName): string {
		const latinName = item.name_lat ? `<span>${escapeHtml(item.name_lat)}</span>` : "";
		return `
		<button class="correction-option" data-action="select-correction-species" data-species-id="${escapeHtml(item.species_id)}" type="button" ${this.states.speciesCorrection.busy ? "disabled" : ""}>
			<strong>${escapeHtml(this.birdNamePrimaryName(item))}</strong>
			${latinName}
		</button>
	`;
	}


	private renderCorrectionEmptyMessage(suggestionCount: number, query: string): string {
		if (suggestionCount > 0) {
			return "";
		}

		if (this.states.speciesCorrection.busy) {
			return `<p class="correction-empty">${this.context.text("correction.loading")}</p>`;
		}

		if (!query) {
			return `<p class="correction-empty">${this.context.text("correction.startTyping")}</p>`;
		}

		return `<p class="correction-empty">${this.context.text("correction.noMatch")}</p>`;
	}


	private filteredBirdNames(query: string): BirdName[] {
		return this.states.speciesCorrection.birdNames.filter(item => this.normalizedSearchText([item.name, item.name_lat, item.species_id].join(" ")).includes(query));
	}


	private birdNamePrimaryName(item: BirdName): string {
		return item.name || item.species_id;
	}


	private sortedBirdNames(items: BirdName[]): BirdName[] {
		const locale = this.states.settings.appLanguage;
		return [...items].sort((firstItem, secondItem) => this.birdNameSortName(firstItem).localeCompare(this.birdNameSortName(secondItem), locale, { sensitivity: "base" }) || (firstItem.name_lat || firstItem.species_id).localeCompare(secondItem.name_lat || secondItem.species_id, locale, { sensitivity: "base" }));
	}


	private birdNameSortName(item: BirdName): string {
		return item.name || item.name_lat || item.species_id;
	}


	private classificationDisplayName(classification: Classification): string {
		return classification.name || classification.species_id;
	}


	private normalizedSearchText(value: string): string {
		return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
	}


	private renderRuntimeRow(): string {
		const refreshButtonClass = `icon-button runtime-refresh-button${this.isRuntimeDetecting() ? " is-spinning" : ""}`;
		const refreshRuntime = this.context.text("settings.refreshRuntime");
		return `
				<div class="settings-row settings-runtime-row">
					<div>
						<strong>${this.context.text("settings.runtime")}</strong>
						<span>${this.context.text("settings.runtimeHelp")}</span>
					</div>
					<div class="runtime-value">
						<strong>${escapeHtml(this.runtimeDeviceLabel())}</strong>
						<button id="refreshRuntime" class="${refreshButtonClass}" type="button" title="${refreshRuntime}" aria-label="${refreshRuntime}">${iconRefresh()}</button>
					</div>
				</div>
	`;
	}


	private runtimeDeviceLabel(): string {
		if (this.isRuntimeDetecting()) {
			return this.context.text("settings.runtimeDetecting");
		}

		return this.states.runtime.device;
	}


	private isRuntimeDetecting(): boolean {
		return this.states.runtime.isDetecting();
	}


	private renderOrganizationProgressModal(): string {
		if (!this.states.organization.modalOpen || !this.states.organization.status) {
			return "";
		}

		const status = this.states.organization.status;
		const percent = status.total === 0 ? 0 : Math.round((status.completed / status.total) * 100);
		return `
		<div class="modal-backdrop">
			<section class="progress-modal" role="dialog" aria-modal="true" aria-labelledby="organizationProgressTitle">
				<header>
					<div>
						<h2 id="organizationProgressTitle">${this.context.text("organization.progressTitle")}</h2>
						${this.renderOrganizationModalMessage()}
					</div>
				</header>
				<div class="progress-track"><span style="width: ${percent}%;"></span></div>
				<div class="progress-summary">
					<div class="progress-count"><strong>${status.completed}/${status.total}</strong> ${this.context.text("organization.progressCompleted")}</div>
					${this.renderOrganizationEstimatedFinish()}
				</div>
				<footer>
					${this.renderOrganizationProgressActions()}
				</footer>
			</section>
		</div>
	`;
	}


	private renderOrganizationProgressActions(): string {
		if (this.states.organization.status?.state === "done") {
			return `<button ${this.organizationDomAttributes(ORGANIZATION_DOM.entities.progress, ORGANIZATION_DOM.actions.close)} class="toolbar-button is-primary" type="button">${this.context.text("common.done")}</button>`;
		}

		const canStop = this.states.organization.status?.state === "running";
		return `<button ${this.organizationDomAttributes(ORGANIZATION_DOM.entities.progress, ORGANIZATION_DOM.actions.stop)} class="secondary-action" type="button" ${canStop ? "" : "disabled"}>${iconSquare()}<span>${this.context.text("common.stop")}</span></button>`;
	}


	private renderOrganizationModalMessage(): string {
		const status = this.states.organization.status;
		if (!status || status.state === "running" || status.state === "done") {
			return "";
		}

		return `<p>${escapeHtml(status.error || status.message)}</p>`;
	}


	private renderOrganizationEstimatedFinish(): string {
		const finishMs = this.states.organization.estimatedFinishMs();
		if (finishMs === null) {
			return "";
		}

		return `<div class="progress-eta">${this.context.text("common.eta")} <strong>${formatTimeOfDay(new Date(finishMs))}</strong></div>`;
	}


	private renderVersionLabel(version: string | null | undefined): string {
		return version ? `v${escapeHtml(version)}` : this.context.text("common.unknown");
	}


	private organizationDomAttributes(entity: string, action: string): string {
		return `data-vertical="${ORGANIZATION_DOM.vertical}" data-entity="${entity}" data-action="${action}"`;
	}
}

type ModalRendererStates = {
	organization: OrganizationState;
	collection: CollectionState;
	speciesCorrection: SpeciesCorrectionState;
	detection: DetectionState;
	lightroom: LightroomState;
	runtime: RuntimeState;
	settings: SettingsState;
	update: UpdateState;
};
