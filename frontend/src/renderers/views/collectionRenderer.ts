import { iconChevronLeft, iconChevronRight, iconFolder, iconGallery, iconPencil, iconPlay, iconSearch, iconSquare, iconTrash } from "../../icons";
import type { CollectionState } from "../../state/collectionState";
import type { DetectionState } from "../../state/detectionState";
import type { ImageViewportState } from "../../state/imageViewportState";
import type { SettingsState } from "../../state/settingsState";
import type { CollectionOccurrence, CollectionSpecies } from "../../types";
import { escapeHtml, fileName, formatPercentWhole, formatRemainingDuration } from "../../utils";
import type { RendererContext } from "../rendererContext";
import { DetectionRenderer } from "./detectionRenderer";

export class CollectionRenderer {
	private readonly detectionRenderer: DetectionRenderer;


	public constructor(private readonly context: RendererContext, private readonly collection: CollectionState, private readonly detection: DetectionState, private readonly imageViewport: ImageViewportState, private readonly settings: SettingsState) {
		this.detectionRenderer = new DetectionRenderer(context, detection, imageViewport, settings);
	}


	public render(): string {
		const className = this.collection.occurrenceOpen ? "collection-view is-image-open" : "collection-view";
		return `
		<section class="${className}">
			<div class="collection-top-bar">
				<div class="section-heading">
					<div class="section-title">
						<h2>${this.context.text("collection.title")}</h2>
					</div>
					<div class="analysis-actions" data-collection-stats>
						${this.renderCollectionStats()}
					</div>
				</div>
				${this.renderToolbar()}
			</div>
			<section class="collection-results" data-collection-results>
				${this.renderCollectionContent()}
			</section>
		</section>
	`;
	}


	public updateExistingView(): boolean {
		const collectionView = document.querySelector<HTMLElement>(".collection-view");
		if (!collectionView) {
			return false;
		}

		if (collectionView.classList.contains("is-image-open") !== this.collection.occurrenceOpen) {
			return false;
		}

		return this.updateCollectionStats() && this.updateToolbar() && this.updateCollectionContent();
	}


	private renderCollectionStats(): string {
		const speciesCount = this.collection.visibleSpecies().length;
		if (speciesCount === 0) {
			return "";
		}

		return `<span>${this.context.text("collection.speciesCount", { count: speciesCount })}</span>`;
	}


	private renderToolbar(): string {
		return `
		<section class="collection-toolbar">
			<div class="collection-picker-row">
				<div class="path-picker">
					<input data-collection-directory readonly value="${escapeHtml(this.collection.directory)}" placeholder="${this.context.text("collection.selectFolderPlaceholder")}" />
					<button id="chooseCollectionDirectory" class="toolbar-button is-primary" type="button">${iconFolder()}<span>${this.context.text("common.browse")}</span></button>
				</div>
				<div class="collection-toolbar__actions" data-collection-toolbar-actions>
					${this.renderToolbarActions()}
				</div>
			</div>
			${this.renderScanOptions()}
			<div data-collection-progress>${this.renderProgress()}</div>
		</section>
	`;
	}


	private renderToolbarActions(): string {
		if (this.collection.activeJobId || this.collection.stopping) {
			return `<button id="stopCollectionScan" class="secondary-action" type="button" ${this.collection.stopping ? "disabled" : ""}>${iconSquare()}<span>${this.context.text(this.collection.stopping ? "collection.stopping" : "common.stop")}</span></button>`;
		}

		return `
		<button id="scanCollection" class="toolbar-button is-primary" type="button" ${this.collection.canScan() ? "" : "disabled"}>${iconPlay()}<span>${this.context.text("collection.scan")}</span></button>
	`;
	}


	private renderScanOptions(): string {
		return `
		<label class="collection-scan-mode">
			<span>${this.context.text("collection.scanMode")}</span>
			<select id="collectionScanMode" ${this.collection.activeJobId ? "disabled" : ""}>
				<option value="raw_jpeg" ${this.collection.scanMode === "raw_jpeg" ? "selected" : ""}>${this.context.text("collection.scanModeRawJpeg")}</option>
				<option value="raw" ${this.collection.scanMode === "raw" ? "selected" : ""}>${this.context.text("collection.scanModeRaw")}</option>
				<option value="jpeg" ${this.collection.scanMode === "jpeg" ? "selected" : ""}>${this.context.text("collection.scanModeJpeg")}</option>
			</select>
		</label>
	`;
	}


