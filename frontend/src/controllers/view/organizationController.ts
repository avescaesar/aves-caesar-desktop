import { OrganizationState } from "../../state/organizationState";
import { ActiveView } from "../../types";
import { delay, errorMessage } from "../../utils";
import type { AppControllerContext } from "../core/appControllerContext";
import type { EventBinder } from "../core/eventBinder";
import type { ViewController } from "./viewController";

const ORGANIZATION_DOM = {
	vertical: "organization",
	entities: {
		sourceDirectory: "source-directory",
		gpxTracks: "gpx-tracks",
		destinationDirectory: "destination-directory",
		recursiveOption: "recursive-option",
		renameOption: "rename-option",
		progress: "progress",
		destinationConflict: "destination-conflict",
	},
	actions: {
		choose: "choose",
		run: "run",
		open: "open",
		close: "close",
		cancel: "cancel",
		confirm: "confirm",
		stop: "stop",
		toggle: "toggle",
	},
} as const;

export class OrganizationController implements ViewController {
	public readonly view = ActiveView.Organization;


	public constructor(private readonly context: AppControllerContext, public readonly state: OrganizationState) {}


	public bindEvents(bindEvent: EventBinder): void {
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.sourceDirectory, ORGANIZATION_DOM.actions.choose), "click", () => void this.chooseSourceDirectory());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.gpxTracks, ORGANIZATION_DOM.actions.choose), "click", () => void this.chooseGpxTracks());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.destinationDirectory, ORGANIZATION_DOM.actions.choose), "click", () => void this.chooseDestinationDirectory());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.progress, ORGANIZATION_DOM.actions.run), "click", () => void this.runOrganization());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.progress, ORGANIZATION_DOM.actions.open), "click", () => this.openOrganizationProgress());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.progress, ORGANIZATION_DOM.actions.stop), "click", () => void this.stopOrganization());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.progress, ORGANIZATION_DOM.actions.close), "click", () => this.closeOrganizationProgress());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.destinationConflict, ORGANIZATION_DOM.actions.close), "click", () => this.closeNonEmptyDestinationConfirmation());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.destinationConflict, ORGANIZATION_DOM.actions.cancel), "click", () => this.closeNonEmptyDestinationConfirmation());
		bindEvent(this.organizationElement<HTMLButtonElement>(ORGANIZATION_DOM.entities.destinationConflict, ORGANIZATION_DOM.actions.confirm), "click", () => void this.runOrganizationWithConfirmedDestination());
		bindEvent(this.organizationElement<HTMLInputElement>(ORGANIZATION_DOM.entities.renameOption, ORGANIZATION_DOM.actions.toggle), "change", event => this.changeRenameFiles(event));
		bindEvent(this.organizationElement<HTMLInputElement>(ORGANIZATION_DOM.entities.recursiveOption, ORGANIZATION_DOM.actions.toggle), "change", event => this.changeRecursive(event));
	}


	public show(): void {
		this.context.state.navigation.activeView = this.view;
		this.context.render();
	}


	public hide(): void {}


	public async chooseSourceDirectory(): Promise<void> {
		try {
			const path = await this.context.apiClient.chooseDirectory();
			if (path) {
				this.state.sourceDirectory = path;
				await this.saveOrganizationDirectories();
			}
		} catch (error) {
			this.state.error = errorMessage(error);
		}

		this.context.render();
	}


	public async chooseDestinationDirectory(): Promise<void> {
		try {
			const path = await this.context.apiClient.chooseDirectory();
			if (path) {
				this.state.destinationDirectory = path;
				await this.saveOrganizationDirectories();
			}
		} catch (error) {
			this.state.error = errorMessage(error);
		}

		this.context.render();
	}


	public async chooseGpxTracks(): Promise<void> {
		try {
			const paths = await this.context.apiClient.chooseGpx();
			if (paths && paths.length > 0) {
				this.state.gpxPaths = paths;
			}
		} catch (error) {
			this.state.error = errorMessage(error);
		}

		this.context.render();
	}


	public changeRenameFiles(event: Event): void {
		this.state.renameFiles = (event.target as HTMLInputElement).checked;
		void this.saveOrganizationOptions();
		this.context.render();
	}


	public changeRecursive(event: Event): void {
		this.state.recursive = (event.target as HTMLInputElement).checked;
		void this.saveOrganizationOptions();
		this.context.render();
	}


	public async runOrganization(): Promise<void> {
		if (!this.state.canRun()) {
			return;
		}

		try {
			if (await this.context.apiClient.directoryHasEntries(this.state.destinationDirectory)) {
				this.state.confirmNonEmptyOpen = true;
				this.context.render();
				return;
			}
		} catch (error) {
			this.state.applyStatus({ state: "error", total: 0, completed: 0, copied: 0, errors: 0, currentFile: "", message: errorMessage(error), error: errorMessage(error) });
			this.state.modalOpen = true;
			this.context.render();
			return;
		}

		await this.startOrganization(false);
	}


	public async runOrganizationWithConfirmedDestination(): Promise<void> {
		this.state.confirmNonEmptyOpen = false;
		await this.startOrganization(true);
	}


	public closeNonEmptyDestinationConfirmation(): void {
		this.state.confirmNonEmptyOpen = false;
		this.context.render();
	}


	public openOrganizationProgress(): void {
		this.state.modalOpen = true;
		this.context.render();
	}


	public closeOrganizationProgress(): void {
		this.state.modalOpen = false;
		this.context.render();
	}


	public async stopOrganization(): Promise<void> {
		const jobId = this.state.activeJobId;
		if (!jobId) {
			return;
		}

		const status = await this.context.apiClient.stopOrganization(jobId);
		this.state.applyStatus(status);
		if (status.state === "stopped") {
			this.state.modalOpen = false;
		}

		this.context.render();
	}


	private async saveOrganizationDirectories(): Promise<void> {
		await this.context.apiClient.setOrganizationDirectories(this.state.sourceDirectory, this.state.destinationDirectory);
	}


	private async saveOrganizationOptions(): Promise<void> {
		await this.context.apiClient.setOrganizationOptions(this.state.recursive, this.state.renameFiles);
	}


	private async startOrganization(allowNonEmptyDestination: boolean): Promise<void> {
		if (!this.state.canRun()) {
			return;
		}

		this.state.modalOpen = true;
		this.state.error = "";
		this.context.render();

		try {
			const job = await this.context.apiClient.startOrganization({ sourceDirectory: this.state.sourceDirectory, destinationDirectory: this.state.destinationDirectory, gpxPaths: this.state.gpxPaths, organizationMethod: "species", renameFiles: this.state.renameFiles, recursive: this.state.recursive, allowNonEmptyDestination });
			this.state.start(job.jobId);
			this.context.render();
			await this.pollOrganization(job.jobId);
		} catch (error) {
			this.state.applyStatus({ state: "error", total: 0, completed: 0, copied: 0, errors: 0, currentFile: "", message: errorMessage(error), error: errorMessage(error) });
			this.context.render();
		}
	}


	private async pollOrganization(jobId: string): Promise<void> {
		while (this.state.activeJobId === jobId) {
			const status = await this.context.apiClient.organizationStatus(jobId);
			this.state.applyStatus(status);
			this.context.render();

			if (status.state !== "running") {
				return;
			}

			await delay(400);
		}
	}


	private organizationElement<T extends HTMLElement>(entity: string, action: string): T | null {
		return document.querySelector<T>(`[data-vertical="${ORGANIZATION_DOM.vertical}"][data-entity="${entity}"][data-action="${action}"]`);
	}
}
