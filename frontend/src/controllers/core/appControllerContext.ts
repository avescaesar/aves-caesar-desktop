import type { BackendApiClient } from "../../backendApiClient";
import type { TranslationKey, TranslationParams } from "../../i18n/translations";
import type { AppState } from "../../state/appState";

export type AppControllerContext = {
	state: AppState;
	apiClient: BackendApiClient;
	render: (preserveModal?: boolean) => void;
	text: (key: TranslationKey, params?: TranslationParams) => string;
};
