import type { CollectionState } from "../state/collectionState";
import type { DetectionState } from "../state/detectionState";
import type { ImageViewportState } from "../state/imageViewportState";
import type { LightroomState } from "../state/lightroomState";
import type { NavigationState } from "../state/navigationState";
import type { OrganizationState } from "../state/organizationState";
import type { RuntimeState } from "../state/runtimeState";
import type { SettingsState } from "../state/settingsState";
import type { SpeciesCorrectionState } from "../state/speciesCorrectionState";
import type { UpdateState } from "../state/updateState";
import { ActiveView } from "../types";
import { ModalRenderer } from "./modalRenderer";
import { RendererContext } from "./rendererContext";
import { ShellRenderer } from "./shellRenderer";
import { CollectionRenderer } from "./views/collectionRenderer";
import { DetectionRenderer } from "./views/detectionRenderer";
import { LightroomRenderer } from "./views/lightroomRenderer";
import { OrganizationRenderer } from "./views/organizationRenderer";

export class AppRenderer {
	private readonly context: RendererContext;
	private readonly activeViewState: NavigationState;
	private readonly shellRenderer: ShellRenderer;
	private readonly modalRenderer: ModalRenderer;
	private readonly organizationRenderer: OrganizationRenderer;
	private readonly collectionRenderer: CollectionRenderer;
	private readonly detectionRenderer: DetectionRenderer;
	private readonly lightroomRenderer: LightroomRenderer;


	public constructor(states: AppRendererStates) {
		this.context = new RendererContext(states.settings);
		this.activeViewState = states.navigation;
		this.shellRenderer = new ShellRenderer(this.context, states.navigation, states.runtime, states.update);
		this.modalRenderer = new ModalRenderer(this.context, states);
		this.organizationRenderer = new OrganizationRenderer(this.context, states.organization);
		this.detectionRenderer = new DetectionRenderer(this.context, states.detection, states.imageViewport, states.settings);
		this.collectionRenderer = new CollectionRenderer(this.context, states.collection, states.detection, states.imageViewport, states.settings);
		this.lightroomRenderer = new LightroomRenderer(this.context, states.lightroom);
	}


	public render(): string {
		return this.shellRenderer.render(this.renderActiveView(), this.modalRenderer.render());
	}


	public updateCollectionView(): boolean {
		if (this.activeViewState.activeView !== ActiveView.Collection) {
			return false;
		}

		return this.collectionRenderer.updateExistingView();
	}


	public updateCorrectionOptions(): boolean {
		return this.modalRenderer.updateCorrectionOptions();
	}


	private renderActiveView(): string {
		if (this.activeViewState.activeView === ActiveView.Lightroom) {
			return this.lightroomRenderer.render();
		}

		if (this.activeViewState.activeView === ActiveView.Organization) {
			return this.organizationRenderer.render();
		}

		if (this.activeViewState.activeView === ActiveView.Collection) {
			return this.collectionRenderer.render();
		}

		return this.detectionRenderer.render();
	}
}

export type AppRendererStates = {
	organization: OrganizationState;
	collection: CollectionState;
	speciesCorrection: SpeciesCorrectionState;
	detection: DetectionState;
	imageViewport: ImageViewportState;
	lightroom: LightroomState;
	navigation: NavigationState;
	runtime: RuntimeState;
	settings: SettingsState;
	update: UpdateState;
};