	private renderProgress(): string {
		const status = this.collection.status;
		if (!status || status.state !== "running") {
			return this.collection.error ? `<p class="collection-error">${escapeHtml(this.collection.error)}</p>` : "";
		}

		const progress = status.total > 0 ? Math.round((status.completed / status.total) * 100) : 0;
		const nowMs = Date.now();
		const finish = this.collection.estimatedFinishMs(nowMs);
		const remaining = finish === null ? "" : `<span>${this.context.text("collection.remainingTime")} ${formatRemainingDuration(finish - nowMs)}</span>`;
		return `
		<section class="collection-progress">
			<div class="progress-track"><span style="width: ${progress}%;"></span></div>
			<div class="progress-summary">
				<span><strong>${status.completed}</strong> / ${status.total} ${this.context.text("organization.progressCompleted")}</span>
				${remaining}
			</div>
			<p>${escapeHtml(status.currentFile || status.message)}</p>
		</section>
	`;
	}


	private renderCollectionContent(): string {
		const selectedSpecies = this.collection.selectedSpecies();
		if (selectedSpecies) {
			return this.renderSelectedSpecies(selectedSpecies);
		}

		const species = this.collection.species();
		if (species.length > 0) {
			return this.renderSpeciesGrid(species);
		}

		return `
		<section class="collection-empty">
			<div class="empty-upload__icon">${iconGallery()}</div>
			<h3>${this.context.text("collection.emptyTitle")}</h3>
			<p>${this.context.text("collection.emptyBody")}</p>
		</section>
	`;
	}


	private renderSpeciesGrid(species: CollectionSpecies[]): string {
		const filteredSpecies = this.filteredSpecies(this.collection.visibleSpecies());
		const cards = this.sortedSpecies(filteredSpecies).map(item => this.renderSpeciesCard(item)).join("");
		const emptyMessage = filteredSpecies.length === 0 ? `<p class="collection-no-species-match" data-collection-no-species-match>${escapeHtml(this.context.text("collection.noSpeciesMatch"))}</p>` : "";
		return `
		<section class="collection-species-list">
			${this.renderSpeciesFilters(species)}
			${emptyMessage}
			<section class="collection-grid">${cards}</section>
		</section>
	`;
	}


