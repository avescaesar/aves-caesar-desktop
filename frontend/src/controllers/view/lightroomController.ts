import { LightroomState } from "../../state/lightroomState";
import { ActiveView } from "../../types";
import { errorMessage } from "../../utils";
import type { AppControllerContext } from "../core/appControllerContext";
import type { EventBinder } from "../core/eventBinder";
import type { ViewController } from "./viewController";

export class LightroomController implements ViewController {
	private static readonly IGNORED_UPGRADE_VERSION_KEY = "aves.lightroom.ignoredUpgradeVersion";
	public readonly view = ActiveView.Lightroom;


	public constructor(private readonly context: AppControllerContext, public readonly state: LightroomState) {}


	public bindEvents(bindEvent: EventBinder): void {
		bindEvent(document.querySelector<HTMLButtonElement>("#installLightroomPlugin"), "click", () => void this.installLightroomPlugin());
		bindEvent(document.querySelector<HTMLButtonElement>("#uninstallLightroomPlugin"), "click", () => void this.uninstallLightroomPlugin());
		bindEvent(document.querySelector<HTMLButtonElement>("#closeLightroomUpgrade"), "click", () => this.ignoreLightroomUpgrade());
		bindEvent(document.querySelector<HTMLButtonElement>("#ignoreLightroomUpgrade"), "click", () => this.ignoreLightroomUpgrade());
		bindEvent(document.querySelector<HTMLButtonElement>("#confirmLightroomUpgrade"), "click", () => void this.upgradeLightroomPlugin());
	}


	public async show(): Promise<void> {
		this.context.state.navigation.activeView = this.view;
		this.context.render();
		await this.loadLightroomInfo();
		this.context.render();
	}


	public hide(): void {}


	public async loadLightroomInfo(): Promise<void> {
		try {
			this.state.info = await this.context.apiClient.lightroomInfo();
		} catch {
			return;
		}
	}


	public openUpgradePromptIfNeeded(): void {
		if (this.state.upgradePromptOpen || !this.isUpgradeAvailable()) {
			return;
		}

		const availableVersion = this.state.info?.plugin.availableVersion;
		if (!availableVersion || this.ignoredUpgradeVersion() === availableVersion) {
			return;
		}

		this.state.upgradeError = "";
		this.state.upgradePromptOpen = true;
	}


	public ignoreLightroomUpgrade(): void {
		const availableVersion = this.state.info?.plugin.availableVersion;
		if (availableVersion) {
			window.localStorage.setItem(LightroomController.IGNORED_UPGRADE_VERSION_KEY, availableVersion);
		}

		this.state.upgradeError = "";
		this.state.upgradePromptOpen = false;
		this.context.render();
	}


	public async upgradeLightroomPlugin(): Promise<void> {
		this.state.busy = true;
		this.state.upgradeError = "";
		this.context.render();
		try {
			this.state.info = await this.context.apiClient.installLightroomPlugin();
			this.state.upgradePromptOpen = false;
			this.state.message = "Lightroom plugin updated. Restart Lightroom Classic to load it.";
			window.localStorage.removeItem(LightroomController.IGNORED_UPGRADE_VERSION_KEY);
		} catch (error) {
			this.state.upgradeError = errorMessage(error);
		}

		this.state.busy = false;
		this.context.render();
	}


	public async installLightroomPlugin(): Promise<void> {
		this.state.busy = true;
		this.state.message = "";
		this.context.render();
		try {
			this.state.info = await this.context.apiClient.installLightroomPlugin();
			this.state.message = "Lightroom plugin installed. Restart Lightroom Classic to load it.";
		} catch (error) {
			this.state.message = errorMessage(error);
		}

		this.state.busy = false;
		this.context.render();
	}


	public async uninstallLightroomPlugin(): Promise<void> {
		this.state.busy = true;
		this.state.message = "";
		this.context.render();
		try {
			this.state.info = await this.context.apiClient.uninstallLightroomPlugin();
			this.state.message = "Lightroom plugin uninstalled. Restart Lightroom Classic to unload it.";
		} catch (error) {
			this.state.message = errorMessage(error);
		}

		this.state.busy = false;
		this.context.render();
	}


	private isUpgradeAvailable(): boolean {
		const plugin = this.state.info?.plugin;
		if (!plugin?.installed || !plugin.availableVersion) {
			return false;
		}

		return plugin.installedVersion !== plugin.availableVersion;
	}


	private ignoredUpgradeVersion(): string {
		return window.localStorage.getItem(LightroomController.IGNORED_UPGRADE_VERSION_KEY) || "";
	}
}
