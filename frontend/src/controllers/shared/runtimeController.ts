import { CollectionState } from "../../state/collectionState";
import { loadTranslations } from "../../i18n/translations";
import { OrganizationState } from "../../state/organizationState";
import type { RuntimeInfo } from "../../types";
import type { AppControllerContext } from "../core/appControllerContext";
import type { EventBinder } from "../core/eventBinder";
import type { CollectionController } from "../view/collectionController";
import type { LightroomController } from "../view/lightroomController";

export class RuntimeController {
	private runtimeInfoTimer: number | null = null;


	public constructor(private readonly context: AppControllerContext, private readonly organizationState: OrganizationState, private readonly collectionState: CollectionState, private readonly collectionController: CollectionController, private readonly lightroomController: LightroomController) {}


	public bindEvents(bindEvent: EventBinder): void {
		bindEvent(document.querySelector<HTMLButtonElement>("#refreshRuntime"), "click", () => void this.refreshRuntime());
	}


	public async loadRuntimeInfo(): Promise<void> {
		try {
			const info = await this.context.apiClient.runtimeInfo();
			this.applyRuntimeInfo(info);
			await loadTranslations(this.context.state.settings.appLanguage);
			void this.collectionController.preloadCollectionIndex();
			await this.lightroomController.loadLightroomInfo();
			this.lightroomController.openUpgradePromptIfNeeded();
			this.context.render();
			this.scheduleRuntimeInfoRefresh(info.runtimeDevice);
		} catch {
			return;
		}
	}


	private async refreshRuntime(): Promise<void> {
		this.context.state.runtime.startDeviceDetection();
		this.context.render();
		try {
			const info = await this.context.apiClient.refreshRuntime();
			this.applyRuntimeInfo(info);
			await loadTranslations(this.context.state.settings.appLanguage);
			this.context.render();
			this.scheduleRuntimeInfoRefresh(info.runtimeDevice);
		} catch {
			return;
		}
	}


	private scheduleRuntimeInfoRefresh(runtimeDevice: string): void {
		if (!this.context.state.runtime.isDetecting(runtimeDevice) || this.runtimeInfoTimer !== null) {
			return;
		}

		this.runtimeInfoTimer = window.setTimeout(() => {
			this.runtimeInfoTimer = null;
			void this.loadRuntimeInfo();
		}, 500);
	}


	private applyRuntimeInfo(info: RuntimeInfo): void {
		this.context.state.runtime.appVersion = info.appVersion || "0.0.0";
		this.context.state.runtime.versionDetails = info.versionDetails ?? null;
		this.context.state.settings.applyAvailableAppLanguages(info.availableAppLanguages ?? [], info.appLanguagePreference ?? "system");
		this.context.state.runtime.applyDevice(info.runtimeProvider, info.runtimeDevice);
		this.context.state.runtime.appIconDataUrl = info.appIconDataUrl;
		this.organizationState.sourceDirectory = info.batchSourceDirectory;
		this.organizationState.destinationDirectory = info.batchDestinationDirectory;
		this.organizationState.recursive = info.batchRecursive;
		this.organizationState.renameFiles = info.batchRenameFiles;
		this.collectionState.directory = info.collectionDirectory;
		this.collectionState.scanMode = info.collectionScanMode || "raw_jpeg";
		this.collectionState.scanEnabled = info.collectionScanEnabled === true;
		this.context.state.settings.acceptedClassificationThreshold = info.acceptedClassificationThreshold;
		this.context.state.settings.gpxMatchToleranceSeconds = info.gpxMatchToleranceSeconds;
	}
}