	private renderSpeciesFilters(species: CollectionSpecies[]): string {
		const families = [...new Set(species.map(item => item.family_name?.trim()).filter((family): family is string => Boolean(family)))].sort((left, right) => left.localeCompare(right, this.settings.appLanguage, { sensitivity: "base" }));
		const familyOptions = families.map(family => `<option value="${escapeHtml(family)}" ${this.collection.familyFilter === family ? "selected" : ""}>${escapeHtml(family)}</option>`).join("");
		return `
			<div class="collection-species-filters">
				<label class="collection-list-control collection-species-search" for="collectionSpeciesSearch">
					${iconSearch()}
					<input id="collectionSpeciesSearch" type="search" value="${escapeHtml(this.collection.speciesSearchQuery)}" placeholder="${escapeHtml(this.context.text("collection.speciesSearchPlaceholder"))}" />
				</label>
				<label class="collection-filter-control" for="collectionFamilyFilter">
					<span>${this.context.text("collection.familyFilter")}</span>
					<select id="collectionFamilyFilter">
						<option value="">${this.context.text("collection.allFamilies")}</option>
						${familyOptions}
					</select>
				</label>
				<label class="collection-filter-control" for="collectionDateFrom">
					<span>${this.context.text("collection.dateFrom")}</span>
					<input id="collectionDateFrom" type="date" value="${escapeHtml(this.collection.dateFrom)}" />
				</label>
				<label class="collection-filter-control" for="collectionDateTo">
					<span>${this.context.text("collection.dateTo")}</span>
					<input id="collectionDateTo" type="date" value="${escapeHtml(this.collection.dateTo)}" />
				</label>
				<label class="collection-filter-control" for="collectionGpsFilter">
					<span>${this.context.text("collection.locationFilter")}</span>
					<select id="collectionGpsFilter">
						<option value="all">${this.context.text("collection.allLocations")}</option>
						<option value="withGps" ${this.collection.gpsFilter === "withGps" ? "selected" : ""}>${this.context.text("collection.withGps")}</option>
						<option value="withoutGps" ${this.collection.gpsFilter === "withoutGps" ? "selected" : ""}>${this.context.text("collection.withoutGps")}</option>
					</select>
				</label>
				<label class="collection-filter-control" for="collectionConfidenceFilter">
					<span>${this.context.text("collection.confidenceFilter")}</span>
					<select id="collectionConfidenceFilter">
						<option value="all">${this.context.text("collection.anyConfidence")}</option>
						<option value="manual" ${this.collection.confidenceFilter === "manual" ? "selected" : ""}>${this.context.text("collection.manualOnly")}</option>
						<option value="low" ${this.collection.confidenceFilter === "low" ? "selected" : ""}>${this.context.text("collection.lowConfidence")}</option>
						<option value="medium" ${this.collection.confidenceFilter === "medium" ? "selected" : ""}>${this.context.text("collection.mediumConfidence")}</option>
						<option value="high" ${this.collection.confidenceFilter === "high" ? "selected" : ""}>${this.context.text("collection.highConfidence")}</option>
					</select>
				</label>
				<label class="collection-filter-control" for="collectionSpeciesSort">
					<span>${this.context.text("collection.sortBy")}</span>
					<select id="collectionSpeciesSort">
						<option value="name" ${this.collection.speciesSortOrder === "name" ? "selected" : ""}>${this.context.text("collection.sortBySpecies")}</option>
						<option value="family" ${this.collection.speciesSortOrder === "family" ? "selected" : ""}>${this.context.text("collection.sortByFamily")}</option>
						<option value="date" ${this.collection.speciesSortOrder === "date" ? "selected" : ""}>${this.context.text("collection.sortByDate")}</option>
						<option value="location" ${this.collection.speciesSortOrder === "location" ? "selected" : ""}>${this.context.text("collection.sortByLocation")}</option>
						<option value="imageCount" ${this.collection.speciesSortOrder === "imageCount" ? "selected" : ""}>${this.context.text("collection.sortByImageCount")}</option>
						<option value="confidence" ${this.collection.speciesSortOrder === "confidence" ? "selected" : ""}>${this.context.text("collection.sortByConfidence")}</option>
					</select>
				</label>
				<div class="collection-filter-actions">${this.renderCollectionFilterActions()}</div>
			</div>
		`;
	}


	private renderCollectionFilterActions(): string {
		return `${this.collection.selectedSpeciesIds.size > 0 ? `<button id="removeSelectedSpecies" class="secondary-action" type="button">${iconTrash()}<span>${this.context.text("collection.removeSelected", { count: this.collection.selectedSpeciesIds.size })}</span></button><button id="exportEbirdRecords" class="toolbar-button is-primary" type="button">${this.context.text("collection.exportSelected", { count: this.collection.selectedSpeciesIds.size })}</button>` : ""}${this.collection.hasRemovedItems() ? `<button class="secondary-action collection-restore-button" data-action="restore-collection-items" type="button">${this.context.text("collection.restoreRemoved")}</button>` : ""}`;
	}


