import { iconDownload, iconGallery, iconLayers, iconPlug, iconSettings, iconTarget } from "../icons";
import type { NavigationState } from "../state/navigationState";
import type { RuntimeState } from "../state/runtimeState";
import type { UpdateState } from "../state/updateState";
import { ActiveView, type ModelBuildInfo, type ModelPerformanceBlock } from "../types";
import { escapeHtml } from "../utils";
import type { RendererContext } from "./rendererContext";

const NAVIGATION_DOM = {
	vertical: "navigation",
	entities: {
		detection: "detection",
		collection: "collection",
		organization: "organization",
		lightroom: "lightroom",
	},
	action: "show",
} as const;

export class ShellRenderer {
	public constructor(private readonly context: RendererContext, private readonly navigation: NavigationState, private readonly runtime: RuntimeState, private readonly update: UpdateState) {}


	public render(content: string, overlays: string): string {
		return `
		<main class="app-shell">
			<section class="app-frame">
				${this.renderAppHeader()}
				<div class="app-body">
					${this.renderSidebar()}
					${content}
				</div>
				${overlays}
			</section>
		</main>
	`;
	}


	private renderAppHeader(): string {
		return `
		<header class="app-header">
			<h1>${this.renderAppIcon()}<span>Aves Caesar</span></h1>
			<div class="header-tools">
				${this.renderUpdateIndicator()}
				<button id="openSettings" class="icon-button header-icon-button" type="button" title="${this.context.text("settings.open")}" aria-label="${this.context.text("settings.open")}">${iconSettings()}</button>
			</div>
		</header>
	`;
	}


	private renderUpdateIndicator(): string {
		if (!this.update.shouldShowIndicator()) {
			return "";
		}

		const availableVersion = this.update.info?.availableVersion || "";
		const label = this.context.text("update.indicator", { version: availableVersion });
		return `<button id="openUpdatePrompt" class="update-indicator" type="button" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${iconDownload()}<span>v${escapeHtml(availableVersion)}</span></button>`;
	}


	private renderAppIcon(): string {
		return this.runtime.appIconDataUrl ? `<img class="app-logo" src="${this.runtime.appIconDataUrl}" alt="" />` : "";
	}


	private renderSidebar(): string {
		return `
		<aside class="side-nav">
			<nav>
				<button ${this.navigationDomAttributes(NAVIGATION_DOM.entities.detection)} class="nav-item ${this.navigation.activeView === ActiveView.Detection ? "is-active" : ""}" type="button">${iconTarget()}<span>${this.context.text("nav.detection")}</span></button>
				<button ${this.navigationDomAttributes(NAVIGATION_DOM.entities.collection)} class="nav-item ${this.navigation.activeView === ActiveView.Collection ? "is-active" : ""}" type="button">${iconGallery()}<span>${this.context.text("nav.collection")}</span></button>
				<button ${this.navigationDomAttributes(NAVIGATION_DOM.entities.organization)} class="nav-item ${this.navigation.activeView === ActiveView.Organization ? "is-active" : ""}" type="button">${iconLayers()}<span>${this.context.text("nav.organization")}</span></button>
				<button ${this.navigationDomAttributes(NAVIGATION_DOM.entities.lightroom)} class="nav-item ${this.navigation.activeView === ActiveView.Lightroom ? "is-active" : ""}" type="button">${iconPlug()}<span>${this.context.text("nav.lightroom")}</span></button>
			</nav>
			<div class="side-status">
				<div class="version-card">
					<span>${this.context.text("version.label")}</span>
					<strong class="version-value" tabindex="0" aria-describedby="versionTooltip">v${escapeHtml(this.runtime.appVersion)}</strong>
					${this.renderVersionTooltip()}
				</div>
			</div>
		</aside>
	`;
	}


	private renderVersionTooltip(): string {
		const details = this.runtime.versionDetails;
		const executableDate = this.formatDate(details?.appExecutableDate ?? null);
		const performance = details?.classifierModelPerformance ?? null;
		const modelBuildInfo = details?.modelBuildInfo ?? null;

		return `
		<div id="versionTooltip" class="version-tooltip" role="tooltip">
			<div class="version-tooltip__row">
				<span>${this.context.text("version.appDate")}</span>
				<strong>${escapeHtml(executableDate)}</strong>
			</div>
			${this.renderModelBuildInfo(modelBuildInfo)}
			<div class="version-tooltip__section">
				<span>${this.context.text("version.performance")}</span>
				${this.renderPerformanceLine(this.context.text("version.withGps"), performance?.withGps ?? null)}
				${this.renderPerformanceLine(this.context.text("version.withoutGps"), performance?.withoutGps ?? null)}
			</div>
		</div>
	`;
	}


	private renderModelBuildInfo(modelBuildInfo: ModelBuildInfo | null): string {
		if (!modelBuildInfo) {
			return "";
		}

		return `
			<div class="version-tooltip__section">
				<span>${this.context.text("version.model")}</span>
				<div class="version-tooltip__performance">
					<strong>${this.context.text("version.modelRepository")}</strong>
					<span>${escapeHtml(modelBuildInfo.repository)}</span>
				</div>
				<div class="version-tooltip__performance">
					<strong>${this.context.text("version.modelRevision")}</strong>
					<span>${escapeHtml(modelBuildInfo.revision)}</span>
				</div>
				<div class="version-tooltip__performance">
					<strong>${this.context.text("version.modelFiles")}</strong>
					<span>${modelBuildInfo.files.length}</span>
				</div>
			</div>
	`;
	}


	private renderPerformanceLine(label: string, performance: ModelPerformanceBlock | null): string {
		if (!performance) {
			return `<div class="version-tooltip__performance"><strong>${escapeHtml(label)}</strong><span>${this.context.text("common.unknown")}</span></div>`;
		}

		return `
		<div class="version-tooltip__performance">
			<strong>${escapeHtml(label)}</strong>
			<span>${this.context.text("version.species")} ${this.formatPercent(performance.speciesTop1Percent)} (${this.context.text("version.top5")} ${this.formatPercent(performance.speciesTop5Percent)})</span>
		</div>
	`;
	}


	private formatPercent(value: number): string {
		return `${value.toFixed(2)}%`;
	}


	private formatDate(value: string | null): string {
		if (!value) {
			return this.context.text("common.unknown");
		}

		const date = new Date(value);
		if (Number.isNaN(date.getTime())) {
			return this.context.text("common.unknown");
		}

		return new Intl.DateTimeFormat(this.context.locale(), { dateStyle: "medium", timeStyle: "short" }).format(date);
	}


	private navigationDomAttributes(entity: string): string {
		return `data-vertical="${NAVIGATION_DOM.vertical}" data-entity="${entity}" data-action="${NAVIGATION_DOM.action}"`;
	}
}
