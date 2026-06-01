import { iconChevronDown, iconPencil } from "../../icons";
import type { DetectionState } from "../../state/detectionState";
import type { SettingsState } from "../../state/settingsState";
import type { BirdResult, Classification } from "../../types";
import { escapeHtml, formatPercentWhole } from "../../utils";
import type { RendererContext } from "../rendererContext";

export class BirdResultRenderer {
	public constructor(private readonly context: RendererContext, private readonly detection: DetectionState, private readonly settings: SettingsState) {}


	public renderBirdBoxes(): string {
		if (!this.detection.result) {
			return "";
		}

		const result = this.detection.result;
		const boxes = result.birds.map((bird, birdIndex) => {
			const [x0, y0, x1, y1] = bird.box;
			const label = this.bestBirdName(bird);
			const left = (x0 / result.width) * 100;
			const top = (y0 / result.height) * 100;
			const width = ((x1 - x0) / result.width) * 100;
			const height = ((y1 - y0) / result.height) * 100;
			const confidence = bird.classification[0]?.confidence ?? bird.box_confidence;
			return `<div class="bird-box" data-bird-index="${birdIndex}" style="left: ${left}%; top: ${top}%; width: ${width}%; height: ${height}%;" aria-label="${escapeHtml(label)}"><button class="bird-box__label ${top < 8 ? "is-below" : ""}" data-bird-index="${birdIndex}" type="button">${this.context.text("detection.birdLabel", { index: birdIndex + 1 })}: ${escapeHtml(this.compactBirdName(bird))} ${formatPercentWhole(confidence)}</button></div>`;
		});
		return boxes.join("");
	}


	public renderResults(): string {
		if (!this.detection.result) {
			return `<div class="empty">${this.context.text("detection.emptyPanel")}</div>`;
		}

		if (this.detection.result.birds.length === 0) {
			return `<div class="empty">${this.context.text("detection.noDetectedBirds")}</div>`;
		}

		const cards = this.detection.result.birds.map((bird, birdIndex) => this.renderBirdCard(bird, birdIndex));
		return cards.join("");
	}


	private renderBirdCard(bird: BirdResult, birdIndex: number): string {
		const best = bird.classification[0];
		const bestName = best ? this.classificationDisplayName(best) : this.context.text("common.unknown");
		const latinName = best?.name_lat ? `<em>${escapeHtml(best.name_lat)}</em>` : "";
		const bestConfidence = best ? best.confidence : 0;
		const isManualCorrection = Boolean(bird.manualCorrection);
		const matchClass = `primary-match${bestConfidence < this.settings.acceptedClassificationThreshold && !isManualCorrection ? " is-unsure" : ""}${isManualCorrection ? " is-manual-correction" : ""}`;
		return `
			<details class="detection-card" data-bird-index="${birdIndex}" open>
				<summary>
					<h3>${this.context.text("detection.birdDetection", { index: birdIndex + 1 })}</h3>
					<span class="collapse-chevron">${iconChevronDown()}</span>
				</summary>
				<div class="detection-card__content">
					<div class="match-label primary-match-label"><span>${this.context.text("detection.primaryMatch")}</span>${this.renderCorrectionEditButton(birdIndex)}</div>
					<div class="${matchClass}">
					<div>
						<strong>${escapeHtml(bestName)}</strong>
						${latinName}
					</div>
					${this.renderPrimaryMatchBadge(bird, bestConfidence)}
					</div>
					${this.renderAlternates(bird.classification.slice(1))}
				</div>
			</details>
		`;
	}


	private renderPrimaryMatchBadge(bird: BirdResult, confidence: number): string {
		if (bird.manualCorrection) {
			return `<span class="primary-match__manual-badge" title="${escapeHtml(this.context.text("correction.manualBadge"))}" aria-label="${escapeHtml(this.context.text("correction.manualBadge"))}">${iconPencil()}</span>`;
		}

		return `<span>${formatPercentWhole(confidence)}</span>`;
	}


	private renderCorrectionEditButton(birdIndex: number): string {
		return `<button class="match-label__edit" data-action="edit-correction" data-bird-index="${birdIndex}" type="button" title="${escapeHtml(this.context.text("correction.edit"))}" aria-label="${escapeHtml(this.context.text("correction.edit"))}">${iconPencil()}</button>`;
	}


	private renderAlternates(items: Classification[]): string {
		if (!items.length) {
			return "";
		}

		const rows = items.slice(0, 3).map(item => `<div class="alternate-row"><div><strong>${escapeHtml(this.classificationDisplayName(item))}</strong>${this.renderLatinName(item)}</div><span>${formatPercentWhole(item.confidence)}</span></div>`);
		return `
		<div class="match-label">${this.context.text("detection.alternates")}</div>
		<div class="alternates">${rows.join("")}</div>
	`;
	}


	private renderLatinName(item: Classification): string {
		return item.name_lat ? `<em>${escapeHtml(item.name_lat)}</em>` : "";
	}


	private bestBirdName(bird: BirdResult): string {
		const best = bird.classification[0];
		return best ? this.classificationName(best) : this.context.text("common.unknown");
	}


	private compactBirdName(bird: BirdResult): string {
		const best = bird.classification[0];
		return best ? this.classificationDisplayName(best) : this.context.text("common.unknown");
	}


	private classificationName(item: Classification): string {
		const baseName = item.name || item.species_id;
		return item.name_lat ? `${baseName} (${item.name_lat})` : baseName;
	}


	private classificationDisplayName(item: Classification): string {
		return item.name || item.species_id;
	}
}
