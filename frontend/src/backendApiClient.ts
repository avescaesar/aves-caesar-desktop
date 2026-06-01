import type { BirdName, ClearCacheResponse, CollectionJobStart, CollectionJobStatus, CollectionScanMode, ExportLogsResponse, GpxMatch, ImageInfo, LightroomInfo, OrganizationJobStart, OrganizationJobStatus, OrganizationRequest, PredictRequest, PredictResponse, PredictionJobStart, PredictionJobStatus, AppLanguage, AppLanguagePreference, RuntimeInfo, UpdateInfo, UpdateInstallStart, UpdateInstallStatus } from "./types";

type PywebviewBackendApi = {
	choose_image: () => Promise<ImageInfo | null>;
	choose_gpx: () => Promise<string[] | null>;
	choose_directory: () => Promise<string | null>;
	directory_has_entries: (path: string) => Promise<boolean>;
	reveal_in_file_explorer: (path: string) => Promise<{ path: string }>;
	match_gpx: (gpxPaths: string[], photoDatetime: string | null) => Promise<GpxMatch | null>;
	cached_prediction_preview: (request: Record<string, unknown>) => Promise<PredictResponse>;
	start_predict: (request: Record<string, unknown>) => Promise<PredictionJobStart>;
	prediction_status: (jobId: string) => Promise<PredictionJobStatus>;
	start_batch: (request: Record<string, unknown>) => Promise<OrganizationJobStart>;
	batch_status: (jobId: string) => Promise<OrganizationJobStatus>;
	stop_batch: (jobId: string) => Promise<OrganizationJobStatus>;
	start_collection_scan: (request: Record<string, unknown>) => Promise<CollectionJobStart>;
	collection_index: (baseDirectory: string, scanMode: CollectionScanMode) => Promise<CollectionJobStatus>;
	collection_status: (jobId: string) => Promise<CollectionJobStatus>;
	stop_collection_scan: (jobId: string) => Promise<CollectionJobStatus>;
	runtime_info: () => Promise<RuntimeInfo>;
	refresh_runtime: () => Promise<RuntimeInfo>;
	clear_prediction_cache: () => Promise<ClearCacheResponse>;
	bird_names: (language: AppLanguage) => Promise<BirdName[]>;
	set_prediction_correction: (imagePath: string, birdIndex: number, speciesId: string) => Promise<{ imagePath: string; birdIndex: number; speciesId: string }>;
	clear_prediction_correction: (imagePath: string, birdIndex: number) => Promise<{ imagePath: string; birdIndex: number }>;
	log_frontend_event?: (event: string, payload: Record<string, unknown>) => Promise<{ path: string }>;
	export_logs: () => Promise<ExportLogsResponse>;
	lightroom_info: () => Promise<LightroomInfo>;
	install_lightroom_plugin: () => Promise<LightroomInfo>;
	uninstall_lightroom_plugin: () => Promise<LightroomInfo>;
	update_info: () => Promise<Record<string, unknown>>;
	check_for_updates: () => Promise<UpdateInfo>;
	download_and_install_update: () => Promise<UpdateInstallStart>;
	update_install_status: (jobId: string) => Promise<UpdateInstallStatus>;
	cancel_update_install: (jobId: string) => Promise<UpdateInstallStatus>;
	set_batch_directories: (sourceDirectory: string, destinationDirectory: string) => Promise<{ batchSourceDirectory: string; batchDestinationDirectory: string }>;
	set_batch_options: (recursive: boolean, renameFiles: boolean) => Promise<{ batchRecursive: boolean; batchRenameFiles: boolean }>;
	set_collection_directory: (path: string) => Promise<{ collectionDirectory: string }>;
	set_collection_scan_mode: (scanMode: CollectionScanMode) => Promise<{ collectionScanMode: CollectionScanMode }>;
	set_collection_scan_enabled: (enabled: boolean) => Promise<{ collectionScanEnabled: boolean }>;
	set_accepted_classification_threshold: (value: number) => Promise<{ acceptedClassificationThreshold: number }>;
	set_gpx_match_tolerance_seconds: (value: number) => Promise<{ gpxMatchToleranceSeconds: number }>;
	set_app_language_preference: (preference: AppLanguagePreference) => Promise<{ appLanguagePreference: AppLanguagePreference }>;
};

declare global {
	interface Window {
		pywebview?: {
			api: PywebviewBackendApi;
		};
	}
}


export class BackendApiClient {
	public chooseImage(): Promise<ImageInfo | null> {
		return this.api.choose_image();
	}


	public chooseGpx(): Promise<string[] | null> {
		return this.api.choose_gpx();
	}


	public chooseDirectory(): Promise<string | null> {
		return this.api.choose_directory();
	}


	public directoryHasEntries(path: string): Promise<boolean> {
		return this.api.directory_has_entries(path);
	}


	public revealInFileExplorer(path: string): Promise<{ path: string }> {
		return this.api.reveal_in_file_explorer(path);
	}


	public matchGpx(gpxPaths: string[], photoDatetime: string | null): Promise<GpxMatch | null> {
		return this.api.match_gpx(gpxPaths, photoDatetime);
	}


	public startPredict(request: PredictRequest): Promise<PredictionJobStart> {
		return this.api.start_predict(request);
	}