	private renderSpeciesCard(species: CollectionSpecies): string {
		const thumbnail = species.thumbnailDataUrl ? `<img src="${species.thumbnailDataUrl}" alt="" draggable="false" />` : iconGallery();
		return `
		<article class="collection-card collection-species-card" data-species-id="${escapeHtml(species.speciesId)}">
			<button class="collection-card-open" data-action="select-collection-species" data-species-id="${escapeHtml(species.speciesId)}" type="button">
				<div class="collection-card-thumbnail">${thumbnail}</div>
				<strong>${escapeHtml(this.speciesName(species))}</strong>
				${this.renderSpeciesLatinName(species)}
			${species.family_name ? `<span class="collection-species-family">${escapeHtml(species.family_name)}</span>` : ""}
				<span data-collection-species-count>${this.context.text("collection.imageCount", { count: species.imageCount })}</span>
			</button>
			<div class="collection-card__actions">
				<label class="collection-export-select"><input data-action="toggle-ebird-species" data-species-id="${escapeHtml(species.speciesId)}" type="checkbox" title="${escapeHtml(this.context.text("collection.selectForEbird"))}" aria-label="${escapeHtml(this.context.text("collection.selectForEbird"))}" ${this.collection.selectedSpeciesIds.has(species.speciesId) ? "checked" : ""} /></label>
				<button class="collection-remove-button" data-action="remove-collection-species" data-species-id="${escapeHtml(species.speciesId)}" type="button" title="${escapeHtml(this.context.text("collection.removeSpecies"))}" aria-label="${escapeHtml(this.context.text("collection.removeSpecies"))}">${iconTrash()}<span>${this.context.text("collection.remove")}</span></button>
			</div>
		</article>
	`;
	}


	private renderSelectedSpecies(species: CollectionSpecies): string {
		if (this.collection.occurrenceOpen) {
			return this.renderSelectedOccurrence(species);
		}

		return `
		<section class="collection-detail">
			${this.renderSpeciesHeader("backToCollectionSpecies", this.speciesName(species), this.context.text("collection.occurrenceCount", { count: species.occurrenceCount }), species.speciesId)}
			${this.renderOccurrenceGrid(species.speciesId, species.occurrences)}
		</section>
	`;
	}


	private renderSpeciesHeader(buttonId: string, title: string, meta: string, speciesId?: string): string {
		return `
		<header class="collection-list-control collection-detail__header">
			<button id="${buttonId}" class="collection-back-button" type="button" title="${this.context.text("collection.back")}">${iconChevronLeft()}</button>
			<div>
				<h3>${escapeHtml(title)}</h3>
				<div class="collection-detail__meta">${meta}</div>
			</div>
			${speciesId ? `<button class="collection-remove-button" data-action="remove-collection-species" data-species-id="${escapeHtml(speciesId)}" type="button" title="${escapeHtml(this.context.text("collection.removeSpecies"))}" aria-label="${escapeHtml(this.context.text("collection.removeSpecies"))}">${iconTrash()}<span>${this.context.text("collection.remove")}</span></button>` : ""}
		</header>
	`;
	}


	private renderOccurrenceGrid(speciesId: string, occurrences: CollectionOccurrence[]): string {
		const items = occurrences.map((occurrence, index) => this.renderOccurrenceButton(speciesId, occurrence, index)).join("");
		return `<section class="collection-grid collection-occurrence-grid">${items}</section>`;
	}


	private renderOccurrenceButton(speciesId: string, occurrence: CollectionOccurrence, index: number): string {
		const thumbnail = occurrence.thumbnailDataUrl ? `<img src="${occurrence.thumbnailDataUrl}" alt="" />` : iconGallery();
		const isKeyPhoto = this.collection.isKeyPhoto(speciesId, occurrence);
		return `
		<article class="collection-card collection-occurrence-item" data-occurrence-key="${escapeHtml(this.occurrenceKey(occurrence))}">
			<button class="collection-card-open collection-occurrence" data-action="select-collection-occurrence" data-occurrence-index="${index}" data-occurrence-key="${escapeHtml(this.occurrenceKey(occurrence))}" type="button">
				<div class="collection-card-thumbnail">${thumbnail}</div>
				<span>${escapeHtml(fileName(occurrence.imagePath))}</span>
				${this.renderOccurrenceConfidence(occurrence)}
			</button>
			<div class="collection-card__actions">
				<button class="secondary-action collection-key-photo-button" data-action="set-collection-key-photo" data-species-id="${escapeHtml(speciesId)}" data-image-path="${escapeHtml(occurrence.imagePath)}" data-bird-index="${occurrence.birdIndex}" type="button" title="${escapeHtml(this.context.text(isKeyPhoto ? "collection.keyPhoto" : "collection.makeKeyPhoto"))}" aria-label="${escapeHtml(this.context.text(isKeyPhoto ? "collection.keyPhoto" : "collection.makeKeyPhoto"))}" aria-pressed="${isKeyPhoto}" ${isKeyPhoto ? "disabled" : ""}>${isKeyPhoto ? "★" : "☆"}</button>
				<button class="collection-remove-button" data-action="remove-collection-image" data-image-path="${escapeHtml(occurrence.imagePath)}" type="button" title="${escapeHtml(this.context.text("collection.removeImage"))}" aria-label="${escapeHtml(this.context.text("collection.removeImage"))}">${iconTrash()}<span>${this.context.text("collection.remove")}</span></button>
			</div>
		</article>
	`;
	}


