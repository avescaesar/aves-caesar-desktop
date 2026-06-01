export type ImageInfo = {
	path: string;
	latitude: number | null;
	longitude: number | null;
	datetime: string | null;
	thumbnailDataUrl?: string | null;
};


export type GpxMatch = {
	latitude: number;
	longitude: number;
	timestamp: string | null;
	secondsDelta: number | null;
};


export type Classification = {
	species_id: string;
	confidence: number;
	name?: string;
	name_language?: string;
	name_lat?: string;
	manual?: boolean;
};


export type ManualCorrection = {
	speciesId: string;
	originalClassification: Classification | null;
};


export type BirdResult = {
	box: number[];
	box_confidence: number;
	classification: Classification[];
	manualCorrection?: ManualCorrection | null;
};


export type PredictResponse = {
	provider: string[];
	birds: BirdResult[];
	lowConfidenceThreshold: number;
	acceptedClassificationThreshold: number;
	usedLatitude?: number | null;
	usedLongitude?: number | null;
	usedDatetime?: string | null;
	previewDataUrl: string;
	width: number;
	height: number;
	elapsedSeconds?: number;
};


export type AppLanguage = string;


export type AppLanguagePreference = AppLanguage | "system";


export type CollectionScanMode = "raw" | "jpeg" | "raw_jpeg";


export enum ActiveView {
	Detection = "detection",
	Collection = "collection",
	Organization = "organization",
	Lightroom = "lightroom",
}


export type ModelPerformanceBlock = {
	familyTop1Percent: number;
	speciesF1Percent: number;
	speciesTop1Percent: number;
	speciesTop5Percent: number;
};


export type ClassifierModelPerformance = {
	withGps: ModelPerformanceBlock | null;
	withoutGps: ModelPerformanceBlock | null;
};


export type ModelBuildFile = {
	path: string;
	size?: number;
	sha256?: string;
	url?: string;
};


export type ModelBuildInfo = {
	repository: string;
	repositoryUrl: string;
	revision: string;
	downloadedAt: string;
	files: ModelBuildFile[];
};


export type VersionDetails = {
	appExecutableDate: string | null;
	classifierModelPerformance: ClassifierModelPerformance | null;
	modelBuildInfo: ModelBuildInfo | null;
};


export type PredictionJobStart = {
	jobId: string;
};


export type PredictionJobStatus = {
	state: "running" | "done" | "error" | "missing";
	result?: PredictResponse;
	error?: string;
};


export type RuntimeInfo = {
	appVersion: string;
	versionDetails: VersionDetails;
	availableAppLanguages: AppLanguage[];
	appLanguagePreference: AppLanguagePreference;
	batchSourceDirectory: string;
	batchDestinationDirectory: string;
	batchRecursive: boolean;
	batchRenameFiles: boolean;
	collectionDirectory: string;
	collectionScanMode: CollectionScanMode;
	collectionScanEnabled: boolean;
	acceptedClassificationThreshold: number;
	gpxMatchToleranceSeconds: number;
	appIconDataUrl: string | null;
	runtimeProvider: string;
	runtimeDevice: string;
};


export type UpdateCheckState = "available" | "current" | "development" | "error" | "idle";


export type UpdateInfo = {
	state: UpdateCheckState;
	currentVersion: string;
	availableVersion: string | null;
	ignored: boolean;
	error: string;
	flightId: string;
	platform?: string;
	url?: string;
	sha256?: string;
	publishedAt?: number;
};


export type UpdateInstallStart = {
	jobId: string;
};


export type UpdateInstallStatus = {
	jobId: string;
	state: "cancelled" | "checking" | "downloading" | "done" | "error" | "installing" | "missing" | "preparing" | "verifying";
	message: string;
	completedBytes: number;
	totalBytes: number | null;
	progressPercent: number | null;
	downloadSpeedBytesPerSecond: number | null;
	installerPath: string;
};


export type ClearCacheResponse = {
	clearedEntries: number;
	clearedCollectionThumbnails: number;
};


export type ExportLogsResponse = {
	zipPath: string;
	logCount: number;
};


export type BirdName = {
	species_id: string;
	name: string;
	name_language?: string;
	name_lat: string;
};


export type LightroomServerInfo = {
	running: boolean;
	host: string;
	port: number;
	apiVersion: string;
};


export type LightroomPluginInfo = {
	installed: boolean;
	installedVersion: string | null;
	availableVersion: string | null;
	port: string;
};


export type LightroomInfo = {
	server: LightroomServerInfo;
	plugin: LightroomPluginInfo;
};


export type PredictRequest = {
	imagePath: string;
	latitude: string | number | null;
	longitude: string | number | null;
	datetime: string | null;
};


export type OrganizationRequest = {
	sourceDirectory: string;
	destinationDirectory: string;
	gpxPaths: string[];
	organizationMethod: "species";
	renameFiles: boolean;
	recursive: boolean;
	allowNonEmptyDestination: boolean;
};


export type OrganizationJobStart = {
	jobId: string;
};


export type OrganizationJobStatus = {
	state: "running" | "done" | "stopped" | "error" | "missing";
	total: number;
	completed: number;
	copied: number;
	errors: number;
	currentFile: string;
	message: string;
	error?: string;
};


export type CollectionOccurrence = {
	imagePath: string;
	birdIndex: number;
	box: number[];
	confidence: number;
	usedLatitude?: number | null;
	usedLongitude?: number | null;
	usedDatetime?: string | null;
	thumbnailDataUrl: string | null;
	classification: Classification;
};


export type CollectionSpecies = {
	speciesId: string;
	name?: string;
	name_language?: string;
	name_lat?: string;
	thumbnailDataUrl: string | null;
	occurrenceCount: number;
	imageCount: number;
	occurrences: CollectionOccurrence[];
};


export type CollectionJobStart = {
	jobId: string;
};


export type CollectionJobStatus = {
	state: "running" | "done" | "stopped" | "error" | "missing";
	total: number;
	completed: number;
	errors: number;
	currentFile: string;
	message: string;
	species: CollectionSpecies[];
	error?: string;
};
