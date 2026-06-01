import { iconFolder, iconPlay } from "../../icons";
import type { OrganizationState } from "../../state/organizationState";
import { escapeHtml, fileName } from "../../utils";
import type { RendererContext } from "../rendererContext";

const ORGANIZATION_DOM = {
	vertical: "organization",
	entities: {
		sourceDirectory: "source-directory",
		gpxTracks: "gpx-tracks",
		destinationDirectory: "destination-directory",
		recursiveOption: "recursive-option",
		renameOption: "rename-option",
		progress: "progress",
	},
	actions: {
		choose: "choose",
		run: "run",
		open: "open",
		toggle: "toggle",
	},
} as const;

export class OrganizationRenderer {
	public constructor(private readonly context: RendererContext, private readonly organization: OrganizationState) {}


	public render(): string {
		return `
		<section class="organization-view">
			<div class="section-heading">
				<div class="section-title">
					<h2>${this.context.text("organization.title")}</h2>
				</div>
				<div class="analysis-actions">
					${this.renderOrganizationHeaderAction()}
				</div>
			</div>
			<p class="organization-intro">${this.context.text("organization.intro")}</p>
			<section class="organization-content">
				${this.renderOrganizationStep("1", this.context.text("organization.sourceFolder"), this.renderOrganizationSourceStep())}
				${this.renderOrganizationStep("2", this.context.text("organization.gpxOptional"), this.renderOrganizationGpxStep(), "is-warm")}
				${this.renderOrganizationStep("3", this.context.text("organization.destination"), this.renderOrganizationDestinationStep())}
				${this.renderOrganizationStep("4", this.context.text("organization.options"), this.renderOrganizationOptionsStep())}
				${this.renderOrganizationRunAction()}
			</section>
		</section>
	`;
	}


	private renderOrganizationHeaderAction(): string {
		if (this.organization.activeJobId) {
			return `<button ${this.domAttributes(ORGANIZATION_DOM.entities.progress, ORGANIZATION_DOM.actions.open)} class="toolbar-button" type="button">${this.context.text("organization.progress")}</button>`;
		}

		return "";
	}


	private renderOrganizationRunAction(): string {
		if (this.organization.activeJobId) {
			return "";
		}

		return `
		<div class="organization-run-row">
			<button ${this.domAttributes(ORGANIZATION_DOM.entities.progress, ORGANIZATION_DOM.actions.run)} class="toolbar-button is-primary" type="button" ${this.organization.canRun() ? "" : "disabled"}>${iconPlay()}<span>${this.context.text("organization.run")}</span></button>
		</div>
	`;
	}


	private renderOrganizationStep(index: string, title: string, content: string, className = ""): string {
		return `
		<div class="organization-step ${className}">
			<div class="step-index">${index}</div>
			<div class="step-panel">
				<h3>${escapeHtml(title)}</h3>
				${content}
			</div>
		</div>
	`;
	}


	private renderOrganizationSourceStep(): string {
		return `
		<div class="path-picker">
			<input readonly value="${escapeHtml(this.organization.sourceDirectory)}" placeholder="${this.context.text("organization.selectSourcePlaceholder")}" />
			<button ${this.domAttributes(ORGANIZATION_DOM.entities.sourceDirectory, ORGANIZATION_DOM.actions.choose)} class="toolbar-button is-primary" type="button">${iconFolder()}<span>${this.context.text("common.browse")}</span></button>
		</div>
		<label class="organization-checkbox">
			<input ${this.domAttributes(ORGANIZATION_DOM.entities.recursiveOption, ORGANIZATION_DOM.actions.toggle)} type="checkbox" ${this.organization.recursive ? "checked" : ""} />
			<span>${this.context.text("organization.subfolders")}</span>
		</label>
	`;
	}


	private renderOrganizationGpxStep(): string {
		return `
		<p class="organization-help">${this.context.text("organization.gpxHelp")}</p>
		<div class="inline-picker">
			<button ${this.domAttributes(ORGANIZATION_DOM.entities.gpxTracks, ORGANIZATION_DOM.actions.choose)} class="secondary-action" type="button">${this.context.text("organization.selectGpx")}</button>
			<span>${this.renderGpxSelection(this.organization.gpxPaths)}</span>
		</div>
	`;
	}


	private renderOrganizationDestinationStep(): string {
		return `
		<div class="path-picker">
			<input readonly value="${escapeHtml(this.organization.destinationDirectory)}" placeholder="${this.context.text("organization.selectDestinationPlaceholder")}" />
			<button ${this.domAttributes(ORGANIZATION_DOM.entities.destinationDirectory, ORGANIZATION_DOM.actions.choose)} class="secondary-action" type="button">${this.context.text("organization.setPath")}</button>
		</div>
	`;
	}


	private renderOrganizationOptionsStep(): string {
		return `
		<label class="organization-checkbox">
			<input ${this.domAttributes(ORGANIZATION_DOM.entities.renameOption, ORGANIZATION_DOM.actions.toggle)} type="checkbox" ${this.organization.renameFiles ? "checked" : ""} />
			<span>${this.context.text("organization.renameFiles")}</span>
		</label>
	`;
	}


	private renderGpxSelection(paths: string[]): string {
		if (paths.length === 0) {
			return this.context.text("organization.noFileSelected");
		}

		if (paths.length === 1) {
			return escapeHtml(fileName(paths[0]));
		}

		return this.context.text("organization.filesSelected", { count: paths.length });
	}


	private domAttributes(entity: string, action: string): string {
		return `data-vertical="${ORGANIZATION_DOM.vertical}" data-entity="${entity}" data-action="${action}"`;
	}
}