	private renderOccurrenceConfidence(occurrence: CollectionOccurrence): string {
		if (occurrence.classification.manual) {
			return `<strong class="collection-occurrence-manual" title="${escapeHtml(this.context.text("correction.manualBadge"))}" aria-label="${escapeHtml(this.context.text("correction.manualBadge"))}">${iconPencil()}</strong>`;
		}

		return `<strong>${formatPercentWhole(occurrence.confidence)}</strong>`;
	}


	private renderSelectedOccurrence(species: CollectionSpecies): string {
		const occurrence = this.collection.selectedOccurrence();
		const label = occurrence ? this.renderOccurrenceTitleMeta(occurrence) : "";
		const occurrenceKey = occurrence ? this.occurrenceKey(occurrence) : "";
		return `
		<section class="collection-detail" data-selected-occurrence-key="${escapeHtml(occurrenceKey)}">
			${this.renderSpeciesHeader("backToCollectionOccurrences", this.speciesName(species), label)}
			${this.renderSelectedOccurrenceAnalysis()}
		</section>
	`;
	}


	private renderOccurrenceTitleMeta(occurrence: CollectionOccurrence): string {
		return `
		<span class="collection-image-title-meta">
			<span class="collection-image-title-path" title="${escapeHtml(occurrence.imagePath)}">${escapeHtml(occurrence.imagePath)}</span>
			<button id="revealCollectionOccurrence" class="collection-reveal-button" type="button" title="${this.context.text("collection.revealImage")}" aria-label="${this.context.text("collection.revealImage")}">${iconFolder()}</button>
			<button class="collection-remove-button" data-action="remove-collection-image" data-image-path="${escapeHtml(occurrence.imagePath)}" type="button" title="${escapeHtml(this.context.text("collection.removeImage"))}" aria-label="${escapeHtml(this.context.text("collection.removeImage"))}">${iconTrash()}</button>
		</span>
	`;
	}


	private renderSelectedOccurrenceAnalysis(): string {
		if (this.detection.loading) {
			return `<div class="collection-analysis-placeholder">${this.context.text("collection.loadingCachedPrediction")}</div>`;
		}

		if (!this.detection.result) {
			return `<div class="collection-analysis-placeholder">${this.context.text("collection.selectOccurrence")}</div>`;
		}

		return `
		<section class="collection-image-view">
			<div class="collection-image-analysis">
				${this.detectionRenderer.renderAnalysisContent()}
				${this.renderPreviousButton()}
				${this.renderNextButton()}
			</div>
		</section>
	`;
	}


	private renderPreviousButton(): string {
		if (!this.collection.hasPreviousOccurrence()) {
			return "";
		}

		return `<button id="previousCollectionOccurrence" class="collection-image-nav is-previous" type="button" title="${this.context.text("collection.previousImage")}">${iconChevronLeft()}</button>`;
	}


	private renderNextButton(): string {
		if (!this.collection.hasNextOccurrence()) {
			return "";
		}

		return `<button id="nextCollectionOccurrence" class="collection-image-nav is-next" type="button" title="${this.context.text("collection.nextImage")}">${iconChevronRight()}</button>`;
	}