	public cachedPredictionPreview(request: PredictRequest): Promise<PredictResponse> {
		return this.api.cached_prediction_preview(request);
	}


	public predictionStatus(jobId: string): Promise<PredictionJobStatus> {
		return this.api.prediction_status(jobId);
	}


	public startOrganization(request: OrganizationRequest): Promise<OrganizationJobStart> {
		return this.api.start_batch(request);
	}


	public organizationStatus(jobId: string): Promise<OrganizationJobStatus> {
		return this.api.batch_status(jobId);
	}


	public stopOrganization(jobId: string): Promise<OrganizationJobStatus> {
		return this.api.stop_batch(jobId);
	}


	public startCollectionScan(baseDirectory: string, scanMode: CollectionScanMode): Promise<CollectionJobStart> {
		return this.api.start_collection_scan({ baseDirectory, scanMode });
	}


	public collectionIndex(baseDirectory: string, scanMode: CollectionScanMode): Promise<CollectionJobStatus> {
		return this.api.collection_index(baseDirectory, scanMode);
	}


	public collectionStatus(jobId: string): Promise<CollectionJobStatus> {
		return this.api.collection_status(jobId);
	}


	public stopCollectionScan(jobId: string): Promise<CollectionJobStatus> {
		return this.api.stop_collection_scan(jobId);
	}


	public runtimeInfo(): Promise<RuntimeInfo> {
		return this.api.runtime_info();
	}


	public refreshRuntime(): Promise<RuntimeInfo> {
		return this.api.refresh_runtime();
	}


	public clearPredictionCache(): Promise<ClearCacheResponse> {
		return this.api.clear_prediction_cache();
	}


	public birdNames(language: AppLanguage): Promise<BirdName[]> {
		return this.api.bird_names(language);
	}


	public setPredictionCorrection(imagePath: string, birdIndex: number, speciesId: string): Promise<{ imagePath: string; birdIndex: number; speciesId: string }> {
		return this.api.set_prediction_correction(imagePath, birdIndex, speciesId);
	}


	public clearPredictionCorrection(imagePath: string, birdIndex: number): Promise<{ imagePath: string; birdIndex: number }> {
		return this.api.clear_prediction_correction(imagePath, birdIndex);
	}


	public logFrontendEvent(event: string, payload: Record<string, unknown> = {}): void {
		const logger = window.pywebview?.api?.log_frontend_event;
		if (!logger) {
			return;
		}

		void logger(event, payload).catch(() => undefined);
	}


	public exportLogs(): Promise<ExportLogsResponse> {
		return this.api.export_logs();
	}


	public lightroomInfo(): Promise<LightroomInfo> {
		return this.api.lightroom_info();
	}


	public installLightroomPlugin(): Promise<LightroomInfo> {
		return this.api.install_lightroom_plugin();
	}


	public uninstallLightroomPlugin(): Promise<LightroomInfo> {
		return this.api.uninstall_lightroom_plugin();
	}


	public updateInfo(): Promise<Record<string, unknown>> {
		return this.api.update_info();
	}


	public checkForUpdates(): Promise<UpdateInfo> {
		return this.api.check_for_updates();
	}


	public downloadAndInstallUpdate(): Promise<UpdateInstallStart> {
		return this.api.download_and_install_update();
	}


	public updateInstallStatus(jobId: string): Promise<UpdateInstallStatus> {
		return this.api.update_install_status(jobId);
	}


	public cancelUpdateInstall(jobId: string): Promise<UpdateInstallStatus> {
		return this.api.cancel_update_install(jobId);
	}


	public setOrganizationDirectories(sourceDirectory: string, destinationDirectory: string): Promise<{ batchSourceDirectory: string; batchDestinationDirectory: string }> {
		return this.api.set_batch_directories(sourceDirectory, destinationDirectory);
	}


	public setOrganizationOptions(recursive: boolean, renameFiles: boolean): Promise<{ batchRecursive: boolean; batchRenameFiles: boolean }> {
		return this.api.set_batch_options(recursive, renameFiles);
	}


	public setCollectionDirectory(path: string): Promise<{ collectionDirectory: string }> {
		return this.api.set_collection_directory(path);
	}


	public setCollectionScanMode(scanMode: CollectionScanMode): Promise<{ collectionScanMode: CollectionScanMode }> {
		return this.api.set_collection_scan_mode(scanMode);
	}


	public setCollectionScanEnabled(enabled: boolean): Promise<{ collectionScanEnabled: boolean }> {
		return this.api.set_collection_scan_enabled(enabled);
	}


	public setAcceptedClassificationThreshold(value: number): Promise<{ acceptedClassificationThreshold: number }> {
		return this.api.set_accepted_classification_threshold(value);
	}


	public setGpxMatchToleranceSeconds(value: number): Promise<{ gpxMatchToleranceSeconds: number }> {
		return this.api.set_gpx_match_tolerance_seconds(value);
	}


	public setAppLanguagePreference(preference: AppLanguagePreference): Promise<{ appLanguagePreference: AppLanguagePreference }> {
		return this.api.set_app_language_preference(preference);
	}


	private get api(): PywebviewBackendApi {
		if (!window.pywebview?.api) {
			throw new Error("Desktop API is not available.");
		}

		return window.pywebview.api;
	}
}
