import { AVAILABLE_APP_LANGUAGES } from "../i18n/translations";
import type { AppLanguage, AppLanguagePreference } from "../types";

export class SettingsState {
	public availableAppLanguages: AppLanguage[] = [...AVAILABLE_APP_LANGUAGES];
	public appLanguage: AppLanguage = this.systemAppLanguage();
	public appLanguageExplicit = false;
	public acceptedClassificationThreshold = 0.5;
	public gpxMatchToleranceSeconds = 300;
	public modalOpen = false;
	public cacheBusy = false;
	public logsBusy = false;
	public cacheMessage = "";


	public appLanguagePreference(): AppLanguagePreference {
		return this.appLanguageExplicit ? this.appLanguage : "system";
	}


	public systemAppLanguage(): AppLanguage {
		const language = navigator.language.toLowerCase().split("-", 1)[0];
		if (this.availableAppLanguages.includes(language)) {
			return language;
		}

		return this.availableAppLanguages.includes("en") ? "en" : (this.availableAppLanguages[0] ?? "en");
	}


	public applyAvailableAppLanguages(languages: AppLanguage[], preference: AppLanguagePreference = "system"): void {
		const supportedLanguages = languages.filter(language => AVAILABLE_APP_LANGUAGES.includes(language));
		this.availableAppLanguages = supportedLanguages.length ? supportedLanguages : [...AVAILABLE_APP_LANGUAGES];
		this.setAppLanguagePreference(preference);
	}


	public setAppLanguagePreference(preference: AppLanguagePreference): void {
		const supportedPreference = preference !== "system" && this.availableAppLanguages.includes(preference) ? preference : "system";
		this.appLanguageExplicit = supportedPreference !== "system";
		if (supportedPreference === "system") {
			this.appLanguage = this.systemAppLanguage();
			return;
		}

		this.appLanguage = supportedPreference;
	}
}