	private updateCollectionStats(): boolean {
		const stats = document.querySelector<HTMLElement>("[data-collection-stats]");
		if (!stats) {
			return false;
		}

		stats.innerHTML = this.renderCollectionStats();
		return true;
	}


	private updateToolbar(): boolean {
		const directoryInput = document.querySelector<HTMLInputElement>("[data-collection-directory]");
		const toolbarActions = document.querySelector<HTMLElement>("[data-collection-toolbar-actions]");
		const progress = document.querySelector<HTMLElement>("[data-collection-progress]");
		const scanMode = document.querySelector<HTMLSelectElement>("#collectionScanMode");
		if (!directoryInput || !toolbarActions || !progress || !scanMode) {
			return false;
		}

		directoryInput.value = this.collection.directory;
		toolbarActions.innerHTML = this.renderToolbarActions();
		progress.innerHTML = this.renderProgress();
		scanMode.value = this.collection.scanMode;
		scanMode.disabled = Boolean(this.collection.activeJobId);
		return true;
	}


	private updateCollectionContent(): boolean {
		const selectedSpecies = this.collection.selectedSpecies();
		if (selectedSpecies) {
			return this.updateSelectedSpecies(selectedSpecies);
		}

		const species = this.collection.species();
		if (species.length > 0) {
			return this.updateSpeciesGrid(species);
		}

		return this.replaceCollectionResults(this.renderCollectionContent());
	}


	private updateSpeciesGrid(species: CollectionSpecies[]): boolean {
		const results = document.querySelector<HTMLElement>("[data-collection-results]");
		if (!results) {
			return false;
		}

		const list = results.querySelector<HTMLElement>(".collection-species-list");
		if (!list) {
			results.innerHTML = this.renderSpeciesGrid(species);
			return true;
		}

		const grid = list.querySelector<HTMLElement>(".collection-grid");
		if (!grid) {
			return false;
		}

		this.updateSpeciesFilters(list, species);
		const visibleSpecies = this.sortedSpecies(this.filteredSpecies(this.collection.visibleSpecies()));
		this.updateNoSpeciesMatch(list, grid, visibleSpecies.length === 0);
		this.updateSpeciesCards(grid, visibleSpecies);
		return true;
	}


	private updateNoSpeciesMatch(list: HTMLElement, grid: HTMLElement, shouldShow: boolean): void {
		const message = list.querySelector<HTMLElement>("[data-collection-no-species-match]");
		if (shouldShow && !message) {
			grid.before(this.createElement(`<p class="collection-no-species-match" data-collection-no-species-match>${escapeHtml(this.context.text("collection.noSpeciesMatch"))}</p>`));
			return;
		}

		if (!shouldShow && message) {
			message.remove();
		}
	}


	private updateSelectedSpecies(species: CollectionSpecies): boolean {
		if (this.collection.occurrenceOpen) {
			return this.updateSelectedOccurrence(species);
		}

		const results = document.querySelector<HTMLElement>("[data-collection-results]");
		if (!results) {
			return false;
		}

		const detail = results.querySelector<HTMLElement>(".collection-detail");
		if (!detail) {
			results.innerHTML = this.renderSelectedSpecies(species);
			return true;
		}

		const title = detail.querySelector<HTMLElement>(".collection-detail__header h3");
		const meta = detail.querySelector<HTMLElement>(".collection-detail__meta");
		const grid = detail.querySelector<HTMLElement>(".collection-occurrence-grid");
		if (!title || !meta || !grid) {
			return false;
		}

		title.textContent = this.speciesName(species);
		meta.textContent = this.context.text("collection.occurrenceCount", { count: species.occurrenceCount });
		this.reconcileElements(grid, species.occurrences, ".collection-occurrence-item[data-occurrence-key]", item => this.occurrenceKey(item), element => element.dataset.occurrenceKey || "", (item, index) => this.renderOccurrenceButton(species.speciesId, item, index));
		return true;
	}


