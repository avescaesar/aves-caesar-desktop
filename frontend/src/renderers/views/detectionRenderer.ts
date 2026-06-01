import { iconBolt, iconCamera, iconGallery, iconImageSearch, iconPlay, iconShield } from "../../icons";
import type { DetectionState } from "../../state/detectionState";
import type { ImageViewportState } from "../../state/imageViewportState";
import type { SettingsState } from "../../state/settingsState";
import { escapeHtml, fileName, formatElapsedSeconds } from "../../utils";
import { BirdResultRenderer } from "./birdResultRenderer";
import type { RendererContext } from "../rendererContext";

export class DetectionRenderer {
	private readonly birdResultRenderer: BirdResultRenderer;


	public constructor(private readonly context: RendererContext, private readonly detection: DetectionState, private readonly imageViewport: ImageViewportState, private readonly settings: SettingsState) {
		this.birdResultRenderer = new BirdResultRenderer(context, detection, settings);
	}


	public render(): string {
		return this.detection.result ? this.renderAnalysisView() : this.renderPreDetectionView();
	}


	public renderAnalysisContent(): string {
		return this.renderDetectionContent();
	}


	private renderAnalysisView(): string {
		return `
		<section class="detection-view">
			<div class="section-heading">
				<div class="section-title">
					<button data-action="choose-image" class="toolbar-button is-primary new-photo-button" type="button">${iconCamera()}<span>${this.context.text("analysis.newPhoto")}</span></button>
					<h2>${this.context.text("analysis.title")}</h2>
				</div>
				<div class="analysis-actions">
					${this.renderAnalysisStats()}
				</div>
			</div>
			${this.renderDetectionContent()}
		</section>
	`;
	}


	private renderAnalysisStats(): string {
		if (!this.detection.result) {
			return "";
		}

		const elapsed = this.detection.result.elapsedSeconds == null ? "" : ` - ${formatElapsedSeconds(this.detection.result.elapsedSeconds)}`;
		return `<span>${this.context.text("analysis.detected", { count: this.detection.result.birds.length, elapsed })}</span>`;
	}


	private renderPreDetectionView(): string {
		return `
		<section class="detection-view pre-detection-view">
			<header class="pre-toolbar">
				<div class="toolbar-actions">
					<button data-action="choose-image" class="toolbar-button is-primary" type="button" ${this.detection.loading ? "disabled" : ""}>${iconCamera()}<span>${this.context.text("empty.choosePicture")}</span></button>
				</div>
			</header>
			<section class="pre-content">
				${this.detection.image ? this.renderSelectedImageSetup() : this.renderEmptySetup()}
			</section>
		</section>
	`;
	}


	private renderSelectedImageSetup(): string {
		if (!this.detection.image) {
			return "";
		}

		const path = escapeHtml(this.detection.image.path);
		const predictLabel = this.detection.loading ? this.context.text("detection.predicting") : this.context.text("detection.predict");
		return `
			<div class="selected-setup">
				<div class="selected-card">
				${this.renderSelectedThumbnail()}
				<div>
					<h2>${escapeHtml(fileName(this.detection.image.path))}</h2>
					<p>${path}</p>
				</div>
			</div>
			<section class="gps-card">
				<div class="gps-card__header">
					<div>
						<h3>${this.context.text("location.title")}</h3>
						<p>${this.context.text("location.intro")}</p>
					</div>
					<button id="chooseGpx" class="secondary-action" type="button" ${this.detection.loading ? "disabled" : ""}>${this.context.text("location.useGpx")}</button>
				</div>
				<div class="coordinate-grid">
					<label>
						<span>${this.context.text("location.latitude")}</span>
						<input id="latitude" inputmode="decimal" value="${escapeHtml(this.detection.latitude)}" placeholder="${this.context.text("common.optional")}" />
					</label>
					<label>
						<span>${this.context.text("location.longitude")}</span>
						<input id="longitude" inputmode="decimal" value="${escapeHtml(this.detection.longitude)}" placeholder="${this.context.text("common.optional")}" />
					</label>
				</div>
				<p class="status">${escapeHtml((this.detection.statusText || this.context.text(this.detection.statusKey, this.detection.statusParams)))}</p>
			</section>
			<button id="predictInline" class="large-predict" type="button" ${this.detection.loading ? "disabled" : ""}>${iconPlay()}<span>${predictLabel}</span></button>
		</div>
	`;
	}


	private renderSelectedThumbnail(): string {
		const thumbnail = this.detection.image?.thumbnailDataUrl;
		if (thumbnail) {
			return `<img class="selected-thumbnail" src="${thumbnail}" alt="${this.context.text("image.thumbnailAlt")}" />`;
		}

		return `<div class="selected-icon">${iconGallery()}</div>`;
	}


	private renderEmptySetup(): string {
		return `
		<div class="empty-upload">
			<div class="empty-upload__icon">${iconImageSearch()}</div>
			<h2>${this.context.text("empty.noImage")}</h2>
			<p>${this.context.text("empty.intro")}</p>
			<div class="feature-grid">
				<article>
					${iconShield()}
					<strong>${this.context.text("empty.featureLocalTitle")}</strong>
					<span>${this.context.text("empty.featureLocalBody")}</span>
				</article>
				<article>
					${iconBolt()}
					<strong>${this.context.text("empty.featureModelTitle")}</strong>
					<span>${this.context.text("empty.featureModelBody")}</span>
				</article>
			</div>
		</div>
	`;
	}


	private renderDetectionContent(): string {
		const result = this.detection.result;
		if (!result) {
			return "";
		}

		if (result.birds.length === 0) {
			return `
			<div class="analysis-layout">
				${this.renderImagePreview()}
				<aside class="result-panel">
					<div class="empty-result">${this.context.text("detection.noBirds")}</div>
					${this.renderGpsWarning()}
				</aside>
			</div>
		`;
		}

		return `
		<div class="analysis-layout">
			${this.renderImagePreview()}
			<aside class="result-panel">
				${this.birdResultRenderer.renderResults()}
				${this.renderGpsWarning()}
			</aside>
		</div>
	`;
	}


	private renderImagePreview(): string {
		if (!this.detection.result) {
			return "";
		}

		return `
		<section class="image-panel">
			<div class="image-stage" data-image-stage>
				<div class="image-zoom-layer" data-image-zoom-layer style="transform: translate(${this.imageViewport.panX}px, ${this.imageViewport.panY}px);">
					<img src="${this.detection.result.previewDataUrl}" alt="${this.context.text("image.previewAlt")}" />
					${this.birdResultRenderer.renderBirdBoxes()}
				</div>
			</div>
		</section>
	`;
	}


	private renderGpsWarning(): string {
		if (this.detection.hasCoordinates() || this.detection.resultUsedCoordinates()) {
			return "";
		}

		return `
		<div class="gps-warning">
			<strong>${this.context.text("detection.gpsMissingTitle")}</strong>
			<span>${this.context.text("detection.gpsMissingBody")}</span>
		</div>
	`;
	}
}
