import { UpdateState } from "../../state/updateState";
import { errorMessage } from "../../utils";
import type { AppControllerContext } from "../core/appControllerContext";
import type { EventBinder } from "../core/eventBinder";

export class UpdateController {
	private static readonly CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
	private static readonly INSTALL_STATUS_INTERVAL_MS = 300;
	private checkTimer: number | null = null;
	private installCancellationRequested = false;
	private installStatusTimer: number | null = null;


	public constructor(private readonly context: AppControllerContext, private readonly state: UpdateState) {}


	public bindEvents(bindEvent: EventBinder): void {
		bindEvent(document.querySelector<HTMLButtonElement>("#closeUpdatePrompt"), "click", () => void this.closePrompt());
		bindEvent(document.querySelector<HTMLButtonElement>("#installUpdate"), "click", () => void this.installUpdate());
		bindEvent(document.querySelector<HTMLButtonElement>("#cancelUpdateInstall"), "click", () => void this.cancelInstallUpdate(true));
		bindEvent(document.querySelector<HTMLButtonElement>("#openUpdatePrompt"), "click", () => this.openPrompt());
	}


	public start(): void {
		void this.checkForUpdates();
		this.scheduleNextCheck();
	}


	public async checkForUpdates(): Promise<void> {
		try {
			this.state.info = await this.context.apiClient.checkForUpdates();
			this.state.message = "";
		} catch (error) {
			this.state.message = errorMessage(error);
		}

		this.context.render();
	}


	private openPrompt(): void {
		if (!this.state.hasAvailableUpdate()) {
			return;
		}

		this.state.promptOpen = true;
		this.context.render();
	}


	private async closePrompt(): Promise<void> {
		if (this.state.busy) {
			await this.cancelInstallUpdate(true);
			return;
		}

		this.state.promptOpen = false;
		this.context.render();
	}


	private async installUpdate(): Promise<void> {
		this.installCancellationRequested = false;
		this.state.busy = true;
		this.state.message = "";
		this.state.installStatus = null;
		this.context.render();
		try {
			const start = await this.context.apiClient.downloadAndInstallUpdate();
			this.state.installJobId = start.jobId;
			if (this.installCancellationRequested) {
				await this.cancelInstallUpdate(true);
				return;
			}

			await this.pollInstallStatus();
		} catch (error) {
			this.state.message = errorMessage(error);
			this.installCancellationRequested = false;
			this.state.busy = false;
			this.context.render();
		}
	}


	private async cancelInstallUpdate(closePrompt: boolean): Promise<void> {
		this.installCancellationRequested = true;
		this.clearInstallStatusTimer();
		const jobId = this.state.installJobId;
		if (!jobId) {
			this.state.busy = false;
			this.state.installStatus = null;
			if (closePrompt) {
				this.state.promptOpen = false;
			}

			this.context.render();
			return;
		}

		try {
			this.state.installStatus = await this.context.apiClient.cancelUpdateInstall(jobId);
			this.state.message = "";
			this.state.installJobId = null;
			this.installCancellationRequested = false;
			this.state.busy = false;
			if (closePrompt) {
				this.state.promptOpen = false;
			}
		} catch (error) {
			this.state.message = errorMessage(error);
			this.installCancellationRequested = false;
			this.state.busy = false;
		}

		this.context.render();
	}


	private async pollInstallStatus(): Promise<void> {
		const jobId = this.state.installJobId;
		if (!jobId) {
			return;
		}

		try {
			this.state.installStatus = await this.context.apiClient.updateInstallStatus(jobId);
			this.state.message = this.state.installStatus.state === "error" ? this.state.installStatus.message : "";
		} catch (error) {
			this.state.message = errorMessage(error);
			this.state.busy = false;
			this.context.render();
			return;
		}

		if (this.state.installStatus.state === "cancelled" || this.state.installStatus.state === "error" || this.state.installStatus.state === "missing") {
			this.state.busy = false;
			this.state.installJobId = null;
			this.installCancellationRequested = false;
			this.context.render();
			return;
		}

		if (this.state.installStatus.state === "done") {
			this.state.promptOpen = false;
			this.state.installJobId = null;
			this.installCancellationRequested = false;
			this.context.render();
			return;
		}

		this.context.render();
		this.installStatusTimer = window.setTimeout(() => void this.pollInstallStatus(), UpdateController.INSTALL_STATUS_INTERVAL_MS);
	}


	private scheduleNextCheck(): void {
		if (this.checkTimer !== null) {
			window.clearTimeout(this.checkTimer);
		}

		this.checkTimer = window.setTimeout(() => {
			this.checkTimer = null;
			void this.checkForUpdates();
			this.scheduleNextCheck();
		}, UpdateController.CHECK_INTERVAL_MS);
	}


	private clearInstallStatusTimer(): void {
		if (this.installStatusTimer === null) {
			return;
		}

		window.clearTimeout(this.installStatusTimer);
		this.installStatusTimer = null;
	}
}