	private updateSelectedOccurrence(species: CollectionSpecies): boolean {
		const occurrence = this.collection.selectedOccurrence();
		const currentKey = occurrence ? this.occurrenceKey(occurrence) : "";
		const detail = document.querySelector<HTMLElement>(".collection-detail[data-selected-occurrence-key]");
		const analysis = detail?.querySelector<HTMLElement>(".collection-image-analysis") ?? null;
		if (!detail || detail.dataset.selectedOccurrenceKey !== currentKey || !analysis || this.detection.loading || !this.detection.result) {
			return this.replaceCollectionResults(this.renderSelectedSpecies(species));
		}

		const title = detail.querySelector<HTMLElement>(".collection-detail__header h3");
		const meta = detail.querySelector<HTMLElement>(".collection-detail__meta");
		if (!title || !meta) {
			return false;
		}

		title.textContent = this.speciesName(species);
		meta.innerHTML = occurrence ? this.renderOccurrenceTitleMeta(occurrence) : "";
		this.updateOccurrenceNavigation();
		return true;
	}


	private updateOccurrenceNavigation(): void {
		const analysis = document.querySelector<HTMLElement>(".collection-image-analysis");
		if (!analysis) {
			return;
		}

		analysis.querySelector<HTMLElement>("#previousCollectionOccurrence")?.remove();
		analysis.querySelector<HTMLElement>("#nextCollectionOccurrence")?.remove();
		analysis.insertAdjacentHTML("beforeend", `${this.renderPreviousButton()}${this.renderNextButton()}`);
	}


	private updateSpeciesCards(grid: HTMLElement, species: CollectionSpecies[]): void {
		this.reconcileElements(grid, species, ".collection-species-card[data-species-id]", item => item.speciesId, element => element.dataset.speciesId || "", item => this.renderSpeciesCard(item));
	}


	private updateSpeciesFilters(list: HTMLElement, species: CollectionSpecies[]): void {
		const familySelect = list.querySelector<HTMLSelectElement>("#collectionFamilyFilter");
		const sortSelect = list.querySelector<HTMLSelectElement>("#collectionSpeciesSort");
		const gpsSelect = list.querySelector<HTMLSelectElement>("#collectionGpsFilter");
		const confidenceSelect = list.querySelector<HTMLSelectElement>("#collectionConfidenceFilter");
		const actions = list.querySelector<HTMLElement>(".collection-filter-actions");
		if (!familySelect || !sortSelect || !gpsSelect || !confidenceSelect || !actions) {
			return;
		}

		const families = [...new Set(species.map(item => item.family_name?.trim()).filter((family): family is string => Boolean(family)))].sort((left, right) => left.localeCompare(right, this.settings.appLanguage, { sensitivity: "base" }));
		const familyOptions = families.map(family => `<option value="${escapeHtml(family)}">${escapeHtml(family)}</option>`).join("");
		familySelect.innerHTML = `<option value="">${this.context.text("collection.allFamilies")}</option>${familyOptions}`;
		familySelect.value = families.includes(this.collection.familyFilter) ? this.collection.familyFilter : "";
		sortSelect.value = this.collection.speciesSortOrder;
		gpsSelect.value = this.collection.gpsFilter;
		confidenceSelect.value = this.collection.confidenceFilter;
		actions.innerHTML = this.renderCollectionFilterActions();
	}


	private replaceCollectionResults(html: string): boolean {
		const results = document.querySelector<HTMLElement>("[data-collection-results]");
		if (!results) {
			return false;
		}

		results.innerHTML = html;
		return true;
	}


	private reconcileElements<T>(container: HTMLElement, items: T[], selector: string, itemKey: (item: T, index: number) => string, elementKey: (element: HTMLElement) => string, renderItem: (item: T, index: number) => string): void {
		const existingElements = new Map<string, HTMLElement>();
		container.querySelectorAll<HTMLElement>(selector).forEach(element => existingElements.set(elementKey(element), element));
		const nextKeys = new Set<string>();

		items.forEach((item, index) => {
			const key = itemKey(item, index);
			const currentElement = existingElements.get(key);
			const renderedElement = this.createElement(renderItem(item, index));
			nextKeys.add(key);

			if (currentElement && currentElement.isEqualNode(renderedElement)) {
				container.appendChild(currentElement);
				return;
			}

			if (currentElement) {
				currentElement.replaceWith(renderedElement);
			}

			container.appendChild(renderedElement);
		});

		existingElements.forEach((element, key) => {
			if (!nextKeys.has(key)) {
				element.remove();
			}
		});
	}


