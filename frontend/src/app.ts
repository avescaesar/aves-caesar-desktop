import type { AppControllerContext } from "./controllers/core/appControllerContext";
import { ImageViewportController } from "./controllers/shared/imageViewportController";
import { RuntimeController } from "./controllers/shared/runtimeController";
import { SettingsController } from "./controllers/shared/settingsController";
import { UpdateController } from "./controllers/shared/updateController";
import { CollectionController } from "./controllers/view/collectionController";
import { DetectionController } from "./controllers/view/detectionController";
import { LightroomController } from "./controllers/view/lightroomController";
import { OrganizationController } from "./controllers/view/organizationController";
import { ViewRouter } from "./controllers/routing/viewRouter";
import { EventBindingRegistry } from "./eventBindingRegistry";
import { AppRenderer } from "./renderers/appRenderer";
import { BackendApiClient } from "./backendApiClient";
import { loadTranslations, translate, type TranslationKey, type TranslationParams } from "./i18n/translations";
import { AppState } from "./state/appState";
import { CollectionState } from "./state/collectionState";
import { DetectionState } from "./state/detectionState";
import { ImageViewportState } from "./state/imageViewportState";
import { LightroomState } from "./state/lightroomState";
import { OrganizationState } from "./state/organizationState";
import { SpeciesCorrectionState } from "./state/speciesCorrectionState";

export class AvesCaesarApp {
	private readonly apiClient = new BackendApiClient();
	private readonly state = new AppState();
	private readonly organizationState = new OrganizationState();
	private readonly collectionState = new CollectionState();
	private readonly speciesCorrectionState = new SpeciesCorrectionState();
	private readonly detectionState = new DetectionState();
	private readonly imageViewportState = new ImageViewportState();
	private readonly lightroomState = new LightroomState();
	private readonly renderer: AppRenderer;
	private readonly detectionController: DetectionController;
	private readonly organizationController: OrganizationController;
	private readonly collectionController: CollectionController;
	private readonly imageViewportController: ImageViewportController;
	private readonly lightroomController: LightroomController;
	private readonly runtimeController: RuntimeController;
	private readonly settingsController: SettingsController;
	private readonly updateController: UpdateController;
	private readonly viewRouter: ViewRouter;
	private readonly eventBindings = new EventBindingRegistry();


	public constructor(private readonly appElement: HTMLDivElement) {
		const controllerContext: AppControllerContext = {
			state: this.state,
			apiClient: this.apiClient,
			render: (preserveModal = false) => this.render(preserveModal),
			text: (key: TranslationKey, params: TranslationParams = {}) => this.text(key, params),
		};
		this.detectionController = new DetectionController(controllerContext, this.detectionState, this.speciesCorrectionState, this.imageViewportState, () => this.renderer.updateCorrectionOptions(), correction => this.collectionController.refreshAfterPredictionCorrection(correction));
		this.organizationController = new OrganizationController(controllerContext, this.organizationState);
		this.collectionController = new CollectionController(controllerContext, this.collectionState, this.detectionState, this.speciesCorrectionState, this.imageViewportState, this.detectionController);
		this.imageViewportController = new ImageViewportController(this.imageViewportState, this.detectionState);
		this.lightroomController = new LightroomController(controllerContext, this.lightroomState);
		this.runtimeController = new RuntimeController(controllerContext, this.organizationState, this.collectionState, this.collectionController, this.lightroomController);
		this.settingsController = new SettingsController(controllerContext, this.state.settings, this.collectionState, this.detectionState, this.speciesCorrectionState, this.collectionController);
		this.updateController = new UpdateController(controllerContext, this.state.update);
		this.viewRouter = new ViewRouter(controllerContext, [this.detectionController, this.collectionController, this.organizationController, this.lightroomController]);
		this.renderer = new AppRenderer({ organization: this.organizationState, collection: this.collectionState, speciesCorrection: this.speciesCorrectionState, detection: this.detectionState, imageViewport: this.imageViewportState, lightroom: this.lightroomState, navigation: this.state.navigation, runtime: this.state.runtime, settings: this.state.settings, update: this.state.update });
	}


	public async start(): Promise<void> {
		await loadTranslations(this.state.settings.appLanguage);
		window.addEventListener("pywebviewready", () => {
			this.apiClient.logFrontendEvent("frontend_ready", { activeView: this.state.navigation.activeView });
			void this.runtimeController.loadRuntimeInfo();
			this.updateController.start();
		});
		window.addEventListener("resize", () => this.imageViewportController.fitStage());
		window.addEventListener("mousemove", event => this.imageViewportController.storePointerPosition(event));
		window.addEventListener("keydown", event => {
			if (this.collectionController.handleNavigationKey(event)) {
				return;
			}

			this.imageViewportController.handleGlobalKeyDown(event);
		});
		this.render();
	}


	private render(preserveModal = false): void {
		if (preserveModal && this.renderer.updateCollectionView()) {
			this.bindEvents();
			this.imageViewportController.fitStageIfNeeded();
			return;
		}

		document.documentElement.lang = this.state.settings.appLanguage;
		this.appElement.innerHTML = this.renderer.render();
		this.bindEvents();
		this.imageViewportController.fitStage();
	}


	private bindEvents(): void {
		const bindEvent = this.eventBindings.bind;
		this.detectionController.bindEvents(bindEvent, this.appElement);
		this.organizationController.bindEvents(bindEvent);
		this.collectionController.bindEvents(bindEvent);
		this.imageViewportController.bindEvents(bindEvent);
		this.lightroomController.bindEvents(bindEvent);
		this.runtimeController.bindEvents(bindEvent);
		this.settingsController.bindEvents(bindEvent);
		this.updateController.bindEvents(bindEvent);
		this.viewRouter.bindEvents(bindEvent);
	}


	private text(key: TranslationKey, params: TranslationParams = {}): string {
		return translate(this.state.settings.appLanguage, key, params);
	}
}