	private createElement(html: string): HTMLElement {
		const template = document.createElement("template");
		template.innerHTML = html.trim();
		return template.content.firstElementChild as HTMLElement;
	}


	private occurrenceKey(occurrence: CollectionOccurrence): string {
		return encodeURIComponent(`${occurrence.imagePath}\n${occurrence.birdIndex}`);
	}


	private sortedSpecies(species: CollectionSpecies[]): CollectionSpecies[] {
		return [...species].sort((left, right) => {
			const nameOrder = () => this.speciesName(left).localeCompare(this.speciesName(right), this.settings.appLanguage, { sensitivity: "base" });
			switch (this.collection.speciesSortOrder) {
				case "family":
					return (left.family_name || "\uffff").localeCompare(right.family_name || "\uffff", this.settings.appLanguage, { sensitivity: "base" }) || nameOrder();
				case "date":
					return this.firstCaptureDate(left).localeCompare(this.firstCaptureDate(right)) || nameOrder();
				case "location": {
					const leftLocation = this.firstLocation(left);
					const rightLocation = this.firstLocation(right);
					if (!leftLocation || !rightLocation) {
						return leftLocation ? -1 : rightLocation ? 1 : nameOrder();
					}
					return leftLocation.latitude - rightLocation.latitude || leftLocation.longitude - rightLocation.longitude || nameOrder();
				}
				case "imageCount":
					return right.imageCount - left.imageCount || nameOrder();
				case "confidence":
					return this.lowestConfidence(left) - this.lowestConfidence(right) || nameOrder();
				default:
					return nameOrder();
			}
		});
	}


	private firstCaptureDate(species: CollectionSpecies): string {
		return species.occurrences.map(item => this.normalizedCaptureDate(item.usedDatetime)).filter(Boolean).sort()[0] || "9999-99-99";
	}


	private firstLocation(species: CollectionSpecies): { latitude: number; longitude: number } | null {
		const locations = species.occurrences.flatMap(item => typeof item.usedLatitude === "number" && typeof item.usedLongitude === "number"
			? [{ latitude: item.usedLatitude, longitude: item.usedLongitude }]
			: []);
		locations.sort((left, right) => left.latitude - right.latitude || left.longitude - right.longitude);
		return locations[0] ?? null;
	}


	private lowestConfidence(species: CollectionSpecies): number {
		const confidences = species.occurrences.filter(occurrence => occurrence.classification.manual !== true).map(occurrence => occurrence.confidence);
		if (confidences.length === 0) {
			return 1;
		}

		return Math.min(...confidences);
	}


	private normalizedCaptureDate(value: string | null | undefined): string {
		const match = String(value || "").match(/^(\d{4})[:/-](\d{2})[:/-](\d{2})/);
		return match ? `${match[1]}-${match[2]}-${match[3]}` : "";
	}


	private filteredSpecies(species: CollectionSpecies[]): CollectionSpecies[] {
		const query = this.normalizedSearchText(this.collection.speciesSearchQuery.trim());

		return species.filter(item => {
			if (!query) {
				return true;
			}

			const visibleName = this.normalizedSearchText(this.speciesName(item));
			const latinName = this.normalizedSearchText(item.name_lat || "");
			const familyName = this.normalizedSearchText(item.family_name || "");
			return visibleName.includes(query) || latinName.includes(query) || familyName.includes(query);
		});
	}


	private speciesName(species: CollectionSpecies): string {
		return species.name || species.speciesId;
	}


	private renderSpeciesLatinName(species: CollectionSpecies): string {
		return species.name_lat ? `<em class="collection-species-card__latin">${escapeHtml(species.name_lat)}</em>` : "";
	}


	private normalizedSearchText(value: string): string {
		return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
	}
}
